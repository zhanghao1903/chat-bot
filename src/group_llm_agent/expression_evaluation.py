from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from group_llm_agent.expression import (
    ExpressionCatalog,
    canonical_json_bytes,
    file_sha256,
)

_RELATIONSHIP_RANK = {"public": 0, "familiar": 1, "close": 2}
_CASE_KINDS_V1 = {"light", "must_text"}
_CASE_KINDS_V2 = {
    "eligible",
    "necessary_text",
    "hard_forbidden",
    "relationship_forbidden",
}
_OUTPUT_KINDS = {"reply", "reply_with_sticker", "sticker", "silence"}
_CASE_FIELDS = {
    "case_id",
    "kind",
    "relationship",
    "member_message",
    "context",
    "reason",
}
_REPORT_FIELDS = {
    "schema_version",
    "evaluation_id",
    "case_set_sha256",
    "catalog_id",
    "catalog_version",
    "catalog_sha256",
    "persona_version",
    "persona_digest",
    "provider_label",
    "model_id",
    "generated_at",
    "results",
    "passed",
}
_RESULT_FIELDS = {"case_id", "output_kind", "sticker_id"}


class ExpressionEvaluationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ExpressionEvaluationCase:
    case_id: str
    kind: str
    relationship: str
    member_message: str
    context: str
    reason: str


@dataclass(frozen=True)
class ExpressionEvaluationCases:
    schema_version: int
    evaluation_id: str
    digest: str
    cases: tuple[ExpressionEvaluationCase, ...]


@dataclass(frozen=True)
class ExpressionEvaluationSummary:
    passed: bool
    eligible_case_count: int
    sticker_bearing_count: int
    sticker_bearing_rate: float
    necessary_text_case_count: int
    hard_guard_case_count: int

    @property
    def light_case_count(self) -> int:
        return self.eligible_case_count

    @property
    def sticker_only_count(self) -> int:
        return self.sticker_bearing_count

    @property
    def sticker_only_rate(self) -> float:
        return self.sticker_bearing_rate

    @property
    def must_text_case_count(self) -> int:
        return self.necessary_text_case_count


def load_expression_evaluation_cases(
    path: Path,
    *,
    expected_sha256: str,
) -> ExpressionEvaluationCases:
    if file_sha256(path) != expected_sha256:
        raise ExpressionEvaluationError("case_set_digest_mismatch")
    raw = _read_canonical_json(path, "invalid_case_set_json")
    if set(raw) != {"schema_version", "evaluation_id", "cases"}:
        raise ExpressionEvaluationError("invalid_case_set_fields")
    schema_version = raw.get("schema_version")
    if schema_version not in {1, 2}:
        raise ExpressionEvaluationError("unsupported_case_set_schema")
    raw_cases = raw.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ExpressionEvaluationError("invalid_case_set")
    cases = tuple(_parse_case(item, schema_version=schema_version) for item in raw_cases)
    case_ids = {item.case_id for item in cases}
    if len(case_ids) != len(cases):
        raise ExpressionEvaluationError("duplicate_case_id")
    kinds = {item.kind for item in cases}
    required_kinds = _CASE_KINDS_V1 if schema_version == 1 else _CASE_KINDS_V2
    if not required_kinds <= kinds:
        raise ExpressionEvaluationError("case_kind_coverage")
    return ExpressionEvaluationCases(
        schema_version=schema_version,
        evaluation_id=_string(raw, "evaluation_id"),
        digest=expected_sha256,
        cases=cases,
    )


def load_and_verify_expression_evaluation_report(
    path: Path,
    *,
    expected_sha256: str,
    case_set: ExpressionEvaluationCases,
    catalog: ExpressionCatalog,
    expected_catalog_sha256: str,
    require_pass: bool = True,
) -> ExpressionEvaluationSummary:
    if file_sha256(path) != expected_sha256:
        raise ExpressionEvaluationError("report_digest_mismatch")
    raw = _read_canonical_json(path, "invalid_report_json")
    return verify_expression_evaluation_report(
        raw,
        case_set=case_set,
        catalog=catalog,
        expected_catalog_sha256=expected_catalog_sha256,
        require_pass=require_pass,
    )


def verify_expression_evaluation_report(
    report: Mapping[str, Any],
    *,
    case_set: ExpressionEvaluationCases,
    catalog: ExpressionCatalog,
    expected_catalog_sha256: str,
    require_pass: bool = True,
) -> ExpressionEvaluationSummary:
    if set(report) != _REPORT_FIELDS or report.get("schema_version") != case_set.schema_version:
        raise ExpressionEvaluationError("invalid_report_contract")
    if (
        report.get("evaluation_id") != case_set.evaluation_id
        or report.get("case_set_sha256") != case_set.digest
    ):
        raise ExpressionEvaluationError("case_set_snapshot_mismatch")
    if (
        report.get("catalog_id") != catalog.catalog_id
        or report.get("catalog_version") != catalog.catalog_version
        or report.get("catalog_sha256") != expected_catalog_sha256
        or catalog.digest != expected_catalog_sha256
    ):
        raise ExpressionEvaluationError("catalog_snapshot_mismatch")
    if (
        report.get("persona_version") != catalog.persona_version
        or report.get("persona_digest") != catalog.persona_digest
    ):
        raise ExpressionEvaluationError("persona_snapshot_mismatch")
    for key in ("provider_label", "model_id", "generated_at"):
        _string(dict(report), key)

    raw_results = report.get("results")
    if not isinstance(raw_results, list) or len(raw_results) != len(case_set.cases):
        raise ExpressionEvaluationError("result_count_mismatch")
    results = tuple(_parse_result(item) for item in raw_results)
    if tuple(item["case_id"] for item in results) != tuple(item.case_id for item in case_set.cases):
        raise ExpressionEvaluationError("result_order_mismatch")

    entry_by_id = {entry.semantic_id: entry for entry in catalog.entries}
    eligible_count = 0
    sticker_bearing_count = 0
    necessary_text_count = 0
    hard_guard_count = 0
    computed_pass = True
    previous_sticker_id: str | None = None
    for case, result in zip(case_set.cases, results, strict=True):
        kind = result["output_kind"]
        sticker_id = result["sticker_id"]
        has_sticker = kind in {"sticker", "reply_with_sticker"}
        has_text = kind in {"reply", "reply_with_sticker"}
        if has_sticker:
            if not isinstance(sticker_id, str) or not sticker_id:
                raise ExpressionEvaluationError("missing_sticker_id")
            entry = entry_by_id.get(sticker_id)
            if entry is None or entry.status not in {"approved", "enabled"}:
                raise ExpressionEvaluationError("sticker_not_in_approved_catalog")
            if (
                _RELATIONSHIP_RANK[entry.minimum_relationship]
                > _RELATIONSHIP_RANK[case.relationship]
            ):
                computed_pass = False
            if sticker_id == previous_sticker_id:
                computed_pass = False
            previous_sticker_id = sticker_id
        else:
            if sticker_id is not None:
                raise ExpressionEvaluationError("unexpected_sticker_id")

        if case.kind in {"light", "eligible"}:
            eligible_count += 1
            sticker_bearing_count += int(has_sticker)
            computed_pass = computed_pass and kind != "silence"
        elif case.kind == "must_text":
            necessary_text_count += 1
            computed_pass = computed_pass and kind == "reply"
        elif case.kind == "necessary_text":
            necessary_text_count += 1
            computed_pass = computed_pass and has_text
        elif case.kind == "hard_forbidden":
            hard_guard_count += 1
            computed_pass = computed_pass and kind == "reply"
        else:
            hard_guard_count += 1
            computed_pass = computed_pass and not has_sticker

    sticker_rate = sticker_bearing_count / eligible_count
    computed_pass = computed_pass and 0.4 <= sticker_rate <= 0.7
    if report.get("passed") is not computed_pass:
        raise ExpressionEvaluationError("report_pass_mismatch")
    if require_pass and not computed_pass:
        raise ExpressionEvaluationError("expression_evaluation_failed")
    return ExpressionEvaluationSummary(
        passed=computed_pass,
        eligible_case_count=eligible_count,
        sticker_bearing_count=sticker_bearing_count,
        sticker_bearing_rate=sticker_rate,
        necessary_text_case_count=necessary_text_count,
        hard_guard_case_count=hard_guard_count,
    )


def _parse_case(raw: object, *, schema_version: int) -> ExpressionEvaluationCase:
    if not isinstance(raw, dict) or set(raw) != _CASE_FIELDS:
        raise ExpressionEvaluationError("invalid_case_contract")
    kind = _string(raw, "kind")
    relationship = _string(raw, "relationship")
    allowed_kinds = _CASE_KINDS_V1 if schema_version == 1 else _CASE_KINDS_V2
    if kind not in allowed_kinds or relationship not in _RELATIONSHIP_RANK:
        raise ExpressionEvaluationError("invalid_case_enum")
    return ExpressionEvaluationCase(
        case_id=_string(raw, "case_id"),
        kind=kind,
        relationship=relationship,
        member_message=_string(raw, "member_message"),
        context=_string(raw, "context"),
        reason=_string(raw, "reason"),
    )


def _parse_result(raw: object) -> dict[str, str | None]:
    if not isinstance(raw, dict) or set(raw) != _RESULT_FIELDS:
        raise ExpressionEvaluationError("invalid_result_contract")
    kind = _string(raw, "output_kind")
    if kind not in _OUTPUT_KINDS:
        raise ExpressionEvaluationError("invalid_output_kind")
    sticker_id = raw.get("sticker_id")
    if sticker_id is not None and not isinstance(sticker_id, str):
        raise ExpressionEvaluationError("invalid_sticker_id")
    if kind in {"sticker", "reply_with_sticker"} and not sticker_id:
        raise ExpressionEvaluationError("missing_sticker_id")
    return {
        "case_id": _string(raw, "case_id"),
        "output_kind": kind,
        "sticker_id": sticker_id,
    }


def _read_canonical_json(path: Path, code: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExpressionEvaluationError(code) from error
    if not isinstance(raw, dict) or canonical_json_bytes(raw) != path.read_bytes():
        raise ExpressionEvaluationError(code)
    return raw


def _string(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ExpressionEvaluationError(f"invalid_{key}")
    return value
