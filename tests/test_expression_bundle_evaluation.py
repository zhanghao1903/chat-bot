from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from group_llm_agent.expression import canonical_json_bytes, file_sha256, load_expression_catalog
from group_llm_agent.expression_evaluation import (
    ExpressionEvaluationError,
    load_expression_evaluation_cases,
    verify_expression_evaluation_report,
)

_ROOT = (
    Path(__file__).resolve().parents[1]
    / "src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3"
)
_CASES = (
    Path(__file__).resolve().parents[1]
    / "docs/feature/lezhi-avatar-and-expression-v0-3-1/evaluation-cases.json"
)
_STICKERS = ("lezhi.hello_wave.a01", "lezhi.acknowledged.a02")


class ExpressionBundleEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case_set = load_expression_evaluation_cases(
            _CASES,
            expected_sha256=file_sha256(_CASES),
        )
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        raw = json.loads((_ROOT / "catalog.json").read_text(encoding="utf-8"))
        raw["status"] = "approved"
        raw["approval"] = {
            "reference": "user-confirmed:test",
            "candidate_sha256": file_sha256(_ROOT / "catalog.json"),
            "approved_semantic_ids": [entry["semantic_id"] for entry in raw["entries"]],
        }
        for entry in raw["entries"]:
            entry["status"] = "approved"
        path = Path(self.temporary.name) / "catalog.json"
        path.write_bytes(canonical_json_bytes(raw))
        self.catalog_sha = file_sha256(path)
        self.catalog = load_expression_catalog(
            path,
            expected_sha256=self.catalog_sha,
            allowed_statuses=frozenset({"approved"}),
            verify_assets=False,
        )

    def test_case_set_has_40_eligible_and_bounded_guard_coverage(self) -> None:
        self.assertEqual(2, self.case_set.schema_version)
        self.assertEqual(48, len(self.case_set.cases))
        self.assertEqual(40, sum(item.kind == "eligible" for item in self.case_set.cases))
        self.assertEqual(
            {"eligible", "necessary_text", "hard_forbidden", "relationship_forbidden"},
            {item.kind for item in self.case_set.cases},
        )

    def test_sticker_rate_is_observational_and_never_decides_pass(self) -> None:
        for sticker_bearing in (0, 15, 16, 28, 29, 40):
            with self.subTest(sticker_bearing=sticker_bearing):
                report = self._report(sticker_bearing=sticker_bearing)
                summary = verify_expression_evaluation_report(
                    report,
                    case_set=self.case_set,
                    catalog=self.catalog,
                    expected_catalog_sha256=self.catalog_sha,
                    require_pass=False,
                )
                self.assertTrue(summary.passed)
                self.assertEqual(sticker_bearing, summary.sticker_bearing_count)
                self.assertEqual(sticker_bearing / 40, summary.sticker_bearing_rate)

    def test_semantic_case_labels_are_observational_but_repeat_is_enforced(self) -> None:
        for mutation in ("hard_guard", "necessary_text"):
            with self.subTest(mutation=mutation):
                report = self._report(sticker_bearing=16)
                if mutation == "hard_guard":
                    report["results"][43] = {
                        "case_id": "V031-044",
                        "output_kind": "reply_with_sticker",
                        "sticker_id": _STICKERS[0],
                    }
                elif mutation == "necessary_text":
                    report["results"][40] = {
                        "case_id": "V031-041",
                        "output_kind": "sticker",
                        "sticker_id": _STICKERS[0],
                    }
                summary = verify_expression_evaluation_report(
                    report,
                    case_set=self.case_set,
                    catalog=self.catalog,
                    expected_catalog_sha256=self.catalog_sha,
                    require_pass=False,
                )
                self.assertTrue(summary.passed)

        repeated = self._report(sticker_bearing=16)
        repeated["results"][1]["sticker_id"] = repeated["results"][0]["sticker_id"]
        repeated["passed"] = False
        summary = verify_expression_evaluation_report(
            repeated,
            case_set=self.case_set,
            catalog=self.catalog,
            expected_catalog_sha256=self.catalog_sha,
            require_pass=False,
        )
        self.assertFalse(summary.passed)

    def test_self_reported_pass_cannot_override_deterministic_failure(self) -> None:
        report = self._report(sticker_bearing=16)
        report["results"][1]["sticker_id"] = report["results"][0]["sticker_id"]
        with self.assertRaisesRegex(ExpressionEvaluationError, "report_pass_mismatch"):
            verify_expression_evaluation_report(
                report,
                case_set=self.case_set,
                catalog=self.catalog,
                expected_catalog_sha256=self.catalog_sha,
            )

    def _report(self, *, sticker_bearing: int) -> dict:
        results: list[dict[str, object]] = []
        bearing_ordinal = 0
        for case in self.case_set.cases:
            if case.kind == "eligible" and bearing_ordinal < sticker_bearing:
                kind = "sticker" if bearing_ordinal % 2 == 0 else "reply_with_sticker"
                result: dict[str, object] = {
                    "case_id": case.case_id,
                    "output_kind": kind,
                    "sticker_id": _STICKERS[bearing_ordinal % len(_STICKERS)],
                }
                bearing_ordinal += 1
            else:
                result = {
                    "case_id": case.case_id,
                    "output_kind": "reply",
                    "sticker_id": None,
                }
            results.append(result)
        return {
            "schema_version": 2,
            "evaluation_id": self.case_set.evaluation_id,
            "case_set_sha256": self.case_set.digest,
            "catalog_id": self.catalog.catalog_id,
            "catalog_version": self.catalog.catalog_version,
            "catalog_sha256": self.catalog_sha,
            "persona_version": self.catalog.persona_version,
            "persona_digest": self.catalog.persona_digest,
            "provider_label": "configured-provider",
            "model_id": "configured-model",
            "generated_at": "2026-08-04T00:00:00+00:00",
            "results": results,
            "passed": True,
        }


if __name__ == "__main__":
    unittest.main()
