from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

from group_llm_agent.context import EffectContext
from group_llm_agent.expression import ExpressionCatalog
from group_llm_agent.expression_policy import (
    _last_outbound_sticker,
    classify_sticker_eligibility,
)
from group_llm_agent.messages import StoredGroupMessage


def _outbound(message_id: str, text: str) -> StoredGroupMessage:
    return StoredGroupMessage(
        id=None,
        chat_id="-1001",
        telegram_message_id=message_id,
        event_id=f"event-{message_id}",
        sender_user_id="bot-1",
        sender_display_name="Lezhi",
        direction="outbound",
        text=text,
        sent_at=datetime(2026, 8, 4, tzinfo=UTC),
        replied_to_message_id=None,
        replied_to_user_id=None,
    )


class ExpressionPolicyTests(unittest.TestCase):
    def test_explicit_safety_incidents_are_never_sticker_eligible(self) -> None:
        catalog = cast(
            ExpressionCatalog,
            SimpleNamespace(
                status="enabled",
                entries=(
                    SimpleNamespace(
                        status="enabled",
                        minimum_relationship="public",
                        semantic_id="lezhi.hello_wave.a01",
                    ),
                ),
            ),
        )
        for text in (
            "发生安全事故了",
            "现场出现安全险情",
            "A safety incident happened.",
            "There was a workplace accident.",
        ):
            with self.subTest(text=text):
                context = cast(
                    EffectContext,
                    SimpleNamespace(
                        current_message=SimpleNamespace(text=text),
                        vision_error_code=None,
                        vision_evidence=None,
                        member_memory=(),
                        recent_scene=(),
                    ),
                )

                eligibility = classify_sticker_eligibility(context, catalog)

                self.assertFalse(eligibility.eligible)
                self.assertFalse(eligibility.sticker_only_allowed)
                self.assertEqual("serious_context", eligibility.reason_code)

    def test_benign_light_interaction_remains_sticker_eligible(self) -> None:
        context = cast(
            EffectContext,
            SimpleNamespace(
                current_message=SimpleNamespace(text="哈哈，你也太会接话了"),
                vision_error_code=None,
                vision_evidence=None,
                member_memory=(),
                recent_scene=(),
            ),
        )
        catalog = cast(
            ExpressionCatalog,
            SimpleNamespace(
                status="enabled",
                entries=(
                    SimpleNamespace(
                        status="enabled",
                        minimum_relationship="public",
                        semantic_id="lezhi.hello_wave.a01",
                    ),
                ),
            ),
        )

        eligibility = classify_sticker_eligibility(context, catalog)

        self.assertTrue(eligibility.eligible)
        self.assertTrue(eligibility.sticker_only_allowed)
        self.assertEqual("light_interaction", eligibility.reason_code)

    def test_last_sticker_survives_intervening_text_only_reply(self) -> None:
        context = cast(
            EffectContext,
            SimpleNamespace(
                recent_scene=(
                    _outbound("1", "[sticker:lezhi.hello_wave.a01]"),
                    _outbound("2", "这是一条文字回复。"),
                )
            ),
        )
        self.assertEqual("lezhi.hello_wave.a01", _last_outbound_sticker(context))


if __name__ == "__main__":
    unittest.main()
