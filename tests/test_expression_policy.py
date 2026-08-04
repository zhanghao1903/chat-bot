from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

from group_llm_agent.context import EffectContext
from group_llm_agent.expression import ExpressionCatalog, ExpressionEntry
from group_llm_agent.expression_policy import (
    _last_outbound_sticker,
    sticker_selection_error,
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


def _catalog(*, status: str = "enabled") -> ExpressionCatalog:
    return cast(ExpressionCatalog, SimpleNamespace(status=status))


def _entry(
    *,
    semantic_id: str = "lezhi.hello_wave.a01",
    status: str = "enabled",
    relationship: str = "public",
) -> ExpressionEntry:
    return cast(
        ExpressionEntry,
        SimpleNamespace(
            semantic_id=semantic_id,
            status=status,
            minimum_relationship=relationship,
        ),
    )


def _context(
    *,
    text: str = "你好呀",
    has_memory: bool = False,
    recent_scene: tuple[StoredGroupMessage, ...] = (),
) -> EffectContext:
    member_memory = (
        (SimpleNamespace(items=(SimpleNamespace(memory_id="memory-1"),)),) if has_memory else ()
    )
    return cast(
        EffectContext,
        SimpleNamespace(
            current_message=SimpleNamespace(text=text),
            vision_error_code=None,
            vision_evidence=None,
            member_memory=member_memory,
            recent_scene=recent_scene,
        ),
    )


class ExpressionPolicyTests(unittest.TestCase):
    def test_selection_does_not_classify_natural_language(self) -> None:
        texts = (
            "发生安全事故了",
            "我需要医疗帮助",
            "你只能爱我",
            "Please always love only me.",
            "普通轻松闲聊",
            "need to " * 1_024,
        )
        for text in texts:
            with self.subTest(text=text[:40]):
                self.assertIsNone(
                    sticker_selection_error(
                        context=_context(text=text),
                        catalog=_catalog(),
                        entry=_entry(),
                    )
                )

    def test_catalog_and_entry_must_be_enabled(self) -> None:
        self.assertEqual(
            "catalog_not_enabled",
            sticker_selection_error(
                context=_context(),
                catalog=_catalog(status="approved"),
                entry=_entry(),
            ),
        )
        self.assertEqual(
            "sticker_not_enabled",
            sticker_selection_error(
                context=_context(),
                catalog=_catalog(),
                entry=_entry(status="approved"),
            ),
        )

    def test_relationship_metadata_is_enforced_without_language_parsing(self) -> None:
        self.assertEqual(
            "relationship_insufficient",
            sticker_selection_error(
                context=_context(),
                catalog=_catalog(),
                entry=_entry(relationship="familiar"),
            ),
        )
        self.assertIsNone(
            sticker_selection_error(
                context=_context(has_memory=True),
                catalog=_catalog(),
                entry=_entry(relationship="familiar"),
            )
        )
        self.assertEqual(
            "relationship_insufficient",
            sticker_selection_error(
                context=_context(has_memory=True),
                catalog=_catalog(),
                entry=_entry(relationship="close"),
            ),
        )

    def test_consecutive_repeat_is_rejected_across_intervening_text(self) -> None:
        context = _context(
            recent_scene=(
                _outbound("1", "[sticker:lezhi.hello_wave.a01]"),
                _outbound("2", "这是一条文字回复。"),
            )
        )
        self.assertEqual(
            "consecutive_repeat",
            sticker_selection_error(
                context=context,
                catalog=_catalog(),
                entry=_entry(),
            ),
        )
        self.assertEqual("lezhi.hello_wave.a01", _last_outbound_sticker(context))

    def test_only_exact_outbound_sticker_markers_affect_repeat_policy(self) -> None:
        context = _context(
            recent_scene=(
                _outbound("1", "讨论 [sticker:lezhi.hello_wave.a01]"),
                replace_direction(_outbound("2", "[sticker:lezhi.hello_wave.a01]")),
            )
        )
        self.assertIsNone(_last_outbound_sticker(context))


def replace_direction(message: StoredGroupMessage) -> StoredGroupMessage:
    return StoredGroupMessage(
        id=message.id,
        chat_id=message.chat_id,
        telegram_message_id=message.telegram_message_id,
        event_id=message.event_id,
        sender_user_id=message.sender_user_id,
        sender_display_name=message.sender_display_name,
        direction="inbound",
        text=message.text,
        sent_at=message.sent_at,
        replied_to_message_id=message.replied_to_message_id,
        replied_to_user_id=message.replied_to_user_id,
    )


if __name__ == "__main__":
    unittest.main()
