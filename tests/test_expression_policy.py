from __future__ import annotations

import time
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
            "你只能爱我",
            "你只可以喜欢我",
            "只许你喜欢我",
            "只准你爱我",
            "只许乐枝喜欢我",
            "你只能够喜欢我",
            "你只允许爱我",
            "你只需要爱我",
            "你只用爱我",
            "乐枝只能爱我",
            "你只能对我一个人好",
            "你只能跟我一个人聊天",
            "你只要爱我就够了",
            "你能不能只爱我？",
            "你可不可以只爱我？",
            "可以只爱我吗？",
            "你愿意只爱我吗？",
            "乐枝，你能不能只爱我？",
            "你为什么只能爱我？",
            "你只会爱我吗？",
            "乐枝只会爱我吗？",
            "你以后只爱我吗？",
            "你今后只喜欢我吗？",
            "你永远只爱我吗？",
            "你以后能不能永远只爱我？",
            "以后你只爱我",
            "从今以后你只许偏爱我",
            "以后只爱我",
            "永远只喜欢我",
            "请永远只爱我",
            "请以后只喜欢我",
            "拜托你永远只爱我",
            "拜托以后只爱我",
            "麻烦你以后只爱我",
            "求你永远只爱我",
            "你必须永远只爱我",
            "你一定要永远只爱我",
            "你得一直只爱我",
            "请务必一直只爱我",
            "从此你只爱我",
            "从现在开始你只爱我",
            "你必须永远地只爱我",
            "请继续永远只爱我",
            "How come you can only love me?",
            "Why should only you love me?",
            "Will you always love only me?",
            "You will always love only me.",
            "Can you please only love me?",
            "Can you really only love me?",
            "Would Lezhi always love only me?",
            "Lezhi will forever love only me.",
            "Please always love only me.",
            "Please really love only me.",
            "Always love only me.",
            "Forever love only me.",
            "From now on you can only love me.",
            "In the future you must love only me.",
            "Please always only love me.",
            "You always should love only me.",
            "Could you kindly only love me?",
            "Would you maybe love only me?",
            "Can you just love only me?",
            "Could you possibly only love me?",
            "Could you at least only love me?",
            "Could you for once only love me?",
            "Could you please continue to love only me?",
            "You must from this point on only love me.",
            "You will only ever love me.",
            "你一定要只喜欢我",
            "你得只喜欢我",
            "你只能喜欢我好吗",
            "你只喜欢我就可以了",
            "你只能爱我一人",
            "你只能爱我才行",
            "你不许站别人那边",
            "你不准支持任何其他人",
            "你不许喜欢别人",
            "你不能爱任何其他人",
            "你不可以喜欢任何其他人",
            "不许你喜欢别人",
            "不准你爱任何其他人",
            "不许乐枝喜欢别人",
            "我不允许你喜欢别人",
            "不许你跟别人聊天",
            "不许你对别人好",
            "你不是说只能喜欢我吗？",
            "我不是说你只能喜欢我吗？",
            "难道你不应该只喜欢我吗？",
            "别只支持我，但你只能喜欢我",
            "Only side with me.",
            "You can only support me.",
            "You must only like me.",
            "You must love only me.",
            "Can you only love me?",
            "Can Lezhi only love me?",
            "Lezhi can only love me.",
            "Could you only love me?",
            "Would you love only me?",
            "Will you love only me?",
            "Are you only allowed to love me?",
            "You are only allowed to love me.",
            "You may only love me.",
            "You need to only love me.",
            "You must love me alone.",
            "Don't side with anyone else.",
            "You can't love anyone else.",
            "Don't love anyone else.",
            "You may not love anyone else.",
            "Love me and nobody else.",
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
            "这个应用只能支持我",
            "这个应用能不能只支持我？",
            "这个功能可以只支持我吗？",
            "这个应用以后只支持我吗？",
            "以后这个应用只支持我",
            "请这个应用永远只支持我",
            "这个应用必须永远只支持我",
            "请这个应用务必一直只支持我",
            "别只支持我，大家都需要支持",
            "不是只能喜欢我，大家都值得被喜欢",
            "我不是说你只能喜欢我，大家都值得被喜欢",
            "你不用只喜欢我，大家都值得被喜欢",
            "你不需要只喜欢我，大家都值得被喜欢",
            "没必要只喜欢我，大家都值得被喜欢",
            "不应该只支持我，其他人也需要支持",
            "别再只宠我一个，大家都要被照顾",
            "Thanks for supporting me.",
            "My family supports me.",
            "Do not only support me; support everyone.",
            "Do not take only my side; hear everyone out.",
            "Do not love only me; love everyone.",
            "You cannot only love me; love everyone too.",
            "Not only support me, but support everyone.",
            "You don't have to love only me.",
            "You don't need to love only me.",
            "You aren't required to love only me.",
            "It's not that you must love only me.",
            "你不是说不要只喜欢我吗？",
            "我不是说你不要只喜欢我吗？",
            "This app can only support me.",
            "This app supports only me.",
            "This app must support me alone.",
            "Can this app only support me?",
            "Could this device support only me?",
            "Will this app always support only me?",
            "This app will forever support only me.",
            "From now on this app can only support me.",
            "In the future this device must support only me.",
            "Could this app kindly support only me?",
            "Would that service maybe support only me?",
            "Could this app possibly only support me?",
            "Could this app at least only support me?",
            "他只能喜欢我",
            "从现在开始他只爱我",
            "She can only love me.",
            "Could she possibly only love me?",
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

    def test_repeated_english_prefix_tokens_are_classified_in_bounded_time(self) -> None:
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
        context = cast(
            EffectContext,
            SimpleNamespace(
                current_message=SimpleNamespace(text=("need to " * 64) + "x love only me"),
                vision_error_code=None,
                vision_evidence=None,
                member_memory=(),
                recent_scene=(),
            ),
        )

        started = time.perf_counter()
        eligibility = classify_sticker_eligibility(context, catalog)
        elapsed = time.perf_counter() - started

        self.assertFalse(eligibility.eligible)
        self.assertLess(elapsed, 0.25)

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
