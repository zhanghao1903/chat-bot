from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from group_llm_agent.expression import (
    ExpressionCatalogError,
    canonical_json_bytes,
    file_sha256,
    load_expression_catalog,
)


@dataclass(frozen=True)
class TelegramStickerMapping:
    semantic_id: str
    file_id: str
    file_unique_id: str


def approve_expression_catalog(
    path: Path,
    *,
    expected_candidate_sha256: str,
    approval_reference: str,
    approved_semantic_ids: frozenset[str],
) -> str:
    if not approval_reference.startswith("user-confirmed:"):
        raise ExpressionCatalogError("explicit_user_confirmation_required")
    catalog = load_expression_catalog(
        path,
        expected_sha256=expected_candidate_sha256,
        allowed_statuses=frozenset({"candidate"}),
    )
    available = {entry.semantic_id for entry in catalog.entries}
    if not approved_semantic_ids or not approved_semantic_ids <= available:
        raise ExpressionCatalogError("invalid_approved_subset")
    raw = _read_raw(path)
    raw["status"] = "approved"
    raw["approval"] = {
        "reference": approval_reference,
        "candidate_sha256": expected_candidate_sha256,
        "approved_semantic_ids": sorted(approved_semantic_ids),
    }
    for entry in raw["entries"]:
        entry["status"] = (
            "approved" if entry["semantic_id"] in approved_semantic_ids else "candidate"
        )
    _atomic_write(path, canonical_json_bytes(raw))
    return file_sha256(path)


def attach_telegram_mapping(
    path: Path,
    *,
    expected_approved_sha256: str,
    sticker_set_name: str,
    owner_user_id: str,
    verification_reference: str,
    mappings: tuple[TelegramStickerMapping, ...],
) -> str:
    catalog = load_expression_catalog(
        path,
        expected_sha256=expected_approved_sha256,
        allowed_statuses=frozenset({"approved"}),
    )
    approved_ids = {entry.semantic_id for entry in catalog.entries if entry.status == "approved"}
    mapping_by_id = {item.semantic_id: item for item in mappings}
    if (
        len(mapping_by_id) != len(mappings)
        or set(mapping_by_id) != approved_ids
        or not verification_reference.startswith("telegram-smoke:")
    ):
        raise ExpressionCatalogError("invalid_telegram_mapping_proof")
    raw = _read_raw(path)
    raw["status"] = "telegram_ready"
    raw["telegram_mapping"] = {
        "sticker_set_name": sticker_set_name,
        "owner_user_id": owner_user_id,
        "verification_reference": verification_reference,
        "approved_catalog_sha256": expected_approved_sha256,
    }
    for entry in raw["entries"]:
        mapping = mapping_by_id.get(entry["semantic_id"])
        if mapping is None:
            continue
        entry["status"] = "telegram_ready"
        entry["telegram_mapping"] = {
            "file_id": mapping.file_id,
            "file_unique_id": mapping.file_unique_id,
        }
    _atomic_write(path, canonical_json_bytes(raw))
    return file_sha256(path)


def enable_expression_catalog(
    path: Path,
    *,
    expected_telegram_ready_sha256: str,
    activation_reference: str,
) -> str:
    if not activation_reference.startswith("user-confirmed-enable:"):
        raise ExpressionCatalogError("explicit_enable_confirmation_required")
    load_expression_catalog(
        path,
        expected_sha256=expected_telegram_ready_sha256,
        allowed_statuses=frozenset({"telegram_ready"}),
    )
    raw = _read_raw(path)
    raw["status"] = "enabled"
    raw["telegram_mapping"]["activation_reference"] = activation_reference
    raw["telegram_mapping"]["telegram_ready_sha256"] = expected_telegram_ready_sha256
    for entry in raw["entries"]:
        if entry["status"] == "telegram_ready":
            entry["status"] = "enabled"
    _atomic_write(path, canonical_json_bytes(raw))
    return file_sha256(path)


def _read_raw(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExpressionCatalogError("invalid_catalog_json") from error
    if not isinstance(raw, dict):
        raise ExpressionCatalogError("invalid_catalog_json")
    return raw


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, prefix=".catalog-", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
