from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_CATALOG_SCHEMA_VERSION = 1
_CATALOG_STATUSES = {"candidate", "approved", "telegram_ready", "enabled"}
_RUNTIME_STATUSES = {"approved", "telegram_ready", "enabled"}
_RELATIONSHIP_LEVELS = {"public", "familiar", "close"}


class ExpressionCatalogError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ExpressionEntry:
    semantic_id: str
    source_sheet: str
    source_row: int
    source_column: int
    visible_text: str
    action: str
    emotion: str
    interaction_intent: str
    use_when: tuple[str, ...]
    avoid_when: tuple[str, ...]
    minimum_relationship: str
    emoji: str
    master_path: str
    master_sha256: str
    telegram_path: str
    telegram_sha256: str
    status: str
    telegram_file_id: str | None
    telegram_file_unique_id: str | None


@dataclass(frozen=True)
class ExpressionCatalog:
    catalog_id: str
    catalog_version: str
    status: str
    persona_id: str
    persona_version: str
    persona_digest: str
    digest: str
    entries: tuple[ExpressionEntry, ...]
    path: Path

    def entry(self, semantic_id: str) -> ExpressionEntry | None:
        return next((entry for entry in self.entries if entry.semantic_id == semantic_id), None)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def load_expression_catalog(
    path: Path,
    *,
    expected_sha256: str,
    allowed_statuses: frozenset[str] | None = None,
    verify_assets: bool = True,
) -> ExpressionCatalog:
    if not _is_digest(expected_sha256):
        raise ExpressionCatalogError("invalid_expected_digest")
    actual_digest = file_sha256(path)
    if actual_digest != expected_sha256:
        raise ExpressionCatalogError("catalog_digest_mismatch")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExpressionCatalogError("invalid_catalog_json") from exc
    if not isinstance(raw, dict) or canonical_json_bytes(raw) != path.read_bytes():
        raise ExpressionCatalogError("catalog_not_canonical")
    if raw.get("schema_version") != _CATALOG_SCHEMA_VERSION:
        raise ExpressionCatalogError("unsupported_catalog_schema")
    status = _required_string(raw, "status")
    statuses = allowed_statuses if allowed_statuses is not None else frozenset(_RUNTIME_STATUSES)
    if status not in _CATALOG_STATUSES or status not in statuses:
        raise ExpressionCatalogError("catalog_status_not_allowed")
    if raw.get("approval") is not None and status == "candidate":
        raise ExpressionCatalogError("candidate_has_approval")
    if raw.get("telegram_mapping") is not None and status in {"candidate", "approved"}:
        raise ExpressionCatalogError("catalog_mapping_not_allowed")

    raw_entries = raw.get("entries")
    if not isinstance(raw_entries, list) or len(raw_entries) != 48:
        raise ExpressionCatalogError("catalog_entry_count")
    entries = tuple(_parse_entry(item) for item in raw_entries)
    semantic_ids = {entry.semantic_id for entry in entries}
    coordinates = {(entry.source_sheet, entry.source_row, entry.source_column) for entry in entries}
    if len(semantic_ids) != 48:
        raise ExpressionCatalogError("duplicate_semantic_id")
    if coordinates != {
        (sheet, row, column)
        for sheet in ("A", "B", "C")
        for row in range(1, 5)
        for column in range(1, 5)
    }:
        raise ExpressionCatalogError("invalid_source_coordinates")
    if verify_assets:
        _verify_entry_assets(path.parent, entries)

    return ExpressionCatalog(
        catalog_id=_required_string(raw, "catalog_id"),
        catalog_version=_required_string(raw, "catalog_version"),
        status=status,
        persona_id=_required_string(raw, "persona_id"),
        persona_version=_required_string(raw, "persona_version"),
        persona_digest=_required_digest(raw, "persona_digest"),
        digest=actual_digest,
        entries=entries,
        path=path,
    )


def validate_runtime_selection(
    catalog: ExpressionCatalog,
    *,
    semantic_id: str,
    persona_version: str,
    persona_digest: str,
    expected_catalog_version: str,
    expected_catalog_digest: str,
) -> ExpressionEntry:
    if catalog.status != "enabled":
        raise ExpressionCatalogError("catalog_not_enabled")
    if catalog.persona_version != persona_version or catalog.persona_digest != persona_digest:
        raise ExpressionCatalogError("persona_snapshot_mismatch")
    if (
        catalog.catalog_version != expected_catalog_version
        or catalog.digest != expected_catalog_digest
    ):
        raise ExpressionCatalogError("catalog_snapshot_mismatch")
    entry = catalog.entry(semantic_id)
    if entry is None or entry.status != "enabled":
        raise ExpressionCatalogError("expression_not_enabled")
    if not entry.telegram_file_id or not entry.telegram_file_unique_id:
        raise ExpressionCatalogError("expression_mapping_missing")
    return entry


def _parse_entry(raw: object) -> ExpressionEntry:
    if not isinstance(raw, dict):
        raise ExpressionCatalogError("invalid_catalog_entry")
    source = raw.get("source")
    assets = raw.get("assets")
    semantics = raw.get("semantics")
    mapping = raw.get("telegram_mapping")
    if (
        not isinstance(source, dict)
        or not isinstance(assets, dict)
        or not isinstance(semantics, dict)
    ):
        raise ExpressionCatalogError("invalid_catalog_entry")
    if mapping is not None and not isinstance(mapping, dict):
        raise ExpressionCatalogError("invalid_entry_mapping")
    relationship = _required_string(semantics, "minimum_relationship")
    if relationship not in _RELATIONSHIP_LEVELS:
        raise ExpressionCatalogError("invalid_relationship_level")
    status = _required_string(raw, "status")
    if status not in _CATALOG_STATUSES:
        raise ExpressionCatalogError("invalid_entry_status")
    sheet = _required_string(source, "sheet")
    row = _required_bounded_integer(source, "row", 1, 4)
    column = _required_bounded_integer(source, "column", 1, 4)
    return ExpressionEntry(
        semantic_id=_required_string(raw, "semantic_id"),
        source_sheet=sheet,
        source_row=row,
        source_column=column,
        visible_text=_required_string(raw, "visible_text"),
        action=_required_string(semantics, "action"),
        emotion=_required_string(semantics, "emotion"),
        interaction_intent=_required_string(semantics, "interaction_intent"),
        use_when=_required_string_tuple(semantics, "use_when"),
        avoid_when=_required_string_tuple(semantics, "avoid_when"),
        minimum_relationship=relationship,
        emoji=_required_string(semantics, "emoji"),
        master_path=_required_string(assets, "master_path"),
        master_sha256=_required_digest(assets, "master_sha256"),
        telegram_path=_required_string(assets, "telegram_path"),
        telegram_sha256=_required_digest(assets, "telegram_sha256"),
        status=status,
        telegram_file_id=(
            _required_string(mapping, "file_id") if isinstance(mapping, dict) else None
        ),
        telegram_file_unique_id=(
            _required_string(mapping, "file_unique_id") if isinstance(mapping, dict) else None
        ),
    )


def _verify_entry_assets(root: Path, entries: tuple[ExpressionEntry, ...]) -> None:
    root = root.resolve()
    for entry in entries:
        for relative, expected in (
            (entry.master_path, entry.master_sha256),
            (entry.telegram_path, entry.telegram_sha256),
        ):
            target = (root / relative).resolve()
            if root not in target.parents or not target.is_file():
                raise ExpressionCatalogError("catalog_asset_path_invalid")
            if file_sha256(target) != expected:
                raise ExpressionCatalogError("catalog_asset_digest_mismatch")


def _required_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ExpressionCatalogError(f"invalid_{key}")
    return value


def _required_digest(raw: dict[str, Any], key: str) -> str:
    value = _required_string(raw, key)
    if not _is_digest(value):
        raise ExpressionCatalogError(f"invalid_{key}")
    return value


def _required_bounded_integer(raw: dict[str, Any], key: str, minimum: int, maximum: int) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ExpressionCatalogError(f"invalid_{key}")
    return value


def _required_string_tuple(raw: dict[str, Any], key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise ExpressionCatalogError(f"invalid_{key}")
    return tuple(value)


def _is_digest(value: str) -> bool:
    return (
        len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )
