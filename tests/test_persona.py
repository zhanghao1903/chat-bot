from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from helpers import copied_persona_fixture

from group_llm_agent.persona import (
    CharacterBundleError,
    calculate_bundle_digest,
    load_character_bundle,
)

_FIXTURE_DIGEST = "66aedcef8aaf83d599fb065fa34397eee00ee121848395586b0c03a2b9bce590"


def _write_canonical_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _refresh_digest(root: Path) -> str:
    digest = calculate_bundle_digest(root)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["content_sha256"] = digest
    _write_canonical_json(manifest_path, manifest)
    return digest


class CharacterBundleTests(unittest.TestCase):
    def test_valid_bundle_compiles_three_consistent_immutable_views(self) -> None:
        fixture = Path(__file__).parent / "fixtures/personas/test-original/v1"
        bundle = load_character_bundle(
            fixture,
            expected_sha256=_FIXTURE_DIGEST,
            expected_version="v1",
        )

        self.assertEqual("test-original-do-not-ship", bundle.snapshot.persona_id)
        self.assertEqual(bundle.snapshot, bundle.views.trigger.snapshot)
        self.assertEqual(bundle.snapshot, bundle.views.recognition.snapshot)
        self.assertEqual(bundle.snapshot, bundle.views.effector.snapshot)
        self.assertEqual("trigger", bundle.views.trigger.role)
        self.assertIn("attention_and_interest", bundle.views.trigger.policy_json)
        self.assertNotIn("voice_and_interaction_style", bundle.views.trigger.policy_json)
        self.assertIn("member_salience", bundle.views.recognition.policy_json)
        self.assertIn("voice_and_interaction_style", bundle.views.effector.policy_json)
        self.assertEqual(2, len(bundle.views.effector.examples_jsonl))
        self.assertEqual(bundle, load_character_bundle(fixture))

    def test_changed_content_is_rejected_by_stale_manifest(self) -> None:
        with copied_persona_fixture() as fixture:
            character_path = fixture / "character.json"
            character_path.write_bytes(character_path.read_bytes() + b" ")
            with self.assertRaisesRegex(CharacterBundleError, "digest_mismatch"):
                load_character_bundle(fixture)

    def test_unknown_character_field_is_rejected_after_valid_digest_refresh(self) -> None:
        with copied_persona_fixture() as fixture:
            character_path = fixture / "character.json"
            character = json.loads(character_path.read_text(encoding="utf-8"))
            character["unknown"] = {"unsafe": True}
            _write_canonical_json(character_path, character)
            _refresh_digest(fixture)

            with self.assertRaisesRegex(CharacterBundleError, "invalid_character"):
                load_character_bundle(fixture)

    def test_missing_section_and_confirmation_reference_fail_closed(self) -> None:
        with copied_persona_fixture() as fixture:
            character_path = fixture / "character.json"
            character = json.loads(character_path.read_text(encoding="utf-8"))
            del character["dramatic_engine"]
            _write_canonical_json(character_path, character)
            _refresh_digest(fixture)
            with self.assertRaisesRegex(CharacterBundleError, "invalid_character"):
                load_character_bundle(fixture)

        with copied_persona_fixture() as fixture:
            manifest_path = fixture / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["confirmed_snapshot_ref"] = ""
            _write_canonical_json(manifest_path, manifest)
            with self.assertRaisesRegex(
                CharacterBundleError,
                "missing_confirmation_reference",
            ):
                load_character_bundle(fixture)

    def test_unsafe_symlink_and_unexpected_file_are_rejected(self) -> None:
        with copied_persona_fixture() as fixture:
            (fixture / "unexpected.txt").write_text("not allowed", encoding="utf-8")
            with self.assertRaisesRegex(CharacterBundleError, "unexpected_bundle_files"):
                load_character_bundle(fixture)

        with copied_persona_fixture() as fixture, TemporaryDirectory() as tmpdir:
            symlink = Path(tmpdir) / "linked-persona"
            try:
                symlink.symlink_to(fixture, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks are unavailable")
            with self.assertRaisesRegex(CharacterBundleError, "unsafe_path"):
                load_character_bundle(symlink)

    def test_test_fixture_is_not_copied_into_runtime_package_data(self) -> None:
        package_root = Path(__file__).parents[1] / "src/group_llm_agent/persona_bundles"
        self.assertTrue(package_root.exists())
        self.assertFalse((package_root / "test-original").exists())


if __name__ == "__main__":
    unittest.main()
