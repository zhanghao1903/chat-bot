from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

from group_llm_agent.context import EffectContext
from group_llm_agent.events import TriggerPath
from group_llm_agent.temporal import TemporalContextFactory
from group_llm_agent.writer_prompt import build_writer_model_messages


class WriterPromptPolicyTests(unittest.TestCase):
    def test_writer_owns_semantic_reply_form_without_rate_target(self) -> None:
        context = cast(
            EffectContext,
            SimpleNamespace(
                character=SimpleNamespace(examples_jsonl=(), policy_json="{}"),
                scheduled=None,
                current_message=SimpleNamespace(
                    sender_id="member-1",
                    text="今天状态不错",
                    replied_to_user_id=None,
                    timestamp=datetime(2026, 8, 11, 4, 34, 20, tzinfo=UTC),
                ),
                recent_scene=(),
                member_memory=(),
                trigger_path=TriggerPath.DIRECT,
                vision_evidence=None,
                vision_error_code=None,
            ),
        )

        messages = build_writer_model_messages(
            context,
            temporal_context=TemporalContextFactory(
                clock=lambda: datetime(2026, 8, 11, 4, 35, tzinfo=UTC)
            ).sample(group_timezone="Asia/Shanghai"),
            allowed_tools=frozenset(),
            history=(),
            tool_results=(),
            model_calls_remaining=3,
            tool_calls_remaining=0,
            web_tool_calls_remaining=0,
            catalog=None,
        )

        system = messages[0].content
        self.assertIn("sole semantic decision-maker for the final reply form", system)
        self.assertIn(
            "complete conversation, relationship, member-memory, and vision context", system
        )
        self.assertIn("naturally adds emotion or action", system)
        self.assertIn("exclusive-affection, favoritism", system)
        self.assertIn("Never choose a form to hit a rate, target, quota, or metric", system)
        self.assertNotIn("aim near 60%", system)
        self.assertNotIn("40-70%", system)
        self.assertIn("AUTHORITATIVE_TEMPORAL_CONTEXT=", system)
        self.assertIn("only source for the current instant", system)
        self.assertIn("uses no keyword classifier", system)

    def test_scene_distinguishes_current_time_from_message_occurrence_times(self) -> None:
        current_time = datetime(2026, 8, 12, 0, 5, tzinfo=UTC)
        historical_time = datetime(2026, 8, 10, 15, 50, tzinfo=UTC)
        context = cast(
            EffectContext,
            SimpleNamespace(
                character=SimpleNamespace(examples_jsonl=(), policy_json="{}"),
                scheduled=None,
                current_message=SimpleNamespace(
                    sender_id="member-1",
                    text="昨天说今晚再聊",
                    replied_to_user_id=None,
                    timestamp=datetime(2026, 8, 11, 16, 1, tzinfo=UTC),
                ),
                recent_scene=(
                    SimpleNamespace(
                        sender_user_id="member-1",
                        direction="inbound",
                        text="今晚再聊",
                        sent_at=historical_time,
                    ),
                ),
                member_memory=(),
                trigger_path=TriggerPath.DIRECT,
                vision_evidence=None,
                vision_error_code=None,
            ),
        )
        messages = build_writer_model_messages(
            context,
            temporal_context=TemporalContextFactory(clock=lambda: current_time).sample(
                group_timezone="Asia/Shanghai"
            ),
            allowed_tools=frozenset(),
            history=(),
            tool_results=(),
            model_calls_remaining=1,
            tool_calls_remaining=0,
            web_tool_calls_remaining=0,
            catalog=None,
        )
        encoded = messages[1].content.split("\n", 1)[1].rsplit("\n", 1)[0]
        scene = json.loads(encoded)
        self.assertEqual(
            "2026-08-11T16:01:00+00:00",
            scene["current_source"]["occurred_at_utc"],
        )
        self.assertEqual(
            "2026-08-10T15:50:00+00:00",
            scene["recent_scene"][0]["occurred_at_utc"],
        )
        self.assertEqual(
            "2026-08-10T23:50:00+08:00",
            scene["recent_scene"][0]["occurred_at_target_local"],
        )


if __name__ == "__main__":
    unittest.main()
