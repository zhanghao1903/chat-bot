from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from group_llm_agent.avatar import (
    AvatarController,
    approve_avatar_catalog,
    enable_avatar_rotation,
    load_avatar_catalog,
)
from group_llm_agent.database import SQLiteDatabase
from group_llm_agent.expression import (
    ExpressionCatalogError,
    canonical_json_bytes,
    load_expression_catalog,
)
from group_llm_agent.expression_manage import (
    TelegramStickerMapping,
    approve_expression_catalog,
    attach_telegram_mapping,
    enable_expression_catalog,
)
from group_llm_agent.operator_lock import OperatorInterrupted, operator_lock
from group_llm_agent.platforms.telegram import TelegramApiError, TelegramBotApiClient
from group_llm_agent.sticker_publish import StickerPackPublisher, StickerPublishRequest
from group_llm_agent.telegram_multipart import TelegramMultipartTransport

_DEFAULT_LOCK = Path("/tmp/group-llm-agent-operator.lock")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
    except (ExpressionCatalogError, OperatorInterrupted, TelegramApiError, RuntimeError) as error:
        code = str(getattr(error, "code", getattr(error, "category", type(error).__name__)))
        print(f"operator_error={code}", file=sys.stderr)
        return 2
    if result is not None:
        print(result)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="group-llm-agent-operator")
    parser.add_argument("--lock-path", type=Path, default=_DEFAULT_LOCK)
    commands = parser.add_subparsers(required=True)

    approve = commands.add_parser("expression-approve")
    _catalog_digest_arguments(approve)
    approve.add_argument("--approval-reference", required=True)
    approve.add_argument("--semantic-id", action="append", required=True)
    approve.set_defaults(handler=_expression_approve)

    publish = commands.add_parser("expression-publish")
    _catalog_digest_arguments(publish)
    publish.add_argument("--owner-user-id", required=True)
    publish.add_argument("--sticker-set-name", required=True)
    publish.add_argument("--sticker-set-title", required=True)
    publish.add_argument("--mapping-output", type=Path, required=True)
    publish.set_defaults(handler=_expression_publish)

    attach = commands.add_parser("expression-attach")
    _catalog_digest_arguments(attach)
    attach.add_argument("--owner-user-id", required=True)
    attach.add_argument("--sticker-set-name", required=True)
    attach.add_argument("--verification-reference", required=True)
    attach.add_argument("--mapping-file", type=Path, required=True)
    attach.set_defaults(handler=_expression_attach)

    enable = commands.add_parser("expression-enable")
    _catalog_digest_arguments(enable)
    enable.add_argument("--activation-reference", required=True)
    enable.set_defaults(handler=_expression_enable)

    avatar_approve = commands.add_parser("avatar-approve")
    _catalog_digest_arguments(avatar_approve)
    avatar_approve.add_argument("--approval-reference", required=True)
    avatar_approve.add_argument("--avatar-id", action="append", required=True)
    avatar_approve.add_argument("--approved-sticker-catalog-sha256")
    avatar_approve.set_defaults(handler=_avatar_approve)

    avatar_apply = commands.add_parser("avatar-apply")
    _catalog_digest_arguments(avatar_apply)
    avatar_apply.add_argument("--avatar-id", required=True)
    avatar_apply.add_argument("--bot-user-id", required=True)
    avatar_apply.add_argument("--database", type=Path, required=True)
    avatar_apply.add_argument("--state-directory", type=Path, required=True)
    avatar_apply.add_argument("--requested-by", required=True)
    avatar_apply.add_argument("--reason-code", required=True)
    avatar_apply.set_defaults(handler=_avatar_apply)

    avatar_enable = commands.add_parser("avatar-enable-rotation")
    _catalog_digest_arguments(avatar_enable)
    avatar_enable.add_argument("--confirmation-reference", required=True)
    avatar_enable.set_defaults(handler=_avatar_enable_rotation)

    avatar_rotate = commands.add_parser("avatar-rotate")
    _catalog_digest_arguments(avatar_rotate)
    avatar_rotate.add_argument("--bot-user-id", required=True)
    avatar_rotate.add_argument("--database", type=Path, required=True)
    avatar_rotate.add_argument("--state-directory", type=Path, required=True)
    avatar_rotate.add_argument("--requested-by", required=True)
    avatar_rotate.set_defaults(handler=_avatar_rotate)
    return parser


def _catalog_digest_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)


def _expression_approve(args: argparse.Namespace) -> str:
    with operator_lock(args.lock_path):
        return approve_expression_catalog(
            args.catalog,
            expected_candidate_sha256=args.expected_sha256,
            approval_reference=args.approval_reference,
            approved_semantic_ids=frozenset(args.semantic_id),
        )


def _expression_publish(args: argparse.Namespace) -> str:
    with operator_lock(args.lock_path):
        catalog = load_expression_catalog(
            args.catalog,
            expected_sha256=args.expected_sha256,
            allowed_statuses=frozenset({"approved"}),
        )
        telegram, multipart = _telegram_clients()
        mappings = StickerPackPublisher(telegram=telegram, multipart=multipart).publish(
            catalog,
            request=StickerPublishRequest(
                owner_user_id=args.owner_user_id,
                sticker_set_name=args.sticker_set_name,
                sticker_set_title=args.sticker_set_title,
                approved_catalog_sha256=args.expected_sha256,
            ),
        )
        payload = {
            "schema_version": 1,
            "approved_catalog_sha256": args.expected_sha256,
            "sticker_set_name": args.sticker_set_name,
            "mappings": [item.__dict__ for item in mappings],
        }
        _write_private(args.mapping_output, canonical_json_bytes(payload))
        return f"mapping_count={len(mappings)}"


def _expression_attach(args: argparse.Namespace) -> str:
    raw = _mapping_file(args.mapping_file, args.expected_sha256, args.sticker_set_name)
    mappings = tuple(
        TelegramStickerMapping(
            semantic_id=_string(item, "semantic_id"),
            file_id=_string(item, "file_id"),
            file_unique_id=_string(item, "file_unique_id"),
        )
        for item in raw
    )
    with operator_lock(args.lock_path):
        return attach_telegram_mapping(
            args.catalog,
            expected_approved_sha256=args.expected_sha256,
            sticker_set_name=args.sticker_set_name,
            owner_user_id=args.owner_user_id,
            verification_reference=args.verification_reference,
            mappings=mappings,
        )


def _expression_enable(args: argparse.Namespace) -> str:
    with operator_lock(args.lock_path):
        return enable_expression_catalog(
            args.catalog,
            expected_telegram_ready_sha256=args.expected_sha256,
            activation_reference=args.activation_reference,
        )


def _avatar_approve(args: argparse.Namespace) -> str:
    with operator_lock(args.lock_path):
        return approve_avatar_catalog(
            args.catalog,
            expected_candidate_sha256=args.expected_sha256,
            approval_reference=args.approval_reference,
            approved_avatar_ids=frozenset(args.avatar_id),
            approved_sticker_catalog_sha256=args.approved_sticker_catalog_sha256,
        )


def _avatar_apply(args: argparse.Namespace) -> str:
    with operator_lock(args.lock_path):
        catalog = load_avatar_catalog(args.catalog, expected_sha256=args.expected_sha256)
        controller = _avatar_controller(args)
        return controller.apply(
            catalog,
            avatar_id=args.avatar_id,
            requested_by=args.requested_by,
            reason_code=args.reason_code,
        )


def _avatar_enable_rotation(args: argparse.Namespace) -> str:
    with operator_lock(args.lock_path):
        return enable_avatar_rotation(
            args.catalog,
            expected_approved_sha256=args.expected_sha256,
            confirmation_reference=args.confirmation_reference,
        )


def _avatar_rotate(args: argparse.Namespace) -> str:
    with operator_lock(args.lock_path):
        catalog = load_avatar_catalog(args.catalog, expected_sha256=args.expected_sha256)
        controller = _avatar_controller(args)
        candidate = controller.stable_mood_candidate(catalog)
        if candidate is None:
            return "rotation_status=ineligible"
        unique_id = controller.apply(
            catalog,
            avatar_id=candidate.avatar_id,
            requested_by=args.requested_by,
            reason_code="stable_global_mood",
        )
        return f"rotation_status=verified avatar_id={candidate.avatar_id} unique_id={unique_id}"


def _telegram_clients() -> tuple[TelegramBotApiClient, TelegramMultipartTransport]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("telegram_token_required")
    return TelegramBotApiClient(token), TelegramMultipartTransport(token=token)


def _avatar_controller(args: argparse.Namespace) -> AvatarController:
    telegram, multipart = _telegram_clients()
    database = SQLiteDatabase(args.database)
    database.initialize()
    return AvatarController(
        database=database,
        telegram=telegram,
        multipart=multipart,
        bot_user_id=args.bot_user_id,
        state_directory=args.state_directory,
    )


def _mapping_file(path: Path, expected_sha: str, set_name: str) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExpressionCatalogError("invalid_mapping_file") from error
    if (
        not isinstance(raw, dict)
        or raw.get("schema_version") != 1
        or raw.get("approved_catalog_sha256") != expected_sha
        or raw.get("sticker_set_name") != set_name
        or not isinstance(raw.get("mappings"), list)
        or canonical_json_bytes(raw) != path.read_bytes()
    ):
        raise ExpressionCatalogError("invalid_mapping_file")
    mappings = raw["mappings"]
    if not isinstance(mappings, list) or not all(isinstance(item, dict) for item in mappings):
        raise ExpressionCatalogError("invalid_mapping_file")
    return [dict(item) for item in mappings]


def _string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ExpressionCatalogError("invalid_mapping_file")
    return value


def _write_private(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())


if __name__ == "__main__":
    raise SystemExit(main())
