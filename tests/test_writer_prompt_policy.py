from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import cast

from group_llm_agent.context import EffectContext
from group_llm_agent.events import TriggerPath
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


if __name__ == "__main__":
    unittest.main()
