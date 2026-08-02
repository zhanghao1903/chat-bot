from __future__ import annotations

import hashlib
import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from group_llm_agent.persona import (
    CharacterBundleError,
    calculate_bundle_digest,
    load_character_bundle,
)

_ROOT = Path(__file__).parents[1]
_V1_PATH = _ROOT / "src/group_llm_agent/persona_bundles/lezhi/lezhi-v1.0"
_V2_PATH = _ROOT / "src/group_llm_agent/persona_bundles/lezhi/lezhi-v2.0"
_V1_DIGEST = "25af6db13d2a9d4702a167ed99c685d3e934c6436eca491ce7de2ee58907a72a"
_V2_DIGEST = "0bea56724a99dfa6f437ac85b158f3d3190e98c7125eecc1f81672f7fbe17603"
_V2_SOURCE_DIGESTS = {
    "character.json": "600fed847d362f272739d6613874aac857e339c02bc76c18619d104280dbbfcc",
    "evaluation-cases.jsonl": "676d03a5f2e5bf4b2c822ab507abe4516c133a4d6ad754dd265dbfdabb7cb08d",
    "examples.jsonl": "7172725c8e1aed81470b8c9257b54ba8f93fa87fcf4e5d99e5df906f0382b420",
}
_V2_FIELDS = {
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
    "member_salience",
    "preference_evolution",
    "relationship_stance",
    "participation_and_silence_rules",
    "situational_behavior",
    "voice_and_interaction_style",
    "negative_and_safety_rules",
    "behavioral_examples",
}


def _write_canonical_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _refresh_v2(root: Path) -> None:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name in _V2_SOURCE_DIGESTS:
        manifest["source_artifacts"]["files"][name]["sha256"] = hashlib.sha256(
            (root / name).read_bytes()
        ).hexdigest()
    _write_canonical_json(manifest_path, manifest)
    manifest["content_sha256"] = calculate_bundle_digest(root)
    _write_canonical_json(manifest_path, manifest)


class ProductionLezhiV2BundleTests(unittest.TestCase):
    def test_exact_source_identity_and_compiled_views(self) -> None:
        bundle = load_character_bundle(
            _V2_PATH,
            expected_sha256=_V2_DIGEST,
            expected_version="lezhi-v2.0",
        )

        self.assertEqual(2, bundle.schema_version)
        self.assertEqual("lezhi", bundle.snapshot.persona_id)
        self.assertEqual(("乐枝",), bundle.direct_address_terms)
        self.assertEqual(
            "25eacf0c81fb903f131ffa5b113b1740d0cf4512",
            bundle.requirements_commit,
        )
        self.assertIn(
            "48d7910e4afefc7854dcfaab227e3880bacac102f24ac23877df8c07856ef820",
            bundle.confirmed_snapshot_ref,
        )
        for name, expected in _V2_SOURCE_DIGESTS.items():
            self.assertEqual(expected, hashlib.sha256((_V2_PATH / name).read_bytes()).hexdigest())

        character = json.loads((_V2_PATH / "character.json").read_text(encoding="utf-8"))
        self.assertEqual(_V2_FIELDS, set(character))
        self.assertEqual(_V2_FIELDS, set(bundle.views.effector.source_fields))
        self.assertEqual(
            _V2_FIELDS,
            set(bundle.views.trigger.source_fields)
            | set(bundle.views.recognition.source_fields)
            | set(bundle.views.effector.source_fields),
        )
        self.assertEqual(character, json.loads(bundle.views.effector.policy_json))
        self.assertEqual(bundle.snapshot, bundle.views.trigger.snapshot)
        self.assertEqual(bundle.snapshot, bundle.views.recognition.snapshot)
        self.assertEqual(bundle.snapshot, bundle.views.effector.snapshot)

    def test_exact_37_case_contract(self) -> None:
        bundle = load_character_bundle(_V2_PATH)
        expected_ids = {f"CB-EVAL-{index:03d}" for index in range(1, 38)}
        evaluation = [json.loads(line) for line in bundle.evaluation_cases_jsonl]
        examples = [json.loads(line) for line in bundle.views.effector.examples_jsonl]

        self.assertEqual(expected_ids, {item["case_id"] for item in evaluation})
        self.assertEqual(expected_ids, {item["case_id"] for item in examples})
        self.assertTrue(all("8/10" in item["pass_condition"] for item in evaluation))

    def test_v1_remains_byte_identical_and_loadable(self) -> None:
        before = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in _V1_PATH.iterdir()
        }
        bundle = load_character_bundle(_V1_PATH, expected_sha256=_V1_DIGEST)
        after = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in _V1_PATH.iterdir()
        }

        self.assertEqual("lezhi-v1.0", bundle.snapshot.persona_version)
        self.assertEqual(before, after)

    def test_unknown_and_missing_v2_fields_fail_closed(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "bundle"
            shutil.copytree(_V2_PATH, root)
            character_path = root / "character.json"
            character = json.loads(character_path.read_text(encoding="utf-8"))
            character["unknown"] = {"value": "unsafe"}
            _write_canonical_json(character_path, character)
            _refresh_v2(root)
            with self.assertRaisesRegex(CharacterBundleError, "invalid_character"):
                load_character_bundle(root)

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "bundle"
            shutil.copytree(_V2_PATH, root)
            character_path = root / "character.json"
            character = json.loads(character_path.read_text(encoding="utf-8"))
            del character["humor_engine"]
            _write_canonical_json(character_path, character)
            _refresh_v2(root)
            with self.assertRaisesRegex(CharacterBundleError, "invalid_character"):
                load_character_bundle(root)

    def test_stale_source_digest_and_wrong_identity_fail_closed(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "bundle"
            shutil.copytree(_V2_PATH, root)
            character_path = root / "character.json"
            character = json.loads(character_path.read_text(encoding="utf-8"))
            character["persona_meta"]["name"] = "另一角色"
            _write_canonical_json(character_path, character)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["content_sha256"] = calculate_bundle_digest(root)
            _write_canonical_json(manifest_path, manifest)
            with self.assertRaisesRegex(CharacterBundleError, "source_digest_mismatch"):
                load_character_bundle(root)

            _refresh_v2(root)
            with self.assertRaisesRegex(CharacterBundleError, "persona_identity_mismatch"):
                load_character_bundle(root)


if __name__ == "__main__":
    unittest.main()
