from __future__ import annotations

import unittest

from group_llm_agent.model import (
    ModelResultError,
    StructuredModelResult,
    WriterDecisionKind,
    parse_writer_decision,
)
from group_llm_agent.temporal import FreshnessMode, SELECT_ANSWER_TIMEZONE
from group_llm_agent.writer_contract import WRITER_RESPONSE_SCHEMA

_CONTEXT_ID = "time:v1:" + "a" * 64


class WriterTemporalContractTests(unittest.TestCase):
    def test_every_schema_branch_requires_temporal_context_identity(self) -> None:
        branches = WRITER_RESPONSE_SCHEMA["oneOf"]
        self.assertEqual(6, len(branches))
        for branch in branches:
            with self.subTest(kind=branch["properties"]["kind"]):
                self.assertIn("temporal_context_id", branch["required"])

    def test_reply_freshness_modes_and_source_cardinality_are_closed(self) -> None:
        for mode, sources in (
            ("stable", []),
            ("clock", []),
            ("current_verified", ["web:1", "web:2"]),
            ("current_unverified", []),
        ):
            with self.subTest(mode=mode):
                decision = parse_writer_decision(
                    StructuredModelResult(
                        {
                            "kind": "reply",
                            "reason_code": "answer",
                            "temporal_context_id": _CONTEXT_ID,
                            "text": "answer",
                            "freshness": {
                                "mode": mode,
                                "source_result_ids": sources,
                            },
                        }
                    ),
                    allowed_tools=frozenset(),
                    expected_temporal_context_id=_CONTEXT_ID,
                )
                self.assertEqual(FreshnessMode(mode), decision.freshness_mode)
                self.assertEqual(tuple(sources), decision.source_result_ids)

        invalid = (
            {"mode": "stable", "source_result_ids": ["web:1"]},
            {"mode": "clock", "source_result_ids": ["web:1"]},
            {"mode": "current_verified", "source_result_ids": []},
            {"mode": "current_verified", "source_result_ids": ["web:1", "web:1"]},
            {
                "mode": "current_verified",
                "source_result_ids": ["web:1", "web:2", "web:3", "web:4"],
            },
        )
        for freshness in invalid:
            with self.subTest(freshness=freshness), self.assertRaises(ModelResultError):
                parse_writer_decision(
                    StructuredModelResult(
                        {
                            "kind": "reply",
                            "reason_code": "answer",
                            "temporal_context_id": _CONTEXT_ID,
                            "text": "answer",
                            "freshness": freshness,
                        }
                    ),
                    allowed_tools=frozenset(),
                    expected_temporal_context_id=_CONTEXT_ID,
                )

    def test_stale_or_missing_temporal_identity_is_rejected(self) -> None:
        payload = {
            "kind": "silence",
            "reason_code": "quiet",
            "temporal_context_id": "time:v1:" + "b" * 64,
        }
        with self.assertRaisesRegex(ModelResultError, "stale_temporal_context"):
            parse_writer_decision(
                StructuredModelResult(payload),
                allowed_tools=frozenset(),
                expected_temporal_context_id=_CONTEXT_ID,
            )
        del payload["temporal_context_id"]
        with self.assertRaises(ModelResultError):
            parse_writer_decision(
                StructuredModelResult(payload),
                allowed_tools=frozenset(),
                expected_temporal_context_id=_CONTEXT_ID,
            )

    def test_timezone_selection_tool_keeps_current_context_identity(self) -> None:
        decision = parse_writer_decision(
            StructuredModelResult(
                {
                    "kind": "call_tool",
                    "reason_code": "explicit_zone",
                    "temporal_context_id": _CONTEXT_ID,
                    "tool_name": SELECT_ANSWER_TIMEZONE,
                    "tool_arguments": {"timezone": "America/New_York"},
                    "tool_purpose_code": "answer_timezone",
                }
            ),
            allowed_tools=frozenset({SELECT_ANSWER_TIMEZONE}),
            expected_temporal_context_id=_CONTEXT_ID,
        )
        self.assertEqual(WriterDecisionKind.CALL_TOOL, decision.kind)
        self.assertEqual(_CONTEXT_ID, decision.temporal_context_id)


if __name__ == "__main__":
    unittest.main()
