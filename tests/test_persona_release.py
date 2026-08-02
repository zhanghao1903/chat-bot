from __future__ import annotations

import hashlib
import json
import sqlite3
import unittest
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from group_llm_agent.database import SQLiteDatabase
from group_llm_agent.persona_evaluation import write_evaluation_report
from group_llm_agent.persona_release import (
    PersonaImportSpec,
    PersonaPins,
    PersonaReleaseError,
    import_persona_bundle,
    load_release_state,
    preflight_release,
    read_persona_pins,
    read_runtime_database_path,
    record_release_failure,
    replace_persona_pins,
    smoke_trigger_baseline,
    verify_smoke,
    write_release_state,
)

_ROOT = Path(__file__).parents[1]
_V2_PATH = _ROOT / "src/group_llm_agent/persona_bundles/lezhi/lezhi-v2.0"
_SOURCE_NAMES = {
    "lezhi-persona-v2.json": "character.json",
    "evaluation-cases.jsonl": "evaluation-cases.jsonl",
    "examples.jsonl": "examples.jsonl",
}


def _make_zip(path: Path, *, extra_member: str | None = None) -> dict[str, str]:
    digests: dict[str, str] = {}
    with zipfile.ZipFile(path, "w") as archive:
        for source_name, production_name in _SOURCE_NAMES.items():
            payload = (_V2_PATH / production_name).read_bytes()
            archive.writestr(source_name, payload)
            digests[source_name] = hashlib.sha256(payload).hexdigest()
        if extra_member is not None:
            archive.writestr(extra_member, b"unsafe")
    return digests


def _spec(archive: Path, members: dict[str, str]) -> PersonaImportSpec:
    return PersonaImportSpec(
        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        member_sha256=members,
        persona_id="lezhi",
        persona_version="lezhi-v2.0",
        requirements_commit="25eacf0c81fb903f131ffa5b113b1740d0cf4512",
        confirmed_snapshot_ref="RequirementsHandoff:test",
        evaluation_report_ref="docs/provider-evaluation.json",
    )


class PersonaImportTests(unittest.TestCase):
    def test_verified_import_is_atomic_and_immutable(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = root / "source.zip"
            members = _make_zip(archive)
            destination = root / "bundles" / "lezhi-v2.0"

            bundle = import_persona_bundle(archive, destination, spec=_spec(archive, members))

            self.assertEqual("lezhi-v2.0", bundle.snapshot.persona_version)
            self.assertTrue(destination.is_dir())
            self.assertEqual(
                set(_SOURCE_NAMES.values()) | {"manifest.json"},
                {item.name for item in destination.iterdir()},
            )
            with self.assertRaisesRegex(PersonaReleaseError, "immutable_destination_exists"):
                import_persona_bundle(archive, destination, spec=_spec(archive, members))

    def test_archive_and_member_digest_mismatches_fail_closed(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = root / "source.zip"
            members = _make_zip(archive)
            destination = root / "bundle"
            wrong_archive = PersonaImportSpec(
                **{
                    **_spec(archive, members).__dict__,
                    "archive_sha256": "0" * 64,
                }
            )
            with self.assertRaisesRegex(PersonaReleaseError, "archive_digest_mismatch"):
                import_persona_bundle(archive, destination, spec=wrong_archive)
            self.assertFalse(destination.exists())

            wrong_members = dict(members)
            wrong_members["examples.jsonl"] = "0" * 64
            with self.assertRaisesRegex(PersonaReleaseError, "member_digest_mismatch"):
                import_persona_bundle(
                    archive,
                    destination,
                    spec=_spec(archive, wrong_members),
                )
            self.assertFalse(destination.exists())

    def test_unexpected_and_unsafe_archive_members_fail_closed(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = root / "source.zip"
            members = _make_zip(archive, extra_member="../escape")
            destination = root / "bundle"

            with self.assertRaisesRegex(PersonaReleaseError, "unexpected_archive_members"):
                import_persona_bundle(archive, destination, spec=_spec(archive, members))
            self.assertFalse(destination.exists())

    def test_symlink_source_and_invalid_spec_fail_closed(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = root / "source.zip"
            members = _make_zip(archive)
            link = root / "linked.zip"
            try:
                link.symlink_to(archive)
            except OSError:
                self.skipTest("symlinks are unavailable")
            with self.assertRaisesRegex(PersonaReleaseError, "unsafe_archive"):
                import_persona_bundle(link, root / "bundle", spec=_spec(archive, members))

            invalid = PersonaImportSpec(
                **{
                    **_spec(archive, members).__dict__,
                    "requirements_commit": "not-a-commit",
                }
            )
            with self.assertRaisesRegex(PersonaReleaseError, "invalid_import_spec"):
                import_persona_bundle(archive, root / "bundle", spec=invalid)


class PersonaDeploymentGateTests(unittest.TestCase):
    def test_release_failure_and_rollback_result_are_persisted_without_secrets(self) -> None:
        with TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "persona-release.json"
            write_release_state(
                state_path,
                {
                    "schema_version": 1,
                    "candidate": {"digest": "candidate"},
                },
            )

            record_release_failure(
                state_path,
                stage="smoke_baseline",
                rollback_status="attempted",
            )
            record_release_failure(
                state_path,
                stage="smoke_baseline",
                rollback_status="succeeded",
            )

            state = load_release_state(state_path)
            failure = state["failure"]
            self.assertIsInstance(failure, dict)
            self.assertEqual(
                {
                    "stage": "smoke_baseline",
                    "rollback_status": "succeeded",
                },
                {
                    "stage": failure["stage"],
                    "rollback_status": failure["rollback_status"],
                },
            )
            self.assertNotIn("token", state_path.read_text(encoding="utf-8").lower())

    def test_database_path_preserves_the_existing_volume_file(self) -> None:
        with TemporaryDirectory() as tmpdir:
            environment = Path(tmpdir) / ".env"
            environment.write_text(
                "DATABASE_PATH=/app/data/telegram-bot.sqlite3\n",
                encoding="utf-8",
            )

            self.assertEqual(
                "/app/data/telegram-bot.sqlite3",
                read_runtime_database_path(environment),
            )

            environment.write_text(
                "DATABASE_PATH=/app/data/../other.sqlite3\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(PersonaReleaseError, "unsafe_database_path"):
                read_runtime_database_path(environment)

    def test_pin_replacement_preserves_every_other_environment_byte(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".env"
            original = (
                "# operator file\n"
                "TELEGRAM_BOT_TOKEN=123456:do-not-print\n"
                "PERSONA_BUNDLE_PATH=/app/src/group_llm_agent/persona_bundles/lezhi/lezhi-v1.0\n"
                "MODEL_API_KEY=secret-value\n"
                "PERSONA_EXPECTED_SHA256="
                "25af6db13d2a9d4702a167ed99c685d3e934c6436eca491ce7de2ee58907a72a\n"
            )
            path.write_text(original, encoding="utf-8")
            new = PersonaPins(
                "/app/src/group_llm_agent/persona_bundles/lezhi/lezhi-v2.0",
                "0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603",
            )

            replace_persona_pins(path, new)

            changed = path.read_text(encoding="utf-8")
            self.assertEqual(new, read_persona_pins(path))
            self.assertIn("TELEGRAM_BOT_TOKEN=123456:do-not-print\n", changed)
            self.assertIn("MODEL_API_KEY=secret-value\n", changed)
            restored = PersonaPins(
                "/app/src/group_llm_agent/persona_bundles/lezhi/lezhi-v1.0",
                "25af6db13d2a9d4702a167ed99c685d3e934c6436eca491ce7de2ee58907a72a",
            )
            replace_persona_pins(path, restored)
            self.assertEqual(original, path.read_text(encoding="utf-8"))

    def test_preflight_accepts_only_exact_v1_rollback_and_passing_v2_report(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repository = root / "repository"
            source_root = _ROOT / "src/group_llm_agent/persona_bundles/lezhi"
            destination_root = repository / "src/group_llm_agent/persona_bundles/lezhi"
            destination_root.mkdir(parents=True)
            for version in ("lezhi-v1.0", "lezhi-v2.0"):
                import shutil

                shutil.copytree(source_root / version, destination_root / version)
            environment = root / ".env"
            environment.write_text(
                "PERSONA_BUNDLE_PATH=/app/src/group_llm_agent/persona_bundles/lezhi/lezhi-v1.0\n"
                "PERSONA_EXPECTED_SHA256="
                "25af6db13d2a9d4702a167ed99c685d3e934c6436eca491ce7de2ee58907a72a\n"
                "WRITER_MODEL=gpt-5.6-sol\nMODEL_API_KEY=secret\n",
                encoding="utf-8",
            )
            report_path = _ROOT / "docs/feature/lezhi-persona-v2-release/provider-evaluation.json"

            state = preflight_release(
                repository_root=repository,
                environment_path=environment,
                candidate_path="/app/src/group_llm_agent/persona_bundles/lezhi/lezhi-v2.0",
                candidate_digest="0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603",
                report_path=report_path,
            )

            self.assertEqual("gpt-5.6-sol", state["model_id"])
            self.assertNotIn("secret", json.dumps(state))

            fabricated = json.loads(report_path.read_text(encoding="utf-8"))
            fabricated["provider_label"] = "synthetic-provider"
            fabricated["reviewer"] = "synthetic-reviewer"
            for case in fabricated["cases"]:
                case["output_text"] = "fabricated"
                case["reason_code"] = "fabricated"
                case["rationale"] = "fabricated"
                case["score"] = 10
                case["critical_violations"] = []
                case["passed"] = True
            synthetic_path = root / "synthetic-report.json"
            write_evaluation_report(synthetic_path, fabricated)
            with self.assertRaisesRegex(PersonaReleaseError, "unapproved_evaluation_report"):
                preflight_release(
                    repository_root=repository,
                    environment_path=environment,
                    candidate_path="/app/src/group_llm_agent/persona_bundles/lezhi/lezhi-v2.0",
                    candidate_digest=(
                        "0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603"
                    ),
                    report_path=synthetic_path,
                )

            environment.write_text(
                environment.read_text(encoding="utf-8").replace("lezhi-v1.0", "lezhi-v2.0"),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(PersonaReleaseError, "unverified_rollback_pin"):
                preflight_release(
                    repository_root=repository,
                    environment_path=environment,
                    candidate_path="/app/src/group_llm_agent/persona_bundles/lezhi/lezhi-v2.0",
                    candidate_digest="0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603",
                    report_path=report_path,
                )

    def test_smoke_requires_one_new_inbound_and_at_most_one_exact_effect(self) -> None:
        with TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "runtime.sqlite3"
            database = SQLiteDatabase(database_path)
            database.initialize()
            connection = sqlite3.connect(database_path)
            try:
                connection.execute(
                    """
                    INSERT INTO trigger_evaluations (
                        request_id, chat_id, trigger_event_id, trigger_message_id,
                        trigger_category, persona_name_hit,
                        continuity_anchor_message_id, decision_kind, reason_code,
                        model_status, persona_id, persona_version, persona_digest,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'direct_platform', 1, NULL,
                              'effect_requested', 'explicit_mention', 'not_called',
                              'lezhi', 'lezhi-v1.0', ?, ?, ?)
                    """,
                    (
                        "trigger:event-1",
                        "-1001",
                        "event-1",
                        "1",
                        "25af6db13d2a9d4702a167ed99c685d3e934c6436eca491ce7de2ee58907a72a",
                        datetime.now(UTC).isoformat(),
                        datetime.now(UTC).isoformat(),
                    ),
                )
                connection.commit()
                baseline = smoke_trigger_baseline(database_path, "-1001")
                connection.execute(
                    """
                    INSERT INTO trigger_evaluations (
                        request_id, chat_id, trigger_event_id, trigger_message_id,
                        trigger_category, persona_name_hit,
                        continuity_anchor_message_id, decision_kind, reason_code,
                        model_status, persona_id, persona_version, persona_digest,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'direct_platform', 1, NULL,
                              'effect_requested', 'explicit_mention', 'not_called',
                              'lezhi', 'lezhi-v2.0', ?, ?, ?)
                    """,
                    (
                        "trigger:event-2",
                        "-1001",
                        "event-2",
                        "2",
                        "0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603",
                        datetime.now(UTC).isoformat(),
                        datetime.now(UTC).isoformat(),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO external_effects (
                        chat_id, trigger_event_id, trigger_message_id, effect_kind,
                        status, persona_version, persona_digest, created_at, updated_at
                    ) VALUES (?, ?, ?, 'reply', 'sent', ?, ?, ?, ?)
                    """,
                    (
                        "-1001",
                        "event-2",
                        "2",
                        "lezhi-v2.0",
                        "0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603",
                        datetime.now(UTC).isoformat(),
                        datetime.now(UTC).isoformat(),
                    ),
                )
                connection.commit()
            finally:
                connection.close()

            evidence = verify_smoke(
                database_path=database_path,
                chat_id="-1001",
                baseline_trigger_evaluation_id=baseline,
                persona_version="lezhi-v2.0",
                persona_digest="0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603",
            )
            self.assertEqual("sent", evidence["outcome"])
            self.assertEqual(1, evidence["external_effect_count"])


if __name__ == "__main__":
    unittest.main()
