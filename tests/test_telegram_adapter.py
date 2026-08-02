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

    def test_normalizes_photo_caption_and_media_only_static_sticker(self) -> None:
        adapter = TelegramAdapter(bot_username="agent")
        photo_update = {
            "update_id": 130,
            "message": {
                "message_id": 14,
                "date": 1781769600,
                "chat": {"id": -100123, "type": "supergroup"},
                "from": {"id": 42, "first_name": "Alice"},
                "caption": "乐枝，看看这个",
                "photo": [
                    {"file_id": "small", "file_unique_id": "u1", "width": 90, "height": 90},
                    {
                        "file_id": "large",
                        "file_unique_id": "u2",
                        "width": 1280,
                        "height": 960,
                        "file_size": 1234,
                    },
                ],
            },
        }
        sticker_update = {
            "update_id": 131,
            "message": {
                "message_id": 15,
                "date": 1781769600,
                "chat": {"id": -100123, "type": "supergroup"},
                "from": {"id": 42, "first_name": "Alice"},
                "sticker": {
                    "file_id": "sticker-file",
                    "file_unique_id": "sticker-unique",
                    "width": 512,
                    "height": 512,
                    "is_animated": False,
                    "is_video": False,
                    "set_name": "sample",
                },
            },
        }

        photo = adapter.normalize_update(photo_update)[0]
        sticker = adapter.normalize_update(sticker_update)[0]

        self.assertEqual("乐枝，看看这个", photo.text)
        self.assertIsNotNone(photo.media)
        self.assertEqual("large", photo.media.file_id)
        self.assertEqual("photo", photo.media.kind.value)
        self.assertEqual("", sticker.text)
        self.assertIsNotNone(sticker.media)
        self.assertEqual("static_sticker", sticker.media.kind.value)

    def test_rejects_unsupported_document_and_dynamic_sticker(self) -> None:
        adapter = TelegramAdapter()
        base = {
            "message_id": 16,
            "date": 1781769600,
            "chat": {"id": -100123, "type": "supergroup"},
            "from": {"id": 42, "first_name": "Alice"},
        }
        for media in (
            {"document": {"file_id": "x", "file_unique_id": "u", "mime_type": "text/plain"}},
            {
                "sticker": {
                    "file_id": "x",
                    "file_unique_id": "u",
                    "is_animated": True,
                }
            },
        ):
            with self.subTest(media=media):
                update = {"update_id": 132, "message": {**base, **media}}
                self.assertEqual([], adapter.normalize_update(update))

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
        self.assertEqual("agent", event.bot_command_target)

    def test_ignores_commands_addressed_to_another_bot(self) -> None:
        adapter = TelegramAdapter(bot_username="agent")
        for index, text in enumerate(
            (
                "/memory_forget_group@some_other_bot CONFIRM",
                "/weather@some_other_bot Shanghai",
            ),
            start=200,
        ):
            with self.subTest(text=text):
                command = text.split(maxsplit=1)[0]
                update = {
                    "update_id": index,
                    "message": {
                        "message_id": index,
                        "date": 1781769600,
                        "chat": {"id": -100123, "type": "supergroup"},
                        "from": {"id": 42, "first_name": "Alice"},
                        "text": text,
                        "entities": [
                            {
                                "type": "bot_command",
                                "offset": 0,
                                "length": len(command),
                            }
                        ],
                    },
                }

                self.assertEqual([], adapter.normalize_update(update))


if __name__ == "__main__":
    unittest.main()
