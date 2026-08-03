from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from helpers import temporary_database

from group_llm_agent.events import InboundMedia, MediaKind, PersonaSnapshot, TelegramTextMessage
from group_llm_agent.messages import MessageRepository

_PERSONA = PersonaSnapshot("test-persona", "v1", "digest-v1")


def _message(
    index: int,
    *,
    chat_id: str = "group-a",
    sender_id: str = "user-a",
) -> TelegramTextMessage:
    return TelegramTextMessage(
        event_id=f"event-{chat_id}-{index}",
        group_id=chat_id,
        message_id=str(index),
        sender_id=sender_id,
        sender_display_name=sender_id,
        text=f"message {index} searchable",
        timestamp=datetime(2026, 7, 29, tzinfo=UTC) + timedelta(seconds=index),
    )


class MessageRepositoryTests(unittest.TestCase):
    def test_transient_media_keeps_safe_reference_without_persistence(self) -> None:
        with temporary_database() as database:
            repository = MessageRepository(database)
            message = TelegramTextMessage(
                event_id="event-media-transient",
                group_id="group-a",
                message_id="media-1",
                sender_id="user-a",
                sender_display_name="A",
                text="",
                timestamp=datetime(2026, 7, 29, tzinfo=UTC),
                media=InboundMedia(
                    kind=MediaKind.PHOTO,
                    file_id="telegram-download-secret",
                    file_unique_id="stable-media-reference",
                    file_size=1234,
                    width=640,
                    height=480,
                ),
            )

            result = repository.ingest_inbound(
                message,
                persona=_PERSONA,
                recognition_policy_version="policy-v1",
            )
            recent = repository.recent(chat_id="group-a")

            self.assertFalse(result.persisted)
            self.assertEqual(1, len(recent))
            self.assertEqual("photo", recent[0].media_kind)
            self.assertEqual("stable-media-reference", recent[0].media_unique_id)

            connection = database.connect()
            try:
                self.assertEqual(
                    0,
                    int(connection.execute("SELECT count(*) FROM group_messages").fetchone()[0]),
                )
            finally:
                connection.close()

    def test_persistent_media_only_message_never_stores_download_file_id(self) -> None:
        with temporary_database() as database:
            repository = MessageRepository(database)
            repository.policies.set_memory_status(
                chat_id="group-a",
                status="enabled",
                persona=_PERSONA,
                notice_message_id="notice-1",
                enabled_by_user_id="admin-1",
            )
            message = TelegramTextMessage(
                event_id="event-media-persistent",
                group_id="group-a",
                message_id="media-2",
                sender_id="user-a",
                sender_display_name="A",
                text="",
                timestamp=datetime(2026, 7, 29, tzinfo=UTC),
                media=InboundMedia(
                    kind=MediaKind.STATIC_STICKER,
                    file_id="telegram-download-secret",
                    file_unique_id="stable-media-reference",
                    mime_type="image/webp",
                    width=512,
                    height=512,
                    sticker_set_name="example_set",
                ),
            )

            result = repository.ingest_inbound(
                message,
                persona=_PERSONA,
                recognition_policy_version="policy-v1",
            )

            self.assertTrue(result.persisted)
            self.assertIsNotNone(result.message_id)
            self.assertIsNone(result.recognition_job_id)
            connection = database.connect()
            try:
                row = connection.execute(
                    """
                    SELECT media_kind, media_unique_id, media_catalog_id
                    FROM group_messages WHERE id = ?
                    """,
                    (result.message_id,),
                ).fetchone()
                columns = {
                    str(column["name"])
                    for column in connection.execute("PRAGMA table_info(group_messages)")
                }
                jobs = int(
                    connection.execute("SELECT count(*) FROM recognition_jobs").fetchone()[0]
                )
            finally:
                connection.close()

            self.assertEqual(
                ("static_sticker", "stable-media-reference", None),
                tuple(row),
            )
            self.assertNotIn("file_id", columns)
            self.assertEqual(0, jobs)

    def test_disabled_memory_keeps_only_last_twenty_messages_in_process(self) -> None:
        with temporary_database() as database:
            repository = MessageRepository(database)
            for index in range(1, 26):
                result = repository.ingest_inbound(
                    _message(index),
                    persona=_PERSONA,
                    recognition_policy_version="policy-v1",
                )
                self.assertFalse(result.persisted)

            duplicate = repository.ingest_inbound(
                _message(25),
                persona=_PERSONA,
                recognition_policy_version="policy-v1",
            )
            recent = repository.recent(chat_id="group-a")
            connection = database.connect()
            try:
                stored_count = int(
                    connection.execute("SELECT count(*) FROM group_messages").fetchone()[0]
                )
            finally:
                connection.close()

            self.assertTrue(duplicate.duplicate)
            self.assertEqual(20, len(recent))
            self.assertEqual(
                ["6", "25"], [recent[0].telegram_message_id, recent[-1].telegram_message_id]
            )
            self.assertEqual(0, stored_count)

    def test_enabled_memory_persists_message_and_recognition_job_atomically(self) -> None:
        with temporary_database() as database:
            repository = MessageRepository(database)
            repository.policies.set_memory_status(
                chat_id="group-a",
                status="enabled",
                persona=_PERSONA,
                notice_message_id="notice-1",
                enabled_by_user_id="admin-1",
            )

            result = repository.ingest_inbound(
                _message(1),
                persona=_PERSONA,
                recognition_policy_version="policy-v1",
            )
            duplicate = repository.ingest_inbound(
                _message(1),
                persona=_PERSONA,
                recognition_policy_version="policy-v1",
            )

            self.assertTrue(result.persisted)
            self.assertIsNotNone(result.message_id)
            self.assertIsNotNone(result.recognition_job_id)
            self.assertTrue(duplicate.duplicate)
            self.assertIsNone(duplicate.recognition_job_id)

            connection = database.connect()
            try:
                message = connection.execute(
                    """
                    SELECT text, text_sha256, text_expires_at
                    FROM group_messages WHERE id = ?
                    """,
                    (result.message_id,),
                ).fetchone()
                job = connection.execute(
                    """
                    SELECT source_message_id, subject_user_id, persona_version,
                           reset_generation
                    FROM recognition_jobs WHERE id = ?
                    """,
                    (result.recognition_job_id,),
                ).fetchone()
            finally:
                connection.close()

            self.assertEqual("message 1 searchable", message["text"])
            self.assertEqual(64, len(str(message["text_sha256"])))
            self.assertIsNotNone(message["text_expires_at"])
            self.assertEqual(result.message_id, job["source_message_id"])
            self.assertEqual("user-a", job["subject_user_id"])
            self.assertEqual("v1", job["persona_version"])
            self.assertEqual(0, job["reset_generation"])

    def test_expired_text_is_purged_but_metadata_and_digest_remain(self) -> None:
        with temporary_database() as database:
            repository = MessageRepository(database)
            repository.policies.set_memory_status(
                chat_id="group-a",
                status="enabled",
                persona=_PERSONA,
                notice_message_id="notice-1",
                enabled_by_user_id="admin-1",
            )
            result = repository.ingest_inbound(
                _message(1),
                persona=_PERSONA,
                recognition_policy_version="policy-v1",
            )

            purged = repository.purge_expired_text(now=datetime.now(UTC) + timedelta(days=8))
            connection = database.connect()
            try:
                row = connection.execute(
                    """
                    SELECT text, text_sha256, sender_user_id, text_purged_at
                    FROM group_messages WHERE id = ?
                    """,
                    (result.message_id,),
                ).fetchone()
            finally:
                connection.close()

            self.assertEqual(1, purged)
            self.assertIsNone(row["text"])
            self.assertEqual(64, len(str(row["text_sha256"])))
            self.assertEqual("user-a", row["sender_user_id"])
            self.assertIsNotNone(row["text_purged_at"])
            self.assertEqual((), repository.recent(chat_id="group-a"))
            self.assertEqual(
                (),
                repository.search(chat_id="group-a", query="searchable"),
            )

    def test_persistent_search_never_crosses_group_scope(self) -> None:
        with temporary_database() as database:
            repository = MessageRepository(database)
            for chat_id in ("group-a", "group-b"):
                repository.policies.set_memory_status(
                    chat_id=chat_id,
                    status="enabled",
                    persona=_PERSONA,
                    notice_message_id=f"notice-{chat_id}",
                    enabled_by_user_id="admin-1",
                )
                repository.ingest_inbound(
                    _message(1, chat_id=chat_id),
                    persona=_PERSONA,
                    recognition_policy_version="policy-v1",
                )

            group_a = repository.search(chat_id="group-a", query="searchable")
            self.assertEqual(1, len(group_a))
            self.assertEqual("group-a", group_a[0].chat_id)


if __name__ == "__main__":
    unittest.main()
