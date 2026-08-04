from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import uuid4

from group_llm_agent.database import SQLiteDatabase
from group_llm_agent.expression import (
    ExpressionCatalogError,
    canonical_json_bytes,
    file_sha256,
)
from group_llm_agent.platforms.telegram import TelegramApiError, TelegramBotApiClient
from group_llm_agent.telegram_multipart import TelegramMultipartTransport

APPROVED_DEFAULT_AVATAR_CATALOG_SHA256 = (
    "b871161e68c18115893d7aea932dabf1e9101d40278d6ce9168a6eb3735d405a"
)
APPROVED_DEFAULT_AVATAR_IMAGE_SHA256 = (
    "fd7ec0efafb9dc1e36856461228cecbf7467548c7628454fe2022f7ad607badf"
)
DEFAULT_AVATAR_ID = "lezhi-default"
_AVATAR_API_METHOD = "setMyProfilePhoto"


@dataclass(frozen=True)
class AvatarApplyResult:
    operation_id: str
    status: str


@dataclass(frozen=True)
class AvatarCandidate:
    avatar_id: str
    image_path: str
    image_sha256: str
    circle_preview_path: str
    circle_preview_sha256: str
    source: str
    allowed_moods: tuple[str, ...]
    disabled_when: tuple[str, ...]
    status: str
    depends_on_sticker_approval: bool


@dataclass(frozen=True)
class AvatarCatalog:
    catalog_id: str
    catalog_version: str
    status: str
    persona_id: str
    persona_version: str
    persona_digest: str
    default_avatar_id: str
    automatic_rotation_enabled: bool
    cooldown_hours: int
    max_changes_7d: int
    digest: str
    candidates: tuple[AvatarCandidate, ...]
    path: Path

    def candidate(self, avatar_id: str) -> AvatarCandidate | None:
        return next((item for item in self.candidates if item.avatar_id == avatar_id), None)


def load_avatar_catalog(
    path: Path,
    *,
    expected_sha256: str,
    allowed_statuses: frozenset[str] = frozenset({"approved", "enabled"}),
) -> AvatarCatalog:
    if file_sha256(path) != expected_sha256:
        raise ExpressionCatalogError("avatar_catalog_digest_mismatch")
    raw = _read_raw(path)
    if canonical_json_bytes(raw) != path.read_bytes() or raw.get("schema_version") != 1:
        raise ExpressionCatalogError("invalid_avatar_catalog")
    status = _required_string(raw, "status")
    if status not in allowed_statuses:
        raise ExpressionCatalogError("avatar_catalog_status_not_allowed")
    rotation = raw.get("automatic_rotation")
    candidates_raw = raw.get("candidates")
    if not isinstance(rotation, dict) or not isinstance(candidates_raw, list):
        raise ExpressionCatalogError("invalid_avatar_catalog")
    candidates = tuple(_parse_candidate(item) for item in candidates_raw)
    ids = {item.avatar_id for item in candidates}
    default_avatar_id = _required_string(raw, "default_avatar_id")
    if len(ids) != len(candidates) or default_avatar_id not in ids:
        raise ExpressionCatalogError("invalid_avatar_candidates")
    _verify_avatar_assets(path.parent, candidates)
    cooldown = rotation.get("cooldown_hours")
    maximum = rotation.get("max_changes_7d")
    enabled = rotation.get("enabled")
    if (
        not isinstance(cooldown, int)
        or isinstance(cooldown, bool)
        or cooldown < 72
        or not isinstance(maximum, int)
        or isinstance(maximum, bool)
        or not 0 < maximum <= 2
        or not isinstance(enabled, bool)
    ):
        raise ExpressionCatalogError("invalid_avatar_rotation_policy")
    return AvatarCatalog(
        catalog_id=_required_string(raw, "catalog_id"),
        catalog_version=_required_string(raw, "catalog_version"),
        status=status,
        persona_id=_required_string(raw, "persona_id"),
        persona_version=_required_string(raw, "persona_version"),
        persona_digest=_required_string(raw, "persona_digest"),
        default_avatar_id=default_avatar_id,
        automatic_rotation_enabled=enabled,
        cooldown_hours=cooldown,
        max_changes_7d=maximum,
        digest=expected_sha256,
        candidates=candidates,
        path=path,
    )


def approve_avatar_catalog(
    path: Path,
    *,
    expected_candidate_sha256: str,
    approval_reference: str,
    approved_avatar_ids: frozenset[str],
    approved_sticker_catalog_sha256: str | None = None,
) -> str:
    if not approval_reference.startswith("user-confirmed-avatar:"):
        raise ExpressionCatalogError("explicit_avatar_confirmation_required")
    catalog = load_avatar_catalog(
        path,
        expected_sha256=expected_candidate_sha256,
        allowed_statuses=frozenset({"candidate"}),
    )
    available = {item.avatar_id for item in catalog.candidates}
    if catalog.default_avatar_id not in approved_avatar_ids or not approved_avatar_ids <= available:
        raise ExpressionCatalogError("invalid_approved_avatar_subset")
    approved = [item for item in catalog.candidates if item.avatar_id in approved_avatar_ids]
    if (
        any(item.depends_on_sticker_approval for item in approved)
        and not approved_sticker_catalog_sha256
    ):
        raise ExpressionCatalogError("sticker_approval_required")
    raw = _read_raw(path)
    raw["status"] = "approved"
    raw["approval"] = {
        "reference": approval_reference,
        "candidate_sha256": expected_candidate_sha256,
        "approved_avatar_ids": sorted(approved_avatar_ids),
        "approved_sticker_catalog_sha256": approved_sticker_catalog_sha256,
    }
    for candidate in raw["candidates"]:
        candidate["status"] = (
            "approved" if candidate["avatar_id"] in approved_avatar_ids else "candidate"
        )
        if candidate["status"] == "approved":
            candidate["approval"] = {"reference": approval_reference}
    _atomic_write(path, canonical_json_bytes(raw))
    return file_sha256(path)


def enable_avatar_rotation(
    path: Path,
    *,
    expected_approved_sha256: str,
    confirmation_reference: str,
) -> str:
    if not confirmation_reference.startswith("user-confirmed-avatar-rotation:"):
        raise ExpressionCatalogError("explicit_rotation_confirmation_required")
    load_avatar_catalog(
        path,
        expected_sha256=expected_approved_sha256,
        allowed_statuses=frozenset({"approved"}),
    )
    raw = _read_raw(path)
    raw["status"] = "enabled"
    raw["automatic_rotation"]["enabled"] = True
    raw["automatic_rotation"]["confirmation_reference"] = confirmation_reference
    for candidate in raw["candidates"]:
        if candidate["status"] == "approved":
            candidate["status"] = "enabled"
    _atomic_write(path, canonical_json_bytes(raw))
    return file_sha256(path)


class AvatarController:
    def __init__(
        self,
        *,
        database: SQLiteDatabase,
        telegram: TelegramBotApiClient,
        multipart: TelegramMultipartTransport,
        bot_user_id: str,
        state_directory: Path | None = None,
        approved_catalog_digest: str = APPROVED_DEFAULT_AVATAR_CATALOG_SHA256,
    ) -> None:
        self.database = database
        self.telegram = telegram
        self.multipart = multipart
        self.bot_user_id = bot_user_id
        self.state_directory = state_directory
        self.approved_catalog_digest = approved_catalog_digest

    def stable_mood_candidate(
        self,
        catalog: AvatarCatalog,
        *,
        now: datetime | None = None,
    ) -> AvatarCandidate | None:
        current = now or datetime.now(UTC)
        if not catalog.automatic_rotation_enabled or catalog.status != "enabled":
            return None
        if not self._has_verified_default_baseline(catalog):
            return None
        observations = self._recent_moods(current - timedelta(days=7))
        if len(observations) < 3:
            return None
        latest_window = observations[-8:]
        scope_counts = {scope_count for _, _, _, _, scope_count in latest_window}
        if len(scope_counts) != 1 or next(iter(scope_counts)) < 2:
            return None
        counts = Counter(mood for mood, _, _, _, _ in latest_window)
        mood, count = counts.most_common(1)[0]
        matching = [item for item in latest_window if item[0] == mood]
        matching_times = [created for _, created, _, _, _ in matching]
        if count < 3 or count / len(latest_window) < 0.7:
            return None
        if len({chat_id for _, _, chat_id, _, _ in matching}) < 2:
            return None
        if len({member_user_id for _, _, _, member_user_id, _ in matching}) < 2:
            return None
        if max(matching_times) - min(matching_times) < timedelta(hours=2):
            return None
        if not self._cooldown_allows(catalog, current):
            return None
        return next(
            (
                item
                for item in catalog.candidates
                if item.status == "enabled" and mood in item.allowed_moods
            ),
            None,
        )

    def apply(
        self,
        catalog: AvatarCatalog,
        *,
        avatar_id: str,
        requested_by: str,
        reason_code: str,
        authorization_reference: str,
    ) -> AvatarApplyResult:
        if catalog.digest != self.approved_catalog_digest:
            raise ExpressionCatalogError("avatar_catalog_digest_mismatch")
        if avatar_id != DEFAULT_AVATAR_ID or catalog.default_avatar_id != DEFAULT_AVATAR_ID:
            raise ExpressionCatalogError("only_default_avatar_authorized")
        if not authorization_reference.startswith("user-confirmed-avatar-apply:"):
            raise ExpressionCatalogError("explicit_avatar_apply_authorization_required")
        candidate = catalog.candidate(avatar_id)
        if candidate is None or candidate.status not in {"approved", "enabled"}:
            raise ExpressionCatalogError("avatar_not_approved")
        if candidate.image_sha256 != APPROVED_DEFAULT_AVATAR_IMAGE_SHA256:
            raise ExpressionCatalogError("avatar_asset_digest_mismatch")
        image_path = (catalog.path.parent / candidate.image_path).resolve()
        if file_sha256(image_path) != candidate.image_sha256:
            raise ExpressionCatalogError("avatar_asset_digest_mismatch")
        operation_id = f"avatar-{uuid4().hex}"
        audit_id = self._start_audit(
            catalog=catalog,
            operation_id=operation_id,
            requested_avatar_id=avatar_id,
            reason_code=reason_code,
            requested_by=requested_by,
            authorization_reference=authorization_reference,
        )
        try:
            identity = self.telegram.get_me()
            identity_id = identity.get("id")
            if (
                isinstance(identity_id, bool)
                or not isinstance(identity_id, (int, str))
                or str(identity_id) != self.bot_user_id
                or identity.get("is_bot") is not True
            ):
                raise TelegramApiError("getMe", "invalid_identity")
            self.multipart.set_static_profile_photo(jpeg=image_path.read_bytes())
        except BaseException as error:
            status = _avatar_failure_status(error)
            self._finish_audit(
                audit_id,
                platform_status=status,
                error_code=_safe_avatar_error_code(error),
            )
            raise
        self._finish_audit(
            audit_id,
            platform_status="success",
            error_code=None,
        )
        return AvatarApplyResult(operation_id=operation_id, status="success")

    def _recent_moods(self, since: datetime) -> list[tuple[str, datetime, str, str, int]]:
        connection = self.database.connect()
        try:
            rows = connection.execute(
                """
                SELECT mood_code, created_at, chat_id, member_user_id, bot_scope_count
                FROM persona_mood_observations
                WHERE bot_user_id = ? AND created_at >= ?
                    AND chat_id IS NOT NULL AND member_user_id IS NOT NULL
                ORDER BY created_at
                """,
                (self.bot_user_id, since.isoformat()),
            ).fetchall()
        finally:
            connection.close()
        return [
            (
                str(row["mood_code"]),
                datetime.fromisoformat(row["created_at"]),
                str(row["chat_id"]),
                str(row["member_user_id"]),
                int(row["bot_scope_count"]),
            )
            for row in rows
        ]

    def _has_verified_default_baseline(self, catalog: AvatarCatalog) -> bool:
        default = catalog.candidate(catalog.default_avatar_id)
        if default is None:
            return False
        connection = self.database.connect()
        try:
            row = connection.execute(
                """
                SELECT 1 FROM avatar_change_audit
                WHERE bot_user_id = ?
                    AND avatar_catalog_version = ?
                    AND requested_avatar_id = ?
                    AND requested_image_sha256 = ?
                    AND platform_status IN ('verified', 'success')
                LIMIT 1
                """,
                (
                    self.bot_user_id,
                    catalog.catalog_version,
                    catalog.default_avatar_id,
                    default.image_sha256,
                ),
            ).fetchone()
        finally:
            connection.close()
        return row is not None

    def _cooldown_allows(self, catalog: AvatarCatalog, now: datetime) -> bool:
        connection = self.database.connect()
        try:
            rows = connection.execute(
                """
                SELECT created_at FROM avatar_change_audit
                WHERE bot_user_id = ? AND platform_status IN ('verified', 'success')
                ORDER BY created_at DESC
                """,
                (self.bot_user_id,),
            ).fetchall()
        finally:
            connection.close()
        changes = [datetime.fromisoformat(row["created_at"]) for row in rows]
        if changes and now - changes[0] < timedelta(hours=catalog.cooldown_hours):
            return False
        return sum(item >= now - timedelta(days=7) for item in changes) < catalog.max_changes_7d

    def _start_audit(
        self,
        *,
        catalog: AvatarCatalog,
        operation_id: str,
        requested_avatar_id: str,
        reason_code: str,
        requested_by: str,
        authorization_reference: str,
    ) -> int:
        now = datetime.now(UTC).isoformat()
        requested = catalog.candidate(requested_avatar_id)
        if requested is None:
            raise ExpressionCatalogError("avatar_not_approved")
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO avatar_change_audit (
                    operation_id, api_method, authorization_reference,
                    bot_user_id, avatar_catalog_version, avatar_catalog_digest,
                    previous_avatar_id, requested_avatar_id, requested_image_sha256,
                    reason_code,
                    cooldown_status, requested_by, platform_status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, 'eligible', ?, 'applying', ?, ?)
                """,
                (
                    operation_id,
                    _AVATAR_API_METHOD,
                    authorization_reference,
                    self.bot_user_id,
                    catalog.catalog_version,
                    catalog.digest,
                    requested_avatar_id,
                    requested.image_sha256,
                    reason_code,
                    requested_by,
                    now,
                    now,
                ),
            )
            assert cursor.lastrowid is not None
            return int(cursor.lastrowid)

    def _finish_audit(
        self,
        audit_id: int,
        *,
        platform_status: str,
        error_code: str | None,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE avatar_change_audit
                SET platform_status = ?, error_code = ?, rollback_status = NULL, updated_at = ?
                WHERE id = ?
                """,
                (
                    platform_status,
                    error_code,
                    datetime.now(UTC).isoformat(),
                    audit_id,
                ),
            )


def _avatar_failure_status(error: BaseException) -> str:
    if not isinstance(error, TelegramApiError):
        return "uncertain"
    if error.category in {
        "timeout",
        "transport_error",
        "invalid_json",
        "invalid_response",
        "invalid_result",
    }:
        return "uncertain"
    if error.category in {"http_error", "api_error"} and (
        error.status_code is None or error.status_code >= 500
    ):
        return "uncertain"
    return "failed"


def _safe_avatar_error_code(error: BaseException) -> str:
    if isinstance(error, TelegramApiError):
        status = f"_{error.status_code}" if error.status_code is not None else ""
        return f"{error.method}_{error.category}{status}"
    return type(error).__name__


def _parse_candidate(raw: object) -> AvatarCandidate:
    if not isinstance(raw, dict):
        raise ExpressionCatalogError("invalid_avatar_candidate")
    return AvatarCandidate(
        avatar_id=_required_string(raw, "avatar_id"),
        image_path=_required_string(raw, "image_path"),
        image_sha256=_required_string(raw, "image_sha256"),
        circle_preview_path=_required_string(raw, "circle_preview_path"),
        circle_preview_sha256=_required_string(raw, "circle_preview_sha256"),
        source=_required_string(raw, "source"),
        allowed_moods=_string_tuple(raw, "allowed_moods"),
        disabled_when=_string_tuple(raw, "disabled_when"),
        status=_required_string(raw, "status"),
        depends_on_sticker_approval=raw.get("depends_on_sticker_approval") is True,
    )


def _verify_avatar_assets(root: Path, candidates: tuple[AvatarCandidate, ...]) -> None:
    resolved_root = root.resolve()
    for candidate in candidates:
        for relative, expected in (
            (candidate.image_path, candidate.image_sha256),
            (candidate.circle_preview_path, candidate.circle_preview_sha256),
        ):
            target = (resolved_root / relative).resolve()
            if resolved_root not in target.parents or not target.is_file():
                raise ExpressionCatalogError("avatar_asset_path_invalid")
            if file_sha256(target) != expected:
                raise ExpressionCatalogError("avatar_asset_digest_mismatch")


def _read_raw(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExpressionCatalogError("invalid_avatar_catalog") from error
    if not isinstance(raw, dict):
        raise ExpressionCatalogError("invalid_avatar_catalog")
    return raw


def _required_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ExpressionCatalogError(f"invalid_avatar_{key}")
    return value


def _string_tuple(raw: dict[str, Any], key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise ExpressionCatalogError(f"invalid_avatar_{key}")
    return tuple(value)


def _atomic_write(path: Path, content: bytes) -> None:
    with NamedTemporaryFile(dir=path.parent, prefix=".avatar-", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
