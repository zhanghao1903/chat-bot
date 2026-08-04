from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

from group_llm_agent.context import EffectContext
from group_llm_agent.expression_policy import _last_outbound_sticker
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
