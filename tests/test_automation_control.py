from __future__ import annotations

import unittest
from datetime import UTC, datetime

from helpers import temporary_database

from group_llm_agent.automation import AutomationRepository
from group_llm_agent.automation_control import AutomationControlService
from group_llm_agent.events import PersonaSnapshot, TelegramTextMessage
from group_llm_agent.platforms.telegram import (
    ChatMemberStatus,
    SentMessage,
    TelegramMemberStatus,
)
from group_llm_agent.runs import RunRepository


class FakeTelegram:
    def __init__(self, *, administrator: bool = True) -> None:
        self.administrator = administrator
        self.sent: list[str] = []

    def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        reply_to_message_id: str | None = None,
    ) -> SentMessage:
        self.sent.append(text)
        return SentMessage(message_id=str(len(self.sent)))

    def get_chat_member(self, *, chat_id: str, user_id: str) -> ChatMemberStatus:
        status = (
            TelegramMemberStatus.ADMINISTRATOR
            if self.administrator
            else TelegramMemberStatus.MEMBER
        )
        return ChatMemberStatus(user_id=user_id, status=status)


def message(
    text: str, *, event_id: str = "update-1", sender_id: str = "member-1"
) -> TelegramTextMessage:
    return TelegramTextMessage(
        event_id=event_id,
        group_id="-1001",
        message_id=event_id.removeprefix("update-") or "1",
        sender_id=sender_id,
        sender_display_name="Member",
        text=text,
        timestamp=datetime(2026, 8, 3, tzinfo=UTC),
        is_bot_command=True,
    )


class AutomationControlTests(unittest.TestCase):
    def service(self, database, telegram: FakeTelegram, *, available: bool = True):
        return AutomationControlService(
            allowed_chat_id="-1001",
            bot_user_id="7",
            bot_username="lezhi_bot",
            telegram=telegram,
            repository=AutomationRepository(database),
            runs=RunRepository(database),
            capability_available=available,
        )

    def test_admin_enable_member_subscribe_status_and_unsubscribe(self) -> None:
        with temporary_database() as database:
            telegram = FakeTelegram()
            service = self.service(database, telegram)
            persona = PersonaSnapshot("lezhi", "v2", "a" * 64)
            self.assertEqual(
                "enabled",
                service.handle(message("/food_enable"), persona=persona).status,
            )
            self.assertEqual(
                "subscribed",
                service.handle(
                    message("/food_subscribe", event_id="update-2"),
                    persona=persona,
                    now=datetime(2026, 8, 3, 2, tzinfo=UTC),
                ).status,
            )
            subscription_ack = telegram.sent[-1]
            self.assertIn("当前群（-1001）", subscription_ack)
            self.assertIn("时区 Asia/Shanghai", subscription_ack)
            self.assertIn("午餐 11:30，晚餐 17:30", subscription_ack)
            self.assertIn("下一次：2026-08-03 11:30 (Asia/Shanghai)", subscription_ack)
            self.assertIn("全群合并发送最多一条", subscription_ack)
            self.assertIn("/food_unsubscribe", subscription_ack)
            status = service.handle(
                message("/food_status", event_id="update-3"),
                persona=persona,
                now=datetime(2026, 8, 3, 2, tzinfo=UTC),
            )
            self.assertEqual("status", status.status)
            self.assertIn("订阅数：1", telegram.sent[-1])
            self.assertIn("下一次：2026-08-03 11:30 (Asia/Shanghai)", telegram.sent[-1])
            self.assertNotIn("member-1", telegram.sent[-1])
            self.assertEqual(
                "unsubscribed",
                service.handle(
                    message("/food_unsubscribe", event_id="update-4"),
                    persona=persona,
                ).status,
            )

    def test_non_admin_cannot_enable(self) -> None:
        with temporary_database() as database:
            telegram = FakeTelegram(administrator=False)
            service = self.service(database, telegram)
            outcome = service.handle(
                message("/food_enable"),
                persona=PersonaSnapshot("lezhi", "v2", "a" * 64),
            )
            self.assertEqual("not_authorized", outcome.status)
            self.assertIsNone(AutomationRepository(database).get_config(chat_id="-1001"))
            self.assertEqual([], telegram.sent)

    def test_foreign_bot_command_is_not_consumed(self) -> None:
        with temporary_database() as database:
            service = self.service(database, FakeTelegram())
            outcome = service.handle(
                message("/food_disable@other_bot CONFIRM"),
                persona=PersonaSnapshot("lezhi", "v2", "a" * 64),
            )
            self.assertFalse(outcome.consumed)

    def test_capability_disabled_does_not_create_config(self) -> None:
        with temporary_database() as database:
            service = self.service(database, FakeTelegram(), available=False)
            outcome = service.handle(
                message("/food_enable"),
                persona=PersonaSnapshot("lezhi", "v2", "a" * 64),
            )
            self.assertEqual("capability_unavailable", outcome.status)
            self.assertIsNone(AutomationRepository(database).get_config(chat_id="-1001"))

    def test_configuration_and_preferences_use_closed_keys(self) -> None:
        with temporary_database() as database:
            telegram = FakeTelegram()
            service = self.service(database, telegram)
            persona = PersonaSnapshot("lezhi", "v2", "a" * 64)
            service.handle(message("/food_enable"), persona=persona)
            configured = service.handle(
                message(
                    "/food_config timezone=Asia/Shanghai lunch=11:20 dinner=17:40 location=上海徐汇",
                    event_id="update-2",
                ),
                persona=persona,
            )
            self.assertEqual("configured", configured.status)
            service.handle(message("/food_subscribe", event_id="update-3"), persona=persona)
            preference = service.handle(
                message(
                    "/food_preferences cuisine=chinese budget=medium dietary=light avoid=香菜",
                    event_id="update-4",
                ),
                persona=persona,
            )
            self.assertEqual("preferences_updated", preference.status)
            invalid = service.handle(
                message("/food_preferences cron=*", event_id="update-5"),
                persona=persona,
            )
            self.assertEqual("invalid_command", invalid.status)

    def test_status_and_subscribe_render_next_time_in_configured_iana_timezone(self) -> None:
        with temporary_database() as database:
            telegram = FakeTelegram()
            service = self.service(database, telegram)
            persona = PersonaSnapshot("lezhi", "v2", "a" * 64)
            service.handle(message("/food_enable"), persona=persona)
            service.handle(
                message(
                    "/food_config timezone=America/New_York lunch=11:20 dinner=17:40",
                    event_id="update-2",
                ),
                persona=persona,
            )
            service.handle(
                message("/food_subscribe", event_id="update-3"),
                persona=persona,
                now=datetime(2026, 8, 3, 14, tzinfo=UTC),
            )
            self.assertIn("时区 America/New_York", telegram.sent[-1])
            self.assertIn("下一次：2026-08-03 11:20 (America/New_York)", telegram.sent[-1])

            service.handle(
                message("/food_status", event_id="update-4"),
                persona=persona,
                now=datetime(2026, 8, 3, 14, tzinfo=UTC),
            )
            self.assertIn("下一次：2026-08-03 11:20 (America/New_York)", telegram.sent[-1])
            self.assertIn("当前群（-1001）", telegram.sent[-1])
            self.assertIn("/food_unsubscribe", telegram.sent[-1])

    def test_disable_requires_confirmation_and_clears_subscriptions(self) -> None:
        with temporary_database() as database:
            service = self.service(database, FakeTelegram())
            persona = PersonaSnapshot("lezhi", "v2", "a" * 64)
            service.handle(message("/food_enable"), persona=persona)
            service.handle(message("/food_subscribe", event_id="update-2"), persona=persona)
            first = service.handle(message("/food_disable", event_id="update-3"), persona=persona)
            self.assertEqual("confirmation_required", first.status)
            confirmed = service.handle(
                message("/food_disable CONFIRM", event_id="update-4"), persona=persona
            )
            self.assertEqual("disabled", confirmed.status)
            self.assertEqual(
                0,
                AutomationRepository(database)
                .aggregate_preferences(chat_id="-1001")
                .subscriber_count,
            )


if __name__ == "__main__":
    unittest.main()
