from __future__ import annotations

import copy
import unittest
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from group_llm_agent.model import (
    ModelMessage,
    ModelRole,
    StructuredModelResult,
)
from group_llm_agent.persona import load_character_bundle
from group_llm_agent.persona_evaluation import (
    EvaluationIdentity,
    PersonaEvaluationError,
    evaluate_persona,
    load_evaluation_report,
    verify_evaluation_report,
    write_evaluation_report,
)

_ROOT = Path(__file__).parents[1]
_BUNDLE_PATH = _ROOT / "src/group_llm_agent/persona_bundles/lezhi/lezhi-v2.0"
_SETTINGS = {
    "candidate_max_output_tokens": 1200,
    "candidate_temperature": 0.7,
    "judge_max_output_tokens": 800,
    "judge_temperature": 0.0,
}


class GeneratedEvaluationModel:
    def __init__(self, *, failing_case_number: int | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.failing_case_number = failing_case_number

    def complete(
        self,
        *,
        model_role: ModelRole,
        messages: Sequence[ModelMessage],
        response_schema: Mapping[str, Any],
        deadline: datetime,
        max_output_tokens: int,
        temperature: float,
    ) -> StructuredModelResult:
        self.calls.append(
            {
                "model_role": model_role,
                "messages": tuple(messages),
                "response_schema": dict(response_schema),
                "deadline": deadline,
                "max_output_tokens": max_output_tokens,
                "temperature": temperature,
            }
        )
        if "oneOf" in response_schema:
            return StructuredModelResult(
                {
                    "kind": "reply",
                    "reason_code": "evaluated_scene",
                    "text": "这个细节有点意思，我先接住，不替你下结论。",
                }
            )
        case_number = sum("oneOf" not in call["response_schema"] for call in self.calls)
        failing = case_number == self.failing_case_number
        return StructuredModelResult(
            {
                "score": 7 if failing else 9,
                "rationale": "未完全满足语气边界。" if failing else "符合人格和边界要求。",
                "critical_violations": ["over_service"] if failing else [],
            }
        )


class PersonaEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = load_character_bundle(_BUNDLE_PATH)
        self.identity = EvaluationIdentity(
            provider_label="configured-openai-compatible",
            model_id="gpt-test",
            reviewer="provider-model-judge:gpt-test",
        )
        self.clock = lambda: datetime(2026, 8, 2, tzinfo=UTC)

    def test_all_37_cases_use_candidate_and_judge_calls_and_pass(self) -> None:
        model = GeneratedEvaluationModel()
        report = evaluate_persona(
            bundle=self.bundle,
            model=model,
            identity=self.identity,
            clock=self.clock,
        )

        self.assertEqual(74, len(model.calls))
        self.assertEqual(37, len(report["cases"]))
        self.assertTrue(report["passed"])
        self.assertEqual(
            [ModelRole.WRITER] * 74,
            [call["model_role"] for call in model.calls],
        )
        self.assertTrue(
            all(
                "CHARACTER_EFFECTOR_POLICY=" in call["messages"][0].content
                for call in model.calls[:37]
            )
        )
        self.assertTrue(
            all(
                "APPLICATION_OWNED_EVIDENCE=" in call["messages"][1].content
                for call in model.calls[37:]
            )
        )
        evidence_18 = report["cases"][17]["evaluation_evidence"]
        evidence_22 = report["cases"][21]["evaluation_evidence"]
        self.assertEqual("application_owned_snapshot_consistency", evidence_18["kind"])
        self.assertEqual("application_owned_name_masked_output_corpus", evidence_22["kind"])
        verify_evaluation_report(
            report,
            bundle=self.bundle,
            expected_model_id="gpt-test",
            expected_generation_settings=_SETTINGS,
        )

    def test_low_score_or_violation_fails_release_verification(self) -> None:
        report = evaluate_persona(
            bundle=self.bundle,
            model=GeneratedEvaluationModel(failing_case_number=3),
            identity=self.identity,
            clock=self.clock,
        )
        self.assertFalse(report["passed"])
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "failed-evaluation.json"
            write_evaluation_report(path, report)
            self.assertFalse(load_evaluation_report(path)["passed"])
        with self.assertRaisesRegex(PersonaEvaluationError, "evaluation_failed"):
            verify_evaluation_report(
                report,
                bundle=self.bundle,
                expected_model_id="gpt-test",
                expected_generation_settings=_SETTINGS,
            )

    def test_report_rejects_tampered_digest_model_settings_and_case(self) -> None:
        report = evaluate_persona(
            bundle=self.bundle,
            model=GeneratedEvaluationModel(),
            identity=self.identity,
            clock=self.clock,
        )
        mutations: tuple[tuple[str, object, str], ...] = (
            ("persona_digest", "0" * 64, "report_bundle_mismatch"),
            ("model_id", "other-model", "report_model_mismatch"),
            ("generation_settings", {}, "report_settings_mismatch"),
        )
        for field, value, category in mutations:
            with self.subTest(field=field):
                changed = copy.deepcopy(report)
                changed[field] = value
                with self.assertRaisesRegex(PersonaEvaluationError, category):
                    verify_evaluation_report(
                        changed,
                        bundle=self.bundle,
                        expected_model_id="gpt-test",
                        expected_generation_settings=_SETTINGS,
                    )

        changed = copy.deepcopy(report)
        changed["cases"][0]["score"] = 3
        with self.assertRaisesRegex(PersonaEvaluationError, "invalid_report_case"):
            verify_evaluation_report(
                changed,
                bundle=self.bundle,
                expected_model_id="gpt-test",
                expected_generation_settings=_SETTINGS,
            )

    def test_report_write_is_canonical_and_replaces_only_after_complete_write(self) -> None:
        report = evaluate_persona(
            bundle=self.bundle,
            model=GeneratedEvaluationModel(),
            identity=self.identity,
            clock=self.clock,
        )
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "provider-evaluation.json"
            path.write_text("old", encoding="utf-8")
            write_evaluation_report(path, report)

            self.assertEqual(report, load_evaluation_report(path))
            self.assertTrue(path.read_bytes().endswith(b"\n"))
            self.assertEqual([], list(path.parent.glob("*.tmp")))

    def test_invalid_candidate_protocol_fails_without_report(self) -> None:
        class InvalidModel(GeneratedEvaluationModel):
            def complete(self, **_kwargs: Any) -> StructuredModelResult:
                return StructuredModelResult({"reply": "not-the-application-protocol"})

        with self.assertRaisesRegex(PersonaEvaluationError, "candidate_invalid_writer_kind"):
            evaluate_persona(
                bundle=self.bundle,
                model=InvalidModel(),
                identity=self.identity,
                clock=self.clock,
            )


if __name__ == "__main__":
    unittest.main()
