from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from group_llm_agent.events import PersonaSnapshot

_BUNDLE_FILES = {
    "manifest.json",
    "character.json",
    "examples.jsonl",
    "evaluation-cases.jsonl",
}
_MANIFEST_FIELDS_V1 = {
    "schema_version",
    "persona_id",
    "persona_version",
    "content_sha256",
    "requirements_commit",
    "confirmed_snapshot_ref",
    "evaluation_report_ref",
}
_MANIFEST_FIELDS_V2 = _MANIFEST_FIELDS_V1 | {"source_artifacts"}
_SOURCE_ARTIFACT_FIELDS = {"archive_name", "archive_sha256", "files"}
_SOURCE_FILE_FIELDS = {"source_name", "sha256"}
_SOURCE_FILES = {
    "character.json": "lezhi-persona-v2.json",
    "evaluation-cases.jsonl": "evaluation-cases.jsonl",
    "examples.jsonl": "examples.jsonl",
}
_CHARACTER_FIELDS_V1 = {
    "identity_and_stable_facts",
    "dramatic_engine",
    "core_traits",
    "voice_and_interaction_style",
    "relationship_stance",
    "preference_evolution",
    "situational_behavior",
    "negative_and_safety_rules",
    "attention_and_interest",
    "participation_and_silence_rules",
    "member_salience",
}
_CHARACTER_FIELDS_V2 = _CHARACTER_FIELDS_V1 | {
    "persona_meta",
    "behavior_priority",
    "conversational_impulses",
    "humor_engine",
    "state_and_continuity",
    "anti_assistant_defaults",
    "taste_and_bias",
    "behavioral_examples",
}
_TRIGGER_FIELDS_V1 = (
    "identity_and_stable_facts",
    "dramatic_engine",
    "attention_and_interest",
    "participation_and_silence_rules",
    "relationship_stance",
    "situational_behavior",
    "negative_and_safety_rules",
)
_RECOGNITION_FIELDS_V1 = (
    "identity_and_stable_facts",
    "dramatic_engine",
    "member_salience",
    "relationship_stance",
    "preference_evolution",
    "negative_and_safety_rules",
)
_TRIGGER_FIELDS_V2 = (
    "persona_meta",
    "behavior_priority",
    "attention_and_interest",
    "core_traits",
    "dramatic_engine",
    "taste_and_bias",
    "identity_and_stable_facts",
    "conversational_impulses",
    "humor_engine",
    "state_and_continuity",
    "anti_assistant_defaults",
    "relationship_stance",
    "participation_and_silence_rules",
    "situational_behavior",
    "negative_and_safety_rules",
)
_RECOGNITION_FIELDS_V2 = (
    "persona_meta",
    "behavior_priority",
    "core_traits",
    "dramatic_engine",
    "taste_and_bias",
    "identity_and_stable_facts",
    "humor_engine",
    "state_and_continuity",
    "member_salience",
    "preference_evolution",
    "relationship_stance",
    "negative_and_safety_rules",
)
_EXAMPLE_FIELDS = {
    "case_id",
    "scene",
    "expected_behavior",
    "forbidden_behavior",
}
_EVALUATION_FIELDS = {
    "case_id",
    "dimension",
    "pass_condition",
    "critical",
}
_SAFE_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_MAX_JSON_BYTES = 128_000
_MAX_JSONL_LINES = 128
_MAX_CHARACTER_BYTES = 64_000
_MAX_JSON_DEPTH = 12


class CharacterBundleError(RuntimeError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(f"character_bundle_error category={category}")


@dataclass(frozen=True)
class CompiledCharacterView:
    snapshot: PersonaSnapshot
    role: str
    policy_json: str
    examples_jsonl: tuple[str, ...]
    source_fields: tuple[str, ...]


@dataclass(frozen=True)
class CompiledCharacterViews:
    trigger: CompiledCharacterView
    recognition: CompiledCharacterView
    effector: CompiledCharacterView


@dataclass(frozen=True)
class CharacterBundle:
    snapshot: PersonaSnapshot
    schema_version: int
    requirements_commit: str
    confirmed_snapshot_ref: str
    evaluation_report_ref: str
    evaluation_cases_jsonl: tuple[str, ...]
    direct_address_terms: tuple[str, ...]
    views: CompiledCharacterViews


def load_character_bundle(
    path: Path,
    *,
    expected_sha256: str | None = None,
    expected_version: str | None = None,
) -> CharacterBundle:
    root = _safe_bundle_root(path)
    manifest_raw = _read_required_file(root / "manifest.json")
    manifest = _parse_json_object(manifest_raw, category="invalid_manifest")
    schema_version = _manifest_schema_version(manifest)
    manifest_fields = _MANIFEST_FIELDS_V1 if schema_version == 1 else _MANIFEST_FIELDS_V2
    _require_exact_fields(manifest, manifest_fields, category="invalid_manifest")
    if manifest_raw != _canonical_json_bytes(manifest):
        raise CharacterBundleError("noncanonical_manifest")
    _validate_manifest(manifest)

    character_raw = _read_required_file(root / "character.json")
    examples_raw = _read_required_file(root / "examples.jsonl")
    evaluation_raw = _read_required_file(root / "evaluation-cases.jsonl")
    digest = _content_digest(
        manifest=manifest,
        character_raw=character_raw,
        examples_raw=examples_raw,
        evaluation_raw=evaluation_raw,
    )
    if digest != manifest["content_sha256"]:
        raise CharacterBundleError("digest_mismatch")
    if expected_sha256 is not None and digest != expected_sha256:
        raise CharacterBundleError("unexpected_digest")
    if expected_version is not None and manifest["persona_version"] != expected_version:
        raise CharacterBundleError("unexpected_version")
    if schema_version == 2:
        _validate_source_artifacts(
            manifest,
            character_raw=character_raw,
            examples_raw=examples_raw,
            evaluation_raw=evaluation_raw,
        )

    character = _parse_json_object(character_raw, category="invalid_character")
    _validate_character(character, manifest=manifest, schema_version=schema_version)
    examples = _parse_jsonl(examples_raw, _EXAMPLE_FIELDS, category="invalid_examples")
    evaluation_cases = _parse_jsonl(
        evaluation_raw,
        _EVALUATION_FIELDS,
        category="invalid_evaluation_cases",
    )
    _validate_evaluation_coverage(
        examples,
        evaluation_cases,
        schema_version=schema_version,
    )

    snapshot = PersonaSnapshot(
        persona_id=str(manifest["persona_id"]),
        persona_version=str(manifest["persona_version"]),
        persona_digest=digest,
    )
    example_lines = tuple(_canonical_json(item) for item in examples)
    formal_name = _character_name(character, schema_version=schema_version)
    return CharacterBundle(
        snapshot=snapshot,
        schema_version=schema_version,
        requirements_commit=str(manifest["requirements_commit"]),
        confirmed_snapshot_ref=str(manifest["confirmed_snapshot_ref"]),
        evaluation_report_ref=str(manifest["evaluation_report_ref"]),
        evaluation_cases_jsonl=tuple(_canonical_json(item) for item in evaluation_cases),
        direct_address_terms=(formal_name,),
        views=_compile_views(
            snapshot,
            character,
            example_lines,
            schema_version=schema_version,
        ),
    )


def calculate_bundle_digest(path: Path) -> str:
    """Calculate the manifest digest for an authoring workflow.

    The bundle is still untrusted until ``load_character_bundle`` validates the
    manifest and all content.
    """

    root = _safe_bundle_root(path)
    manifest = _parse_json_object(
        _read_required_file(root / "manifest.json"),
        category="invalid_manifest",
    )
    schema_version = _manifest_schema_version(manifest)
    _require_exact_fields(
        manifest,
        _MANIFEST_FIELDS_V1 if schema_version == 1 else _MANIFEST_FIELDS_V2,
        category="invalid_manifest",
    )
    return _content_digest(
        manifest=manifest,
        character_raw=_read_required_file(root / "character.json"),
        examples_raw=_read_required_file(root / "examples.jsonl"),
        evaluation_raw=_read_required_file(root / "evaluation-cases.jsonl"),
    )


def _safe_bundle_root(path: Path) -> Path:
    if ".." in path.parts:
        raise CharacterBundleError("unsafe_path")
    try:
        root = path.resolve(strict=True)
    except (OSError, RuntimeError):
        raise CharacterBundleError("missing_bundle") from None
    if not root.is_dir() or path.is_symlink():
        raise CharacterBundleError("unsafe_path")
    try:
        names = {entry.name for entry in root.iterdir()}
    except OSError:
        raise CharacterBundleError("unreadable_bundle") from None
    if names != _BUNDLE_FILES:
        raise CharacterBundleError("unexpected_bundle_files")
    for name in _BUNDLE_FILES:
        item = root / name
        if item.is_symlink() or not item.is_file():
            raise CharacterBundleError("unsafe_path")
    return root


def _read_required_file(path: Path) -> bytes:
    try:
        size = path.stat().st_size
        if size <= 0 or size > _MAX_JSON_BYTES:
            raise CharacterBundleError("invalid_file_size")
        return path.read_bytes()
    except CharacterBundleError:
        raise
    except OSError:
        raise CharacterBundleError("unreadable_bundle") from None


def _parse_json_object(raw: bytes, *, category: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise CharacterBundleError(category) from None
    if not isinstance(value, dict):
        raise CharacterBundleError(category)
    return value


def _parse_jsonl(
    raw: bytes,
    fields: set[str],
    *,
    category: str,
) -> tuple[dict[str, Any], ...]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise CharacterBundleError(category) from None
    lines = text.splitlines()
    if not lines or len(lines) > _MAX_JSONL_LINES or not text.endswith("\n"):
        raise CharacterBundleError(category)
    values: list[dict[str, Any]] = []
    for line in lines:
        if not line or len(line.encode("utf-8")) > _MAX_JSON_BYTES:
            raise CharacterBundleError(category)
        try:
            value = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
        except (json.JSONDecodeError, ValueError):
            raise CharacterBundleError(category) from None
        if not isinstance(value, dict):
            raise CharacterBundleError(category)
        _require_exact_fields(value, fields, category=category)
        if line != _canonical_json(value):
            raise CharacterBundleError(category)
        values.append(value)
    return tuple(values)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _require_exact_fields(
    value: dict[str, Any],
    expected: set[str],
    *,
    category: str,
) -> None:
    if set(value) != expected:
        raise CharacterBundleError(category)


def _manifest_schema_version(manifest: dict[str, Any]) -> int:
    value = manifest.get("schema_version")
    if isinstance(value, bool) or not isinstance(value, int) or value not in {1, 2}:
        raise CharacterBundleError("unsupported_schema")
    return value


def _validate_manifest(manifest: dict[str, Any]) -> None:
    schema_version = _manifest_schema_version(manifest)
    for field in ("persona_id", "persona_version"):
        value = manifest[field]
        if not isinstance(value, str) or _SAFE_IDENTIFIER.fullmatch(value) is None:
            raise CharacterBundleError("invalid_manifest")
    digest = manifest["content_sha256"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise CharacterBundleError("invalid_manifest")
    commit = manifest["requirements_commit"]
    if not isinstance(commit, str) or _COMMIT_SHA.fullmatch(commit) is None:
        raise CharacterBundleError("invalid_manifest")
    for field in ("confirmed_snapshot_ref", "evaluation_report_ref"):
        value = manifest[field]
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise CharacterBundleError("missing_confirmation_reference")
    if schema_version == 2:
        _validate_source_artifact_shape(manifest["source_artifacts"])


def _validate_character(
    character: dict[str, Any],
    *,
    manifest: dict[str, Any],
    schema_version: int,
) -> None:
    expected = _CHARACTER_FIELDS_V1 if schema_version == 1 else _CHARACTER_FIELDS_V2
    _require_exact_fields(character, expected, category="invalid_character")
    if len(_canonical_json(character).encode("utf-8")) > _MAX_CHARACTER_BYTES:
        raise CharacterBundleError("invalid_character")
    if schema_version == 2:
        for value in character.values():
            if value in ({}, []) or not _valid_json_contract(value, depth=0):
                raise CharacterBundleError("invalid_character")
        meta = character["persona_meta"]
        if not isinstance(meta, dict) or set(meta) != {"id", "version", "name", "one_line"}:
            raise CharacterBundleError("invalid_character")
        if (
            meta["id"] != manifest["persona_id"]
            or f"{meta['id']}-v{meta['version']}" != manifest["persona_version"]
            or meta["name"] != character["identity_and_stable_facts"].get("name")
        ):
            raise CharacterBundleError("persona_identity_mismatch")
        _validate_character_name(meta["name"])
        return
    for field, value in character.items():
        if field in {"core_traits", "negative_and_safety_rules"}:
            if (
                not isinstance(value, list)
                or not value
                or len(value) > 64
                or not all(_is_nonempty_text(item, maximum=1_000) for item in value)
            ):
                raise CharacterBundleError("invalid_character")
        elif (
            not isinstance(value, dict)
            or not value
            or len(_canonical_json(value).encode("utf-8")) > 16_000
        ):
            raise CharacterBundleError("invalid_character")
    _validate_character_name(character["identity_and_stable_facts"].get("name"))


def _validate_character_name(name: Any) -> None:
    if (
        not _is_nonempty_text(name, maximum=64)
        or str(name) != str(name).strip()
        or any(unicodedata.category(character).startswith("C") for character in str(name))
    ):
        raise CharacterBundleError("invalid_character_name")


def _character_name(character: dict[str, Any], *, schema_version: int) -> str:
    if schema_version == 2:
        return str(character["persona_meta"]["name"])
    return str(character["identity_and_stable_facts"]["name"]).strip()


def _valid_json_contract(value: Any, *, depth: int) -> bool:
    if depth > _MAX_JSON_DEPTH:
        return False
    if value is None or isinstance(value, (bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, str):
        return bool(value.strip()) and len(value) <= 4_000
    if isinstance(value, list):
        return len(value) <= 128 and all(
            _valid_json_contract(item, depth=depth + 1) for item in value
        )
    if isinstance(value, dict):
        return len(value) <= 128 and all(
            isinstance(key, str)
            and bool(key)
            and len(key) <= 128
            and _valid_json_contract(item, depth=depth + 1)
            for key, item in value.items()
        )
    return False


def _validate_evaluation_coverage(
    examples: tuple[dict[str, Any], ...],
    evaluation_cases: tuple[dict[str, Any], ...],
    *,
    schema_version: int,
) -> None:
    example_ids: set[str] = set()
    for item in examples:
        case_id = item["case_id"]
        if (
            not _is_nonempty_text(case_id, maximum=64)
            or case_id in example_ids
            or not all(
                _is_nonempty_text(item[field], maximum=4_000)
                for field in ("scene", "expected_behavior", "forbidden_behavior")
            )
        ):
            raise CharacterBundleError("invalid_examples")
        example_ids.add(case_id)

    evaluation_ids: set[str] = set()
    for item in evaluation_cases:
        case_id = item["case_id"]
        if (
            not _is_nonempty_text(case_id, maximum=64)
            or case_id in evaluation_ids
            or not _is_nonempty_text(item["dimension"], maximum=64)
            or not _is_nonempty_text(item["pass_condition"], maximum=4_000)
            or not isinstance(item["critical"], bool)
        ):
            raise CharacterBundleError("invalid_evaluation_cases")
        evaluation_ids.add(case_id)
    if schema_version == 2:
        expected = {f"CB-EVAL-{index:03d}" for index in range(1, 38)}
        if example_ids != expected or evaluation_ids != expected:
            raise CharacterBundleError("invalid_v2_evaluation_coverage")
        if not all("8/10" in str(item["pass_condition"]) for item in evaluation_cases):
            raise CharacterBundleError("invalid_v2_evaluation_threshold")
    elif not example_ids.issubset(evaluation_ids):
        raise CharacterBundleError("missing_evaluation_coverage")


def _compile_views(
    snapshot: PersonaSnapshot,
    character: dict[str, Any],
    examples_jsonl: tuple[str, ...],
    *,
    schema_version: int,
) -> CompiledCharacterViews:
    trigger_fields = _TRIGGER_FIELDS_V1 if schema_version == 1 else _TRIGGER_FIELDS_V2
    recognition_fields = _RECOGNITION_FIELDS_V1 if schema_version == 1 else _RECOGNITION_FIELDS_V2
    effector_fields = tuple(character)
    return CompiledCharacterViews(
        trigger=CompiledCharacterView(
            snapshot=snapshot,
            role="trigger",
            policy_json=_canonical_json({field: character[field] for field in trigger_fields}),
            examples_jsonl=(),
            source_fields=trigger_fields,
        ),
        recognition=CompiledCharacterView(
            snapshot=snapshot,
            role="recognition",
            policy_json=_canonical_json({field: character[field] for field in recognition_fields}),
            examples_jsonl=(),
            source_fields=recognition_fields,
        ),
        effector=CompiledCharacterView(
            snapshot=snapshot,
            role="effector",
            policy_json=_canonical_json(character),
            examples_jsonl=examples_jsonl,
            source_fields=effector_fields,
        ),
    )


def _validate_source_artifact_shape(value: Any) -> None:
    if not isinstance(value, dict):
        raise CharacterBundleError("invalid_source_artifacts")
    _require_exact_fields(value, _SOURCE_ARTIFACT_FIELDS, category="invalid_source_artifacts")
    if (
        value["archive_name"] != "lezhi-persona-v2-bundle.zip"
        or not _is_sha256(value["archive_sha256"])
        or not isinstance(value["files"], dict)
        or set(value["files"]) != set(_SOURCE_FILES)
    ):
        raise CharacterBundleError("invalid_source_artifacts")
    for production_name, source_name in _SOURCE_FILES.items():
        item = value["files"].get(production_name)
        if not isinstance(item, dict):
            raise CharacterBundleError("invalid_source_artifacts")
        _require_exact_fields(item, _SOURCE_FILE_FIELDS, category="invalid_source_artifacts")
        if item["source_name"] != source_name or not _is_sha256(item["sha256"]):
            raise CharacterBundleError("invalid_source_artifacts")


def _validate_source_artifacts(
    manifest: dict[str, Any],
    *,
    character_raw: bytes,
    examples_raw: bytes,
    evaluation_raw: bytes,
) -> None:
    files = manifest["source_artifacts"]["files"]
    payloads = {
        "character.json": character_raw,
        "examples.jsonl": examples_raw,
        "evaluation-cases.jsonl": evaluation_raw,
    }
    for name, payload in payloads.items():
        if hashlib.sha256(payload).hexdigest() != files[name]["sha256"]:
            raise CharacterBundleError("source_digest_mismatch")


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _content_digest(
    *,
    manifest: dict[str, Any],
    character_raw: bytes,
    examples_raw: bytes,
    evaluation_raw: bytes,
) -> str:
    manifest_without_digest = {
        key: value for key, value in manifest.items() if key != "content_sha256"
    }
    chunks = (
        ("manifest.json", _canonical_json_bytes(manifest_without_digest)),
        ("character.json", character_raw),
        ("examples.jsonl", examples_raw),
        ("evaluation-cases.jsonl", evaluation_raw),
    )
    digest = hashlib.sha256()
    for name, payload in chunks:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical_json_bytes(value: Any) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _is_nonempty_text(value: Any, *, maximum: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum
