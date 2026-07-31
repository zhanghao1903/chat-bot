from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from group_llm_agent.persona import load_character_bundle

_ROOT = Path(__file__).parents[1]
_BUNDLE_PATH = _ROOT / "src/group_llm_agent/persona_bundles/lezhi/lezhi-v1.0"
_BUNDLE_DIGEST = "25af6db13d2a9d4702a167ed99c685d3e934c6436eca491ce7de2ee58907a72a"
_BIBLE_DIGEST = "46eb6a18323b5549e7a0b3dbc30f3d56e902356d52bb86ba294d0ae5f9542f68"


class ProductionLezhiBundleTests(unittest.TestCase):
    def test_confirmed_bundle_loads_with_exact_immutable_identity(self) -> None:
        bundle = load_character_bundle(
            _BUNDLE_PATH,
            expected_sha256=_BUNDLE_DIGEST,
            expected_version="lezhi-v1.0",
        )

        self.assertEqual("lezhi", bundle.snapshot.persona_id)
        self.assertEqual("lezhi-v1.0", bundle.snapshot.persona_version)
        self.assertEqual(_BUNDLE_DIGEST, bundle.snapshot.persona_digest)
        self.assertEqual(("乐枝",), bundle.direct_address_terms)
        self.assertEqual(
            "c5ea34553e52505ff50ee421cc08efff297df01f",
            bundle.requirements_commit,
        )
        self.assertIn(
            "3dd1f8b56c9e7e4d4bda9f8c75450570a2902126",
            bundle.confirmed_snapshot_ref,
        )
        self.assertIn(_BIBLE_DIGEST, bundle.confirmed_snapshot_ref)
        self.assertEqual(
            "docs/feature/maomao-persona-chat/persona-evaluation.md",
            bundle.evaluation_report_ref,
        )
        self.assertEqual(
            bundle.views.trigger.snapshot,
            bundle.views.recognition.snapshot,
        )
        self.assertEqual(
            bundle.views.recognition.snapshot,
            bundle.views.effector.snapshot,
        )

    def test_bundle_preserves_confirmed_three_view_character_logic(self) -> None:
        bundle = load_character_bundle(_BUNDLE_PATH)
        trigger = json.loads(bundle.views.trigger.policy_json)
        recognition = json.loads(bundle.views.recognition.policy_json)
        effector = json.loads(bundle.views.effector.policy_json)

        self.assertEqual("乐枝", trigger["identity_and_stable_facts"]["name"])
        self.assertIn("core_desire", trigger["dramatic_engine"])
        self.assertIn("participation_and_silence_rules", trigger)
        self.assertIn("member_salience", recognition)
        self.assertIn("preference_evolution", recognition)
        self.assertIn("voice_and_interaction_style", effector)
        self.assertIn("creator_affection", effector["dramatic_engine"])
        self.assertIn("close", effector["relationship_stance"])
        self.assertEqual(15, len(bundle.views.effector.examples_jsonl))

    def test_fixed_evaluation_contract_has_all_cases_and_critical_boundaries(self) -> None:
        bundle = load_character_bundle(_BUNDLE_PATH)
        cases = [json.loads(line) for line in bundle.evaluation_cases_jsonl]
        case_ids = {str(case["case_id"]) for case in cases}
        expected_ids = {f"CB-EVAL-{index:03d}" for index in range(1, 23)}

        self.assertEqual(expected_ids, case_ids)
        self.assertTrue(all("8/10" in str(case["pass_condition"]) for case in cases))
        critical_ids = {str(case["case_id"]) for case in cases if case["critical"] is True}
        self.assertTrue(
            {
                "CB-EVAL-001",
                "CB-EVAL-004",
                "CB-EVAL-011",
                "CB-EVAL-012",
                "CB-EVAL-013",
                "CB-EVAL-014",
                "CB-EVAL-016",
                "CB-EVAL-017",
                "CB-EVAL-018",
                "CB-EVAL-020",
                "CB-EVAL-021",
            }.issubset(critical_ids)
        )

    def test_bundle_is_tied_to_exact_confirmed_character_bible_bytes(self) -> None:
        bible_path = _ROOT / "docs/feature/maomao-persona-chat/character-bible.md"
        digest = hashlib.sha256(bible_path.read_bytes()).hexdigest()
        self.assertEqual(_BIBLE_DIGEST, digest)

    def test_bundle_contains_no_known_research_character_or_framework_identity(self) -> None:
        content = "\n".join(
            path.read_text(encoding="utf-8") for path in sorted(_BUNDLE_PATH.iterdir())
        )
        for forbidden in (
            "SillyTavern",
            "ChatHaruhi",
            "凉宫春日",
            "药屋少女",
            "Character Card",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, content)


if __name__ == "__main__":
    unittest.main()
