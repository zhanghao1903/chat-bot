from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from group_llm_agent.expression import canonical_json_bytes, file_sha256, load_expression_catalog
from group_llm_agent.expression_evaluation import (
    ExpressionEvaluationError,
    load_and_verify_expression_evaluation_report,
    load_expression_evaluation_cases,
    verify_expression_evaluation_report,
)

_ROOT = (
    Path(__file__).resolve().parents[1]
    / "src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3"
)
_CASE_PATH = _ROOT / "evaluation-cases.json"
_STICKERS = (
    "lezhi.hello_wave.a01",
    "lezhi.acknowledged.a02",
    "lezhi.thinking.a05",
    "lezhi.approving.a06",
    "lezhi.cheering.a08",
    "lezhi.apologetic.a09",
)


class ExpressionEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = load_expression_evaluation_cases(
            _CASE_PATH,
            expected_sha256=file_sha256(_CASE_PATH),
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
        self.catalog_path = Path(self.temporary.name) / "catalog.json"
        self.catalog_path.write_bytes(canonical_json_bytes(raw))
        self.catalog_sha = file_sha256(self.catalog_path)
        self.catalog = load_expression_catalog(
            self.catalog_path,
            expected_sha256=self.catalog_sha,
            allowed_statuses=frozenset({"approved"}),
            verify_assets=False,
        )

    def test_fixed_set_has_light_and_must_text_coverage(self) -> None:
        self.assertEqual(20, len(self.cases.cases))
        self.assertEqual(10, sum(case.kind == "light" for case in self.cases.cases))
        self.assertEqual(10, sum(case.kind == "must_text" for case in self.cases.cases))

    def test_sixty_percent_stickers_and_all_required_text_pass(self) -> None:
        report = self._report()
        summary = verify_expression_evaluation_report(
            report,
            case_set=self.cases,
            catalog=self.catalog,
            expected_catalog_sha256=self.catalog_sha,
        )
        self.assertTrue(summary.passed)
        self.assertEqual(6, summary.sticker_only_count)
        self.assertEqual(0.6, summary.sticker_only_rate)

        report_path = Path(self.temporary.name) / "report.json"
        report_path.write_bytes(canonical_json_bytes(report))
        loaded = load_and_verify_expression_evaluation_report(
            report_path,
            expected_sha256=file_sha256(report_path),
            case_set=self.cases,
            catalog=self.catalog,
            expected_catalog_sha256=self.catalog_sha,
        )
        self.assertEqual(summary, loaded)

    def test_frequency_outside_target_fails_even_when_self_reported_consistently(self) -> None:
        report = self._report()
        for index in range(3, 6):
            report["results"][index] = {
                "case_id": f"EXPR-{index + 1:03d}",
                "output_kind": "reply",
                "sticker_id": None,
            }
        report["passed"] = False
        summary = verify_expression_evaluation_report(
            report,
            case_set=self.cases,
            catalog=self.catalog,
            expected_catalog_sha256=self.catalog_sha,
            require_pass=False,
        )
        self.assertEqual(0.3, summary.sticker_only_rate)
        with self.assertRaisesRegex(ExpressionEvaluationError, "expression_evaluation_failed"):
            verify_expression_evaluation_report(
                report,
                case_set=self.cases,
                catalog=self.catalog,
                expected_catalog_sha256=self.catalog_sha,
            )

    def test_must_text_sticker_and_consecutive_repeat_fail(self) -> None:
        for mutation in ("must_text", "repeat"):
            with self.subTest(mutation=mutation):
                report = self._report()
                if mutation == "must_text":
                    report["results"][10] = {
                        "case_id": "EXPR-011",
                        "output_kind": "sticker",
                        "sticker_id": _STICKERS[0],
                    }
                else:
                    report["results"][1]["sticker_id"] = _STICKERS[0]
                report["passed"] = False
                summary = verify_expression_evaluation_report(
                    report,
                    case_set=self.cases,
                    catalog=self.catalog,
                    expected_catalog_sha256=self.catalog_sha,
                    require_pass=False,
                )
                self.assertFalse(summary.passed)

    def test_unknown_or_unapproved_sticker_fails_closed(self) -> None:
        report = self._report()
        report["results"][0]["sticker_id"] = "telegram-raw-file-id"
        with self.assertRaisesRegex(ExpressionEvaluationError, "sticker_not_in_approved_catalog"):
            verify_expression_evaluation_report(
                report,
                case_set=self.cases,
                catalog=self.catalog,
                expected_catalog_sha256=self.catalog_sha,
            )

    def _report(self) -> dict:
        results = []
        for index, case in enumerate(self.cases.cases):
            if case.kind == "light" and index < 6:
                result = {
                    "case_id": case.case_id,
                    "output_kind": "sticker",
                    "sticker_id": _STICKERS[index],
                }
            else:
                result = {
                    "case_id": case.case_id,
                    "output_kind": "reply",
                    "sticker_id": None,
                }
            results.append(result)
        return {
            "schema_version": 1,
            "evaluation_id": self.cases.evaluation_id,
            "case_set_sha256": self.cases.digest,
            "catalog_id": self.catalog.catalog_id,
            "catalog_version": self.catalog.catalog_version,
            "catalog_sha256": self.catalog_sha,
            "persona_version": self.catalog.persona_version,
            "persona_digest": self.catalog.persona_digest,
            "provider_label": "configured-provider",
            "model_id": "configured-model",
            "generated_at": "2026-08-02T00:00:00+00:00",
            "results": copy.deepcopy(results),
            "passed": True,
        }


if __name__ == "__main__":
    unittest.main()
