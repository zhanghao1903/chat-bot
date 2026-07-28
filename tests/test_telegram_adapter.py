from __future__ import annotations

import unittest

from group_llm_agent.platforms.telegram import TelegramAdapter


class TelegramAdapterTests(unittest.TestCase):
    def test_normalize_message_update(self) -> None:
        adapter = TelegramAdapter(
            bot_username="agent",
        )
        update = {
            "update_id": 123,
            "message": {
                "message_id": 9,
                "date": 1781769600,
                "chat": {"id": -100123, "type": "supergroup", "title": "Group"},
                "from": {"id": 42, "first_name": "Alice", "username": "alice"},
                "text": "@agent 查一下这个链接",
            },
        }

        events = adapter.normalize_update(update, raw_event_ref="raw-1")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_id, "123")
        self.assertEqual(events[0].group_id, "-100123")
        self.assertEqual(events[0].sender_id, "42")
        self.assertTrue(events[0].mentioned_bot)
        self.assertEqual(events[0].raw_event_ref, "raw-1")

    def test_preserves_exact_text_for_fixed_reply_matching(self) -> None:
        adapter = TelegramAdapter()
        update = {
            "update_id": 124,
            "message": {
                "message_id": 10,
                "date": 1781769600,
                "chat": {"id": -100123, "type": "group"},
                "from": {"id": 42, "first_name": "Alice"},
                "text": " 1",
            },
        }

        events = adapter.normalize_update(update)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].text, " 1")

    def test_ignores_private_and_bot_authored_messages(self) -> None:
        adapter = TelegramAdapter()
        private_update = {
            "update_id": 125,
            "message": {
                "message_id": 11,
                "date": 1781769600,
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 42, "first_name": "Alice"},
                "text": "1",
            },
        }
        bot_update = {
            "update_id": 126,
            "message": {
                "message_id": 12,
                "date": 1781769600,
                "chat": {"id": -100123, "type": "supergroup"},
                "from": {"id": 7, "first_name": "Bot", "is_bot": True},
                "text": "1",
            },
        }

        self.assertEqual(adapter.normalize_update(private_update), [])
        self.assertEqual(adapter.normalize_update(bot_update), [])

    def test_ignores_non_text_update(self) -> None:
        adapter = TelegramAdapter()
        update = {"update_id": 123, "message": {"message_id": 9, "chat": {"id": -1}}}

        self.assertEqual(adapter.normalize_update(update), [])

    def test_normalizes_reply_command_and_stable_text_mentions(self) -> None:
        adapter = TelegramAdapter(bot_username="agent")
        update = {
            "update_id": 127,
            "message": {
                "message_id": 13,
                "date": 1781769600,
                "chat": {"id": -100123, "type": "supergroup"},
                "from": {"id": 42, "first_name": "Alice"},
                "text": "/ask@agent hello Bob",
                "entities": [
                    {"type": "bot_command", "offset": 0, "length": 10},
                    {
                        "type": "text_mention",
                        "offset": 17,
                        "length": 3,
                        "user": {"id": 88, "first_name": "Bob"},
                    },
                ],
                "reply_to_message": {
                    "message_id": 12,
                    "from": {"id": 7, "is_bot": True, "first_name": "Agent"},
                    "text": "previous bot reply",
                },
            },
        }

        event = adapter.normalize_update(update)[0]

        self.assertTrue(event.mentioned_bot)
        self.assertTrue(event.is_bot_command)
        self.assertEqual("12", event.replied_to_message_id)
        self.assertEqual("7", event.replied_to_user_id)
        self.assertEqual(("88",), event.mentioned_user_ids)


if __name__ == "__main__":
    unittest.main()
