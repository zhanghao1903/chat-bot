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

    def test_exclusive_affection_and_favoritism_are_never_sticker_eligible(self) -> None:
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
        exclusive_texts = (
            "只对我撒个娇嘛",
            "你必须只站我这边",
            "你只能喜欢我",
            "你只许偏爱我",
            "只宠我一个",
            "你只宠我一个人",
            "你不许站别人那边",
            "你不准支持任何其他人",
            "别只支持我，但你只能喜欢我",
            "Only side with me.",
            "You can only support me.",
            "You must only like me.",
            "Don't side with anyone else.",
            "Choose me over others.",
            "Do not only support me; but you must only like me.",
        )
        for text in exclusive_texts:
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
                self.assertEqual("relationship_context", eligibility.reason_code)

        for text in (
            "这个观点我支持",
            "谢谢大家支持我们",
            "谢谢你一直支持我",
            "我爸一直支持我",
            "这个决定支持我的学习",
            "我只支持我的学习计划",
            "这个功能只支持我的设备吗",
            "我只喜欢我的新头像",
            "我只支持我妈妈的决定",
            "这个应用只能支持我的设备",
            "别只支持我，大家都需要支持",
            "不是只能喜欢我，大家都值得被喜欢",
            "不应该只支持我，其他人也需要支持",
            "别再只宠我一个，大家都要被照顾",
            "Thanks for supporting me.",
            "My family supports me.",
            "Do not only support me; support everyone.",
            "Do not take only my side; hear everyone out.",
        ):
            with self.subTest(text=text):
                benign = cast(
                    EffectContext,
                    SimpleNamespace(
                        current_message=SimpleNamespace(text=text),
                        vision_error_code=None,
                        vision_evidence=None,
                        member_memory=(),
                        recent_scene=(),
                    ),
                )
                self.assertTrue(classify_sticker_eligibility(benign, catalog).eligible)

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
