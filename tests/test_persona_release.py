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
from group_llm_agent.persona import load_character_bundle
from group_llm_agent.persona_evaluation import write_evaluation_report
from group_llm_agent.persona_release import (
    PersonaImportSpec,
    PersonaPins,
    PersonaReleaseError,
    import_persona_bundle,
    preflight_release,
    read_persona_pins,
    replace_persona_pins,
    smoke_inbound_baseline,
    verify_smoke,
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
                "WRITER_MODEL=gpt-test\nMODEL_API_KEY=secret\n",
                encoding="utf-8",
            )
            report_path = root / "report.json"
            write_evaluation_report(report_path, _passing_report())

            state = preflight_release(
                repository_root=repository,
                environment_path=environment,
                candidate_path="/app/src/group_llm_agent/persona_bundles/lezhi/lezhi-v2.0",
                candidate_digest="0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603",
                report_path=report_path,
            )

            self.assertEqual("gpt-test", state["model_id"])
            self.assertNotIn("secret", json.dumps(state))

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
                    INSERT INTO group_messages (
                        chat_id, telegram_message_id, event_id, sender_user_id,
                        sender_display_name, direction, text, text_sha256, sent_at,
                        ingested_at
                    ) VALUES (?, ?, ?, ?, ?, 'inbound', ?, ?, ?, ?)
                    """,
                    (
                        "-1001",
                        "1",
                        "event-1",
                        "member-1",
                        "Member",
                        "乐枝，在吗？",
                        "digest",
                        datetime.now(UTC).isoformat(),
                        datetime.now(UTC).isoformat(),
                    ),
                )
                connection.commit()
                baseline = smoke_inbound_baseline(database_path, "-1001")
                connection.execute(
                    """
                    INSERT INTO group_messages (
                        chat_id, telegram_message_id, event_id, sender_user_id,
                        sender_display_name, direction, text, text_sha256, sent_at,
                        ingested_at
                    ) VALUES (?, ?, ?, ?, ?, 'inbound', ?, ?, ?, ?)
                    """,
                    (
                        "-1001",
                        "2",
                        "event-2",
                        "member-1",
                        "Member",
                        "乐枝，你怎么看？",
                        "digest",
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
                baseline_inbound_id=baseline,
                persona_version="lezhi-v2.0",
                persona_digest="0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603",
            )
            self.assertEqual("sent", evidence["outcome"])
            self.assertEqual(1, evidence["external_effect_count"])


def _passing_report() -> dict[str, object]:
    bundle = load_character_bundle(_V2_PATH)
    evaluations = [json.loads(line) for line in bundle.evaluation_cases_jsonl]
    return {
        "schema_version": 1,
        "persona_id": "lezhi",
        "persona_version": "lezhi-v2.0",
        "persona_digest": bundle.snapshot.persona_digest,
        "provider_label": "test-provider",
        "model_id": "gpt-test",
        "generation_settings": {
            "candidate_max_output_tokens": 1200,
            "candidate_temperature": 0.7,
            "judge_max_output_tokens": 800,
            "judge_temperature": 0.0,
        },
        "generated_at": datetime(2026, 8, 2, tzinfo=UTC).isoformat(),
        "reviewer": "provider-model-judge:gpt-test",
        "cases": [
            {
                "case_id": item["case_id"],
                "dimension": item["dimension"],
                "critical": item["critical"],
                "output_kind": "reply",
                "output_text": "测试回答",
                "reason_code": "test",
                "score": 9,
                "rationale": "满足要求",
                "critical_violations": [],
                "passed": True,
            }
            for item in evaluations
        ],
        "passed": True,
    }


if __name__ == "__main__":
    unittest.main()
