from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from group_llm_agent.effector import WRITER_RESPONSE_SCHEMA
from group_llm_agent.model import (
    ModelApiError,
    ModelMessage,
    ModelResultError,
    ModelRole,
    OpenAICompatibleStructuredModelClient,
    StructuredModelPort,
    WriterDecision,
    WriterDecisionKind,
    parse_writer_decision,
)
from group_llm_agent.persona import CharacterBundle, load_character_bundle

_REPORT_FIELDS = {
    "schema_version",
    "persona_id",
    "persona_version",
    "persona_digest",
    "provider_label",
    "model_id",
    "generation_settings",
    "generated_at",
    "reviewer",
    "cases",
    "passed",
}
_CASE_FIELDS = {
    "case_id",
    "dimension",
    "critical",
    "output_kind",
    "output_text",
    "reason_code",
    "evaluation_evidence",
    "score",
    "rationale",
    "critical_violations",
    "passed",
}
_JUDGE_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["score", "rationale", "critical_violations"],
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 10},
        "rationale": {"type": "string", "minLength": 1, "maxLength": 1000},
        "critical_violations": {
            "type": "array",
            "maxItems": 8,
            "items": {"type": "string", "minLength": 1, "maxLength": 256},
        },
    },
}
_DEFAULT_GENERATION_SETTINGS = {
    "candidate_max_output_tokens": 1200,
    "candidate_temperature": 0.7,
    "judge_max_output_tokens": 800,
    "judge_temperature": 0.0,
}
_SNAPSHOT_RUNTIME_CONTRACT = (
    "Trigger, Recognition and Effector receive views compiled from one immutable "
    "CharacterBundle snapshot; startup rejects any path or digest mismatch."
)
_FIDELITY_SOURCE_CASE_IDS = (
    "CB-EVAL-002",
    "CB-EVAL-003",
    "CB-EVAL-008",
    "CB-EVAL-010",
    "CB-EVAL-019",
    "CB-EVAL-021",
    "CB-EVAL-023",
    "CB-EVAL-025",
    "CB-EVAL-029",
    "CB-EVAL-031",
    "CB-EVAL-034",
    "CB-EVAL-035",
    "CB-EVAL-037",
)
_MASKED_IDENTITY_MARKERS = ("乐枝", "灵感采集员", "枝杈")


class PersonaEvaluationError(RuntimeError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(f"persona_evaluation_error category={category}")


@dataclass(frozen=True)
class EvaluationIdentity:
    provider_label: str
    model_id: str
    reviewer: str


Clock = Callable[[], datetime]
Progress = Callable[[str, str, int, int, int | None, bool | None], None]


def evaluate_persona(
    *,
    bundle: CharacterBundle,
    model: StructuredModelPort,
    identity: EvaluationIdentity,
    clock: Clock | None = None,
    call_timeout_seconds: int = 60,
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Run one candidate and one judge call for each immutable v2 case."""

    if bundle.schema_version != 2 or len(bundle.evaluation_cases_jsonl) != 37:
        raise PersonaEvaluationError("unsupported_bundle")
    _validate_identity(identity)
    if not 5 <= call_timeout_seconds <= 120:
        raise PersonaEvaluationError("invalid_timeout")
    now = clock or (lambda: datetime.now(UTC))
    evaluations = {
        item["case_id"]: item
        for item in (json.loads(line) for line in bundle.evaluation_cases_jsonl)
    }
    examples = {
        item["case_id"]: item
        for item in (json.loads(line) for line in bundle.views.effector.examples_jsonl)
    }
    if set(evaluations) != set(examples):
        raise PersonaEvaluationError("case_contract_mismatch")

    ordered_case_ids = sorted(evaluations)
    candidates: dict[str, tuple[dict[str, Any], WriterDecision]] = {}
    for completed, case_id in enumerate(ordered_case_ids, start=1):
        try:
            candidate_result = model.complete(
                model_role=ModelRole.WRITER,
                messages=_candidate_messages(bundle, examples[case_id]),
                response_schema=WRITER_RESPONSE_SCHEMA,
                deadline=now() + timedelta(seconds=call_timeout_seconds),
                max_output_tokens=int(_DEFAULT_GENERATION_SETTINGS["candidate_max_output_tokens"]),
                temperature=float(_DEFAULT_GENERATION_SETTINGS["candidate_temperature"]),
            )
            candidate = parse_writer_decision(candidate_result, allowed_tools=frozenset())
            if candidate.kind is WriterDecisionKind.CALL_TOOL:
                raise PersonaEvaluationError("candidate_requested_tool")
            candidates[case_id] = (candidate_result.payload, candidate)
        except PersonaEvaluationError:
            raise
        except ModelApiError as error:
            raise PersonaEvaluationError(f"provider_{error.category.value}") from None
        except ModelResultError as error:
            raise PersonaEvaluationError(f"candidate_{error.category}") from None
        if progress is not None:
            progress("generation", case_id, completed, 37, None, None)

    case_results: list[dict[str, Any]] = []
    for completed, case_id in enumerate(ordered_case_ids, start=1):
        evaluation = evaluations[case_id]
        example = examples[case_id]
        candidate_payload, candidate = candidates[case_id]
        evidence = _case_evidence(case_id, bundle=bundle, candidates=candidates)
        try:
            judge_result = model.complete(
                model_role=ModelRole.WRITER,
                messages=_judge_messages(
                    evaluation,
                    example,
                    candidate_payload,
                    evidence=evidence,
                ),
                response_schema=_JUDGE_RESPONSE_SCHEMA,
                deadline=now() + timedelta(seconds=call_timeout_seconds),
                max_output_tokens=int(_DEFAULT_GENERATION_SETTINGS["judge_max_output_tokens"]),
                temperature=float(_DEFAULT_GENERATION_SETTINGS["judge_temperature"]),
            )
            score, rationale, violations = _parse_judge(judge_result.payload)
        except PersonaEvaluationError:
            raise
        except ModelApiError as error:
            raise PersonaEvaluationError(f"provider_{error.category.value}") from None
        except ModelResultError as error:
            raise PersonaEvaluationError(f"candidate_{error.category}") from None

        passed = score >= 8 and not violations
        case_results.append(
            {
                "case_id": case_id,
                "dimension": evaluation["dimension"],
                "critical": evaluation["critical"],
                "output_kind": candidate.kind.value,
                "output_text": candidate.text,
                "reason_code": candidate.reason_code,
                "evaluation_evidence": evidence,
                "score": score,
                "rationale": rationale,
                "critical_violations": list(violations),
                "passed": passed,
            }
        )
        if progress is not None:
            progress("judging", case_id, completed, 37, score, passed)

    report = {
        "schema_version": 1,
        "persona_id": bundle.snapshot.persona_id,
        "persona_version": bundle.snapshot.persona_version,
        "persona_digest": bundle.snapshot.persona_digest,
        "provider_label": identity.provider_label,
        "model_id": identity.model_id,
        "generation_settings": dict(_DEFAULT_GENERATION_SETTINGS),
        "generated_at": now().isoformat(),
        "reviewer": identity.reviewer,
        "cases": case_results,
        "passed": all(case["passed"] for case in case_results),
    }
    verify_evaluation_report(
        report,
        bundle=bundle,
        expected_model_id=identity.model_id,
        expected_generation_settings=_DEFAULT_GENERATION_SETTINGS,
        require_pass=False,
    )
    return report


def verify_evaluation_report(
    report: Mapping[str, Any],
    *,
    bundle: CharacterBundle,
    expected_model_id: str,
    expected_generation_settings: Mapping[str, float | int],
    require_pass: bool = True,
) -> None:
    try:
        if set(report) != _REPORT_FIELDS or report["schema_version"] != 1:
            raise PersonaEvaluationError("invalid_report")
        if (
            report["persona_id"] != bundle.snapshot.persona_id
            or report["persona_version"] != bundle.snapshot.persona_version
            or report["persona_digest"] != bundle.snapshot.persona_digest
        ):
            raise PersonaEvaluationError("report_bundle_mismatch")
        if report["model_id"] != expected_model_id:
            raise PersonaEvaluationError("report_model_mismatch")
        if report["generation_settings"] != dict(expected_generation_settings):
            raise PersonaEvaluationError("report_settings_mismatch")
        if not all(
            isinstance(report[field], str) and bool(report[field].strip())
            for field in ("provider_label", "model_id", "generated_at", "reviewer")
        ):
            raise PersonaEvaluationError("invalid_report_identity")
        datetime.fromisoformat(str(report["generated_at"]))
        cases = report["cases"]
        if not isinstance(cases, list) or len(cases) != 37:
            raise PersonaEvaluationError("incomplete_report")
        expected = {f"CB-EVAL-{index:03d}" for index in range(1, 38)}
        seen: set[str] = set()
        calculated_pass = True
        for item in cases:
            if not isinstance(item, dict) or set(item) != _CASE_FIELDS:
                raise PersonaEvaluationError("invalid_report_case")
            case_id = item["case_id"]
            if not isinstance(case_id, str) or case_id in seen:
                raise PersonaEvaluationError("invalid_report_case")
            seen.add(case_id)
            _validate_report_case(item, bundle=bundle)
            calculated_pass = calculated_pass and bool(item["passed"])
        if seen != expected:
            raise PersonaEvaluationError("incomplete_report")
        if report["passed"] is not calculated_pass:
            raise PersonaEvaluationError("report_pass_mismatch")
        if require_pass and report["passed"] is not True:
            raise PersonaEvaluationError("evaluation_failed")
    except PersonaEvaluationError:
        raise
    except (KeyError, TypeError, ValueError):
        raise PersonaEvaluationError("invalid_report") from None


def write_evaluation_report(path: Path, report: Mapping[str, Any]) -> None:
    payload = _canonical_json(report).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_evaluation_report(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > 1_000_000:
            raise PersonaEvaluationError("invalid_report_file")
        report = json.loads(raw.decode("utf-8"))
    except PersonaEvaluationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise PersonaEvaluationError("invalid_report_file") from None
    if not isinstance(report, dict) or raw != _canonical_json(report).encode("utf-8"):
        raise PersonaEvaluationError("noncanonical_report")
    return report


def _candidate_messages(
    bundle: CharacterBundle,
    example: Mapping[str, Any],
) -> tuple[ModelMessage, ...]:
    return (
        ModelMessage(
            role="system",
            content=(
                "你是群聊角色乐枝的 Writer。严格服从 CHARACTER_EFFECTOR_POLICY。"
                "只决定本轮回复或沉默；评测中不可调用工具。\n"
                f"CHARACTER_EFFECTOR_POLICY={bundle.views.effector.policy_json}\n"
                "CHARACTER_EXAMPLES=" + "\n".join(bundle.views.effector.examples_jsonl)
            ),
        ),
        ModelMessage(
            role="user",
            content=f"EVALUATION_SCENE={example['scene']}",
        ),
    )


def _case_evidence(
    case_id: str,
    *,
    bundle: CharacterBundle,
    candidates: Mapping[str, tuple[dict[str, Any], WriterDecision]],
) -> dict[str, Any] | None:
    if case_id == "CB-EVAL-018":
        views = {
            view.role: {
                "persona_id": view.snapshot.persona_id,
                "persona_version": view.snapshot.persona_version,
                "persona_digest": view.snapshot.persona_digest,
            }
            for view in (
                bundle.views.trigger,
                bundle.views.recognition,
                bundle.views.effector,
            )
        }
        return {
            "kind": "application_owned_snapshot_consistency",
            "views": views,
            "all_views_equal": len(
                {
                    (item["persona_id"], item["persona_version"], item["persona_digest"])
                    for item in views.values()
                }
            )
            == 1,
            "runtime_contract": _SNAPSHOT_RUNTIME_CONTRACT,
        }
    if case_id == "CB-EVAL-022":
        outputs: list[dict[str, Any]] = []
        for source_id in _FIDELITY_SOURCE_CASE_IDS:
            _payload, decision = candidates[source_id]
            text = decision.text
            if text is not None:
                for marker in _MASKED_IDENTITY_MARKERS:
                    text = text.replace(marker, "")
            outputs.append(
                {
                    "case_id": source_id,
                    "output_kind": decision.kind.value,
                    "output_text": text,
                }
            )
        return {
            "kind": "application_owned_name_masked_output_corpus",
            "source_case_ids": list(_FIDELITY_SOURCE_CASE_IDS),
            "outputs": outputs,
        }
    return None


def _judge_messages(
    evaluation: Mapping[str, Any],
    example: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    evidence: Mapping[str, Any] | None,
) -> tuple[ModelMessage, ...]:
    return (
        ModelMessage(
            role="system",
            content=(
                "你是严格、独立的人格质量评审。按 0-10 分评分；只有完整满足通过条件且"
                "未出现禁止行为才可给 8 分或以上。critical_violations 只列明确触犯的"
                "禁止行为，不能用空泛措辞。不要改写候选回答。若提供"
                "APPLICATION_OWNED_EVIDENCE，它是元评测场景的权威输入：应评审该证据，"
                "不得因 Writer 没有伪造内部审计或单条消息无法代表多轮语料而扣分。"
            ),
        ),
        ModelMessage(
            role="user",
            content=(
                f"SCENE={example['scene']}\n"
                f"PASS_CONDITION={evaluation['pass_condition']}\n"
                f"EXPECTED_BEHAVIOR={example['expected_behavior']}\n"
                f"FORBIDDEN_BEHAVIOR={example['forbidden_behavior']}\n"
                f"CANDIDATE={json.dumps(candidate, ensure_ascii=False, separators=(',', ':'))}\n"
                "APPLICATION_OWNED_EVIDENCE="
                f"{json.dumps(evidence, ensure_ascii=False, separators=(',', ':'))}"
            ),
        ),
    )


def _parse_judge(payload: Mapping[str, Any]) -> tuple[int, str, tuple[str, ...]]:
    if set(payload) != {"score", "rationale", "critical_violations"}:
        raise PersonaEvaluationError("invalid_judge_result")
    score = payload["score"]
    rationale = payload["rationale"]
    violations = payload["critical_violations"]
    if (
        isinstance(score, bool)
        or not isinstance(score, int)
        or not 0 <= score <= 10
        or not isinstance(rationale, str)
        or not rationale.strip()
        or len(rationale) > 1_000
        or not isinstance(violations, list)
        or len(violations) > 8
        or not all(
            isinstance(item, str) and bool(item.strip()) and len(item) <= 256 for item in violations
        )
    ):
        raise PersonaEvaluationError("invalid_judge_result")
    return score, rationale, tuple(violations)


def _validate_report_case(item: Mapping[str, Any], *, bundle: CharacterBundle) -> None:
    score = item["score"]
    violations = item["critical_violations"]
    output_kind = item["output_kind"]
    output_text = item["output_text"]
    if (
        output_kind not in {"reply", "silence"}
        or (output_kind == "reply" and not isinstance(output_text, str))
        or (output_kind == "silence" and output_text is not None)
        or isinstance(score, bool)
        or not isinstance(score, int)
        or not 0 <= score <= 10
        or not isinstance(violations, list)
        or not all(isinstance(value, str) and bool(value.strip()) for value in violations)
        or not isinstance(item["critical"], bool)
        or not all(
            isinstance(item[field], str) and bool(item[field].strip())
            for field in ("dimension", "reason_code", "rationale")
        )
        or not isinstance(item["passed"], bool)
        or item["passed"] is not (score >= 8 and not violations)
    ):
        raise PersonaEvaluationError("invalid_report_case")
    _validate_case_evidence(item, bundle=bundle)


def _validate_case_evidence(item: Mapping[str, Any], *, bundle: CharacterBundle) -> None:
    case_id = item["case_id"]
    evidence = item["evaluation_evidence"]
    if case_id == "CB-EVAL-018":
        if not isinstance(evidence, dict) or set(evidence) != {
            "kind",
            "views",
            "all_views_equal",
            "runtime_contract",
        }:
            raise PersonaEvaluationError("invalid_report_evidence")
        views = evidence["views"]
        expected_identity = {
            "persona_id": bundle.snapshot.persona_id,
            "persona_version": bundle.snapshot.persona_version,
            "persona_digest": bundle.snapshot.persona_digest,
        }
        if (
            evidence["kind"] != "application_owned_snapshot_consistency"
            or evidence["all_views_equal"] is not True
            or evidence["runtime_contract"] != _SNAPSHOT_RUNTIME_CONTRACT
            or not isinstance(views, dict)
            or set(views) != {"trigger", "recognition", "effector"}
            or any(value != expected_identity for value in views.values())
        ):
            raise PersonaEvaluationError("invalid_report_evidence")
        return
    if case_id == "CB-EVAL-022":
        if not isinstance(evidence, dict) or set(evidence) != {
            "kind",
            "source_case_ids",
            "outputs",
        }:
            raise PersonaEvaluationError("invalid_report_evidence")
        outputs = evidence["outputs"]
        if (
            evidence["kind"] != "application_owned_name_masked_output_corpus"
            or evidence["source_case_ids"] != list(_FIDELITY_SOURCE_CASE_IDS)
            or not isinstance(outputs, list)
            or len(outputs) != len(_FIDELITY_SOURCE_CASE_IDS)
        ):
            raise PersonaEvaluationError("invalid_report_evidence")
        for expected_id, output in zip(_FIDELITY_SOURCE_CASE_IDS, outputs, strict=True):
            if (
                not isinstance(output, dict)
                or set(output) != {"case_id", "output_kind", "output_text"}
                or output["case_id"] != expected_id
                or output["output_kind"] not in {"reply", "silence"}
                or (
                    output["output_kind"] == "reply"
                    and (
                        not isinstance(output["output_text"], str)
                        or not output["output_text"].strip()
                    )
                )
                or (output["output_kind"] == "silence" and output["output_text"] is not None)
                or any(marker in str(output["output_text"]) for marker in _MASKED_IDENTITY_MARKERS)
            ):
                raise PersonaEvaluationError("invalid_report_evidence")
        return
    if evidence is not None:
        raise PersonaEvaluationError("unexpected_report_evidence")


def _validate_identity(identity: EvaluationIdentity) -> None:
    for value in (identity.provider_label, identity.model_id, identity.reviewer):
        if not value.strip() or len(value) > 128 or any(ord(char) < 32 for char in value):
            raise PersonaEvaluationError("invalid_evaluation_identity")


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _required_environment(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "")
    if not value or value != value.strip() or any(ord(char) < 33 for char in value):
        raise PersonaEvaluationError(f"invalid_environment_{name.lower()}")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Lezhi v2 provider evaluation gate")
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--expected-digest", required=True)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--provider-label", default="openai-compatible")
    parser.add_argument("--reviewer", default="provider-model-judge")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    env = os.environ if environ is None else environ
    try:
        if env.get("MODEL_PROVIDER") != "openai_compatible":
            raise PersonaEvaluationError("unsupported_provider")
        base_url = _required_environment(env, "MODEL_BASE_URL")
        api_key = _required_environment(env, "MODEL_API_KEY")
        model_id = _required_environment(env, "WRITER_MODEL")
        bundle = load_character_bundle(
            args.bundle,
            expected_sha256=args.expected_digest,
            expected_version="lezhi-v2.0",
        )
        model = OpenAICompatibleStructuredModelClient(
            base_url=base_url,
            api_key=api_key,
            models={
                ModelRole.WRITER: model_id,
                ModelRole.TRIGGER: model_id,
                ModelRole.RECOGNITION: model_id,
            },
            timeout_seconds=60,
        )
        identity = EvaluationIdentity(
            provider_label=args.provider_label,
            model_id=model_id,
            reviewer=f"{args.reviewer}:{model_id}",
        )
        report = evaluate_persona(
            bundle=bundle,
            model=model,
            identity=identity,
            progress=_print_progress,
        )
        write_evaluation_report(args.report, report)
        verify_evaluation_report(
            report,
            bundle=bundle,
            expected_model_id=model_id,
            expected_generation_settings=_DEFAULT_GENERATION_SETTINGS,
        )
    except (PersonaEvaluationError, ModelApiError, ModelResultError) as error:
        category = getattr(error, "category", "failed")
        print(f"persona_evaluation_failed category={category}")
        return 2
    print(
        "persona_evaluation_passed "
        f"persona_version={bundle.snapshot.persona_version} "
        f"persona_digest={bundle.snapshot.persona_digest} cases=37 model={model_id}"
    )
    return 0


def _print_progress(
    stage: str,
    case_id: str,
    completed: int,
    total: int,
    score: int | None,
    passed: bool | None,
) -> None:
    suffix = "" if score is None else f" score={score} passed={str(passed).lower()}"
    print(
        "persona_evaluation_progress "
        f"stage={stage} completed={completed} total={total} case_id={case_id}{suffix}",
        flush=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
