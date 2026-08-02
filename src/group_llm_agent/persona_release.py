from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from group_llm_agent.persona import (
    CharacterBundle,
    CharacterBundleError,
    calculate_bundle_digest,
    load_character_bundle,
)
from group_llm_agent.persona_evaluation import (
    PersonaEvaluationError,
    load_evaluation_report,
    verify_evaluation_report,
)

_SOURCE_TO_PRODUCTION = {
    "lezhi-persona-v2.json": "character.json",
    "evaluation-cases.jsonl": "evaluation-cases.jsonl",
    "examples.jsonl": "examples.jsonl",
}
_MAX_ARCHIVE_BYTES = 1_000_000
_MAX_MEMBER_BYTES = 128_000
_SHA256_ZERO = "0" * 64
_PIN_NAMES = ("PERSONA_BUNDLE_PATH", "PERSONA_EXPECTED_SHA256")
_V1_DIGEST = "25af6db13d2a9d4702a167ed99c685d3e934c6436eca491ce7de2ee58907a72a"
_EVALUATION_SETTINGS = {
    "candidate_max_output_tokens": 1200,
    "candidate_temperature": 0.7,
    "judge_max_output_tokens": 800,
    "judge_temperature": 0.0,
    "maximum_attempts_per_call": 2,
}


class PersonaReleaseError(RuntimeError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(f"persona_release_error category={category}")


@dataclass(frozen=True)
class PersonaImportSpec:
    archive_sha256: str
    member_sha256: Mapping[str, str]
    persona_id: str
    persona_version: str
    requirements_commit: str
    confirmed_snapshot_ref: str
    evaluation_report_ref: str


@dataclass(frozen=True)
class PersonaPins:
    bundle_path: str
    digest: str


def read_persona_pins(environment_path: Path) -> PersonaPins:
    values = _read_environment_values(environment_path)
    try:
        pins = PersonaPins(
            bundle_path=values["PERSONA_BUNDLE_PATH"],
            digest=values["PERSONA_EXPECTED_SHA256"],
        )
    except KeyError:
        raise PersonaReleaseError("missing_persona_pins") from None
    _validate_pins(pins)
    return pins


def read_runtime_database_path(environment_path: Path) -> str:
    values = _read_environment_values(environment_path)
    configured = values.get("DATABASE_PATH", "/app/data/telegram_bot.sqlite3")
    path = PurePosixPath(configured)
    if (
        not path.is_absolute()
        or path.parent != PurePosixPath("/app/data")
        or path.name in {"", ".", ".."}
        or any(ord(character) < 32 for character in configured)
    ):
        raise PersonaReleaseError("unsafe_database_path")
    return configured


def replace_persona_pins(environment_path: Path, pins: PersonaPins) -> None:
    """Atomically replace only the two non-secret persona selector lines."""

    _validate_pins(pins)
    try:
        raw = environment_path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise PersonaReleaseError("unreadable_environment") from None
    replacements = {
        "PERSONA_BUNDLE_PATH": pins.bundle_path,
        "PERSONA_EXPECTED_SHA256": pins.digest,
    }
    counts = {name: 0 for name in _PIN_NAMES}
    result: list[str] = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        name, separator, _value = body.partition("=")
        if separator and name in replacements:
            counts[name] += 1
            result.append(f"{name}={replacements[name]}{ending}")
        else:
            result.append(line)
    if counts != {name: 1 for name in _PIN_NAMES}:
        raise PersonaReleaseError("invalid_persona_pin_lines")
    _atomic_write(environment_path, "".join(result).encode("utf-8"), mode=0o600)


def preflight_release(
    *,
    repository_root: Path,
    environment_path: Path,
    candidate_path: str,
    candidate_digest: str,
    report_path: Path,
) -> dict[str, object]:
    current = read_persona_pins(environment_path)
    if current.digest != _V1_DIGEST or "lezhi-v1.0" not in current.bundle_path:
        raise PersonaReleaseError("unverified_rollback_pin")
    rollback_bundle = load_character_bundle(
        _resolve_bundle_path(repository_root, current.bundle_path),
        expected_sha256=current.digest,
        expected_version="lezhi-v1.0",
    )
    candidate = PersonaPins(candidate_path, candidate_digest)
    _validate_pins(candidate)
    candidate_bundle = load_character_bundle(
        _resolve_bundle_path(repository_root, candidate.bundle_path),
        expected_sha256=candidate.digest,
        expected_version="lezhi-v2.0",
    )
    values = _read_environment_values(environment_path)
    model_id = values.get("WRITER_MODEL", "")
    if not model_id or any(character.isspace() for character in model_id):
        raise PersonaReleaseError("invalid_writer_model")
    report = load_evaluation_report(report_path)
    try:
        verify_evaluation_report(
            report,
            bundle=candidate_bundle,
            expected_model_id=model_id,
            expected_generation_settings=_EVALUATION_SETTINGS,
        )
    except PersonaEvaluationError:
        raise PersonaReleaseError("invalid_evaluation_report") from None
    return {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "rollback": {
            "bundle_path": current.bundle_path,
            "digest": rollback_bundle.snapshot.persona_digest,
        },
        "candidate": {
            "bundle_path": candidate.bundle_path,
            "digest": candidate_bundle.snapshot.persona_digest,
        },
        "model_id": model_id,
        "evaluation_report": str(report_path),
        "smoke_baseline_inbound_id": None,
    }


def write_release_state(path: Path, state: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(
        path,
        (
            json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8"),
        mode=0o600,
    )


def load_release_state(path: Path) -> dict[str, object]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise PersonaReleaseError("invalid_release_state") from None
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if not isinstance(value, dict) or raw != canonical.encode("utf-8"):
        raise PersonaReleaseError("invalid_release_state")
    return value


def record_smoke_baseline(path: Path, inbound_id: int) -> None:
    if inbound_id < 0:
        raise PersonaReleaseError("invalid_smoke_baseline")
    state = load_release_state(path)
    state["smoke_baseline_inbound_id"] = inbound_id
    write_release_state(path, state)


def smoke_inbound_baseline(database_path: Path, chat_id: str) -> int:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
        row = connection.execute(
            "SELECT coalesce(max(id), 0) FROM group_messages WHERE chat_id = ? AND direction = 'inbound'",
            (chat_id,),
        ).fetchone()
    except sqlite3.Error:
        raise PersonaReleaseError("smoke_database_unavailable") from None
    finally:
        if connection is not None:
            connection.close()
    return int(row[0])


def verify_smoke(
    *,
    database_path: Path,
    chat_id: str,
    baseline_inbound_id: int,
    persona_version: str,
    persona_digest: str,
) -> dict[str, object]:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        inbound = connection.execute(
            """
            SELECT id, event_id FROM group_messages
            WHERE chat_id = ? AND direction = 'inbound' AND id > ?
            ORDER BY id
            """,
            (chat_id, baseline_inbound_id),
        ).fetchall()
        if not inbound:
            raise PersonaReleaseError("smoke_pending")
        if len(inbound) != 1:
            raise PersonaReleaseError("smoke_inbound_count")
        event_id = str(inbound[0]["event_id"])
        effects = connection.execute(
            """
            SELECT status, persona_version, persona_digest FROM external_effects
            WHERE chat_id = ? AND trigger_event_id = ?
            """,
            (chat_id, event_id),
        ).fetchall()
        if len(effects) > 1:
            raise PersonaReleaseError("smoke_duplicate_effect")
        if effects:
            effect = effects[0]
            if (
                effect["status"] != "sent"
                or effect["persona_version"] != persona_version
                or effect["persona_digest"] != persona_digest
            ):
                raise PersonaReleaseError("smoke_effect_mismatch")
            outcome = "sent"
        else:
            run = connection.execute(
                """
                SELECT status, persona_version, persona_digest FROM effect_runs
                WHERE chat_id = ? AND trigger_event_id = ?
                """,
                (chat_id, event_id),
            ).fetchone()
            if run is None or run["status"] == "processing":
                raise PersonaReleaseError("smoke_pending")
            if (
                run["status"] != "silence"
                or run["persona_version"] != persona_version
                or run["persona_digest"] != persona_digest
            ):
                raise PersonaReleaseError("smoke_effect_mismatch")
            outcome = "silence"
    except PersonaReleaseError:
        raise
    except sqlite3.Error:
        raise PersonaReleaseError("smoke_database_unavailable") from None
    finally:
        if connection is not None:
            connection.close()
    return {
        "inbound_count": 1,
        "external_effect_count": len(effects),
        "outcome": outcome,
        "persona_version": persona_version,
        "persona_digest": persona_digest,
    }


def import_persona_bundle(
    source_zip: Path,
    destination: Path,
    *,
    spec: PersonaImportSpec,
) -> CharacterBundle:
    """Verify and atomically import one immutable v2 persona bundle."""

    _validate_import_spec(spec)
    archive_raw = _read_archive(source_zip)
    if hashlib.sha256(archive_raw).hexdigest() != spec.archive_sha256:
        raise PersonaReleaseError("archive_digest_mismatch")
    source_payloads = _read_source_members(source_zip, expected=spec.member_sha256)

    destination_parent = destination.parent
    destination_parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise PersonaReleaseError("immutable_destination_exists")
    temp_root = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.import-", dir=destination_parent)
    )
    try:
        for source_name, production_name in _SOURCE_TO_PRODUCTION.items():
            (temp_root / production_name).write_bytes(source_payloads[source_name])
        manifest = _manifest(spec)
        _write_canonical_json(temp_root / "manifest.json", manifest)
        manifest["content_sha256"] = calculate_bundle_digest(temp_root)
        _write_canonical_json(temp_root / "manifest.json", manifest)
        bundle = load_character_bundle(
            temp_root,
            expected_sha256=str(manifest["content_sha256"]),
            expected_version=spec.persona_version,
        )
        try:
            os.rename(temp_root, destination)
        except FileExistsError:
            raise PersonaReleaseError("immutable_destination_exists") from None
        return load_character_bundle(
            destination,
            expected_sha256=bundle.snapshot.persona_digest,
            expected_version=spec.persona_version,
        )
    finally:
        if temp_root.exists():
            shutil.rmtree(temp_root)


def _read_archive(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise PersonaReleaseError("unsafe_archive")
    try:
        size = path.stat().st_size
        if size <= 0 or size > _MAX_ARCHIVE_BYTES:
            raise PersonaReleaseError("invalid_archive_size")
        return path.read_bytes()
    except PersonaReleaseError:
        raise
    except OSError:
        raise PersonaReleaseError("unreadable_archive") from None


def _read_source_members(
    path: Path,
    *,
    expected: Mapping[str, str],
) -> dict[str, bytes]:
    if set(expected) != set(_SOURCE_TO_PRODUCTION):
        raise PersonaReleaseError("invalid_member_contract")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if {info.filename for info in infos} != set(_SOURCE_TO_PRODUCTION):
                raise PersonaReleaseError("unexpected_archive_members")
            result: dict[str, bytes] = {}
            for info in infos:
                unix_mode = info.external_attr >> 16
                if (
                    info.is_dir()
                    or info.filename.startswith(("/", "\\"))
                    or Path(info.filename).name != info.filename
                    or ".." in Path(info.filename).parts
                    or stat.S_ISLNK(unix_mode)
                    or info.file_size <= 0
                    or info.file_size > _MAX_MEMBER_BYTES
                ):
                    raise PersonaReleaseError("unsafe_archive_member")
                payload = archive.read(info)
                if len(payload) != info.file_size:
                    raise PersonaReleaseError("invalid_archive_member")
                if hashlib.sha256(payload).hexdigest() != expected[info.filename]:
                    raise PersonaReleaseError("member_digest_mismatch")
                result[info.filename] = payload
    except PersonaReleaseError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError):
        raise PersonaReleaseError("invalid_archive") from None
    return result


def _manifest(spec: PersonaImportSpec) -> dict[str, object]:
    return {
        "schema_version": 2,
        "persona_id": spec.persona_id,
        "persona_version": spec.persona_version,
        "content_sha256": _SHA256_ZERO,
        "requirements_commit": spec.requirements_commit,
        "confirmed_snapshot_ref": spec.confirmed_snapshot_ref,
        "evaluation_report_ref": spec.evaluation_report_ref,
        "source_artifacts": {
            "archive_name": "lezhi-persona-v2-bundle.zip",
            "archive_sha256": spec.archive_sha256,
            "files": {
                production_name: {
                    "source_name": source_name,
                    "sha256": spec.member_sha256[source_name],
                }
                for source_name, production_name in _SOURCE_TO_PRODUCTION.items()
            },
        },
    }


def _validate_import_spec(spec: PersonaImportSpec) -> None:
    if (
        not _is_sha256(spec.archive_sha256)
        or set(spec.member_sha256) != set(_SOURCE_TO_PRODUCTION)
        or not all(_is_sha256(value) for value in spec.member_sha256.values())
        or spec.persona_id != "lezhi"
        or spec.persona_version != "lezhi-v2.0"
        or len(spec.requirements_commit) != 40
        or any(character not in "0123456789abcdef" for character in spec.requirements_commit)
        or not spec.confirmed_snapshot_ref.strip()
        or not spec.evaluation_report_ref.strip()
    ):
        raise PersonaReleaseError("invalid_import_spec")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _write_canonical_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _read_environment_values(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise PersonaReleaseError("unreadable_environment") from None
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = raw_line.partition("=")
        if not separator or not name or name in values:
            raise PersonaReleaseError("invalid_environment_format")
        values[name] = value
    return values


def _validate_pins(pins: PersonaPins) -> None:
    if (
        not pins.bundle_path
        or pins.bundle_path != pins.bundle_path.strip()
        or any(ord(character) < 33 for character in pins.bundle_path)
        or not _is_sha256(pins.digest)
    ):
        raise PersonaReleaseError("invalid_persona_pins")


def _resolve_bundle_path(repository_root: Path, configured_path: str) -> Path:
    try:
        root = repository_root.resolve(strict=True)
        configured = Path(configured_path)
        if configured_path.startswith("/app/"):
            candidate = root / configured_path.removeprefix("/app/")
        elif configured.is_absolute():
            candidate = configured
        else:
            candidate = root / configured
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        raise PersonaReleaseError("unsafe_bundle_path") from None
    return resolved


def _atomic_write(path: Path, payload: bytes, *, mode: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        if temporary.exists():
            temporary.unlink()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage immutable Lezhi persona releases")
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser("import", help="Import an immutable source ZIP")
    importer.add_argument("source_zip", type=Path)
    importer.add_argument("destination", type=Path)
    importer.add_argument("--archive-sha256", required=True)
    importer.add_argument("--character-sha256", required=True)
    importer.add_argument("--evaluation-sha256", required=True)
    importer.add_argument("--examples-sha256", required=True)
    importer.add_argument("--requirements-commit", required=True)
    importer.add_argument("--confirmed-snapshot-ref", required=True)
    importer.add_argument("--evaluation-report-ref", required=True)

    preflight = commands.add_parser("preflight", help="Verify rollback, candidate and report")
    preflight.add_argument("--repository-root", required=True, type=Path)
    preflight.add_argument("--env-file", required=True, type=Path)
    preflight.add_argument("--candidate-path", required=True)
    preflight.add_argument("--candidate-digest", required=True)
    preflight.add_argument("--report", required=True, type=Path)
    preflight.add_argument("--state-file", required=True, type=Path)

    setter = commands.add_parser("set-pins", help="Atomically update persona selectors")
    setter.add_argument("--env-file", required=True, type=Path)
    setter.add_argument("--bundle-path", required=True)
    setter.add_argument("--digest", required=True)

    restore = commands.add_parser("restore-pins", help="Restore recorded rollback selectors")
    restore.add_argument("--env-file", required=True, type=Path)
    restore.add_argument("--state-file", required=True, type=Path)

    baseline = commands.add_parser("smoke-baseline", help="Read the current inbound ID")
    baseline.add_argument("--database", required=True, type=Path)
    baseline.add_argument("--chat-id", required=True)

    record_baseline = commands.add_parser("record-baseline", help="Record the smoke boundary")
    record_baseline.add_argument("--state-file", required=True, type=Path)
    record_baseline.add_argument("--inbound-id", required=True, type=int)

    smoke = commands.add_parser("smoke-verify", help="Verify one bounded Telegram message")
    smoke.add_argument("--database", required=True, type=Path)
    smoke.add_argument("--chat-id", required=True)
    smoke.add_argument("--baseline-id", required=True, type=int)
    smoke.add_argument("--persona-version", required=True)
    smoke.add_argument("--persona-digest", required=True)

    chat_id = commands.add_parser("environment-chat-id", help="Read the non-secret chat ID")
    chat_id.add_argument("--env-file", required=True, type=Path)

    database_path = commands.add_parser(
        "environment-database-path", help="Read the persistent container database path"
    )
    database_path.add_argument("--env-file", required=True, type=Path)

    smoke_arguments = commands.add_parser(
        "state-smoke-arguments", help="Read the non-secret smoke boundary"
    )
    smoke_arguments.add_argument("--state-file", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "import":
            spec = PersonaImportSpec(
                archive_sha256=args.archive_sha256,
                member_sha256={
                    "lezhi-persona-v2.json": args.character_sha256,
                    "evaluation-cases.jsonl": args.evaluation_sha256,
                    "examples.jsonl": args.examples_sha256,
                },
                persona_id="lezhi",
                persona_version="lezhi-v2.0",
                requirements_commit=args.requirements_commit,
                confirmed_snapshot_ref=args.confirmed_snapshot_ref,
                evaluation_report_ref=args.evaluation_report_ref,
            )
            bundle = import_persona_bundle(args.source_zip, args.destination, spec=spec)
            print(
                "persona_bundle_imported "
                f"persona_id={bundle.snapshot.persona_id} "
                f"persona_version={bundle.snapshot.persona_version} "
                f"persona_digest={bundle.snapshot.persona_digest}"
            )
        elif args.command == "preflight":
            state = preflight_release(
                repository_root=args.repository_root,
                environment_path=args.env_file,
                candidate_path=args.candidate_path,
                candidate_digest=args.candidate_digest,
                report_path=args.report,
            )
            write_release_state(args.state_file, state)
            print("persona_preflight_passed rollback=lezhi-v1.0 candidate=lezhi-v2.0 cases=37")
        elif args.command == "set-pins":
            replace_persona_pins(
                args.env_file,
                PersonaPins(bundle_path=args.bundle_path, digest=args.digest),
            )
            print("persona_pins_updated")
        elif args.command == "restore-pins":
            state = load_release_state(args.state_file)
            rollback = state.get("rollback")
            if not isinstance(rollback, dict):
                raise PersonaReleaseError("invalid_release_state")
            replace_persona_pins(
                args.env_file,
                PersonaPins(
                    bundle_path=str(rollback.get("bundle_path", "")),
                    digest=str(rollback.get("digest", "")),
                ),
            )
            print("persona_pins_restored version=lezhi-v1.0")
        elif args.command == "smoke-baseline":
            print(smoke_inbound_baseline(args.database, args.chat_id))
        elif args.command == "record-baseline":
            record_smoke_baseline(args.state_file, args.inbound_id)
            print("persona_smoke_baseline_recorded")
        elif args.command == "smoke-verify":
            evidence = verify_smoke(
                database_path=args.database,
                chat_id=args.chat_id,
                baseline_inbound_id=args.baseline_id,
                persona_version=args.persona_version,
                persona_digest=args.persona_digest,
            )
            print(
                "persona_smoke_passed "
                f"outcome={evidence['outcome']} external_effects={evidence['external_effect_count']}"
            )
        elif args.command == "environment-chat-id":
            chat_id = _read_environment_values(args.env_file).get("TELEGRAM_CHAT_ID", "")
            if not chat_id.startswith("-") or not chat_id[1:].isdigit():
                raise PersonaReleaseError("invalid_chat_id")
            print(chat_id)
        elif args.command == "environment-database-path":
            print(read_runtime_database_path(args.env_file))
        elif args.command == "state-smoke-arguments":
            state = load_release_state(args.state_file)
            candidate = state.get("candidate")
            baseline_id = state.get("smoke_baseline_inbound_id")
            if not isinstance(candidate, dict) or not isinstance(baseline_id, int):
                raise PersonaReleaseError("invalid_release_state")
            digest = str(candidate.get("digest", ""))
            if not _is_sha256(digest):
                raise PersonaReleaseError("invalid_release_state")
            print(f"{baseline_id} {digest}")
        else:
            raise PersonaReleaseError("unsupported_command")
    except (PersonaReleaseError, PersonaEvaluationError, CharacterBundleError) as error:
        category = getattr(error, "category", "failed")
        print(f"persona_release_failed category={category}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
