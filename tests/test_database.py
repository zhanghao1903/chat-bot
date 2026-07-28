from __future__ import annotations

import sqlite3
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from group_llm_agent.database import SQLiteDatabase
from group_llm_agent.delivery import SQLiteDeliveryLedger
from group_llm_agent.events import (
    EffectRequest,
    ExternalEffectKind,
    ExternalEffectStatus,
    FinalEffect,
    FinalEffectKind,
    PersonaSnapshot,
    TelegramTextMessage,
    TriggerPath,
)
from group_llm_agent.runs import RunRepository
from helpers import temporary_database


_EXPECTED_RUNTIME_TABLES = {
    "control_action_audit",
    "effect_runs",
    "external_effects",
    "group_messages",
    "group_policies",
    "member_memory_items",
    "member_memory_sources",
    "memory_reset_barriers",
    "recognition_change_audit",
    "recognition_jobs",
    "schema_migrations",
    "tool_call_audit",
    "trigger_runs",
}


def _message(
    *,
    event_id: str = "update-1",
    group_id: str = "-1001",
    message_id: str = "message-1",
) -> TelegramTextMessage:
    return TelegramTextMessage(
        event_id=event_id,
        group_id=group_id,
        message_id=message_id,
        sender_id="user-1",
        sender_display_name="A",
        text="public group text",
        timestamp=datetime(2026, 7, 29, tzinfo=UTC),
    )


class DatabaseMigrationTests(unittest.TestCase):
    def test_empty_database_migrates_once_and_rerun_is_idempotent(self) -> None:
        with temporary_database() as database:
            database.initialize()
            connection = database.connect()
            try:
                tables = {
                    str(row["name"])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                migrations = connection.execute(
                    "SELECT version, name FROM schema_migrations ORDER BY version"
                ).fetchall()
                foreign_keys = int(connection.execute("PRAGMA foreign_keys").fetchone()[0])
                journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
            finally:
                connection.close()

            self.assertTrue(_EXPECTED_RUNTIME_TABLES.issubset(tables))
            self.assertEqual([(1, "persona_runtime")], [tuple(row) for row in migrations])
            self.assertEqual(1, foreign_keys)
            self.assertEqual("wal", journal_mode)

    def test_legacy_delivery_ledger_survives_additive_migration(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.sqlite3"
            legacy = SQLiteDeliveryLedger(path)
            legacy.initialize()
            delivery_id = legacy.claim(
                chat_id="-1001",
                message_id="legacy-message",
                action_kind="fixed_reply",
            )
            self.assertIsNotNone(delivery_id)
            legacy.close()

            database = SQLiteDatabase(path)
            database.initialize()

            reopened = SQLiteDeliveryLedger(path)
            reopened.initialize()
            record = reopened.get(
                chat_id="-1001",
                message_id="legacy-message",
                action_kind="fixed_reply",
            )
            self.assertIsNotNone(record)
            assert record is not None
            self.assertEqual("sending", record.status)
            reopened.mark_sent(record.id)
            self.assertEqual(
                "sent",
                reopened.get(
                    chat_id="-1001",
                    message_id="legacy-message",
                    action_kind="fixed_reply",
                ).status,  # type: ignore[union-attr]
            )
            reopened.close()

    def test_memory_sources_cannot_cross_group_foreign_key_boundary(self) -> None:
        with temporary_database() as database:
            connection = database.connect()
            try:
                now = datetime(2026, 7, 29, tzinfo=UTC).isoformat()
                first_id = connection.execute(
                    """
                    INSERT INTO group_messages (
                        chat_id, telegram_message_id, event_id, sender_user_id,
                        sender_display_name, direction, text, sent_at, ingested_at
                    )
                    VALUES ('group-a', '1', 'event-a', 'user-a', 'A', 'inbound',
                            'one', ?, ?)
                    """,
                    (now, now),
                ).lastrowid
                second_id = connection.execute(
                    """
                    INSERT INTO group_messages (
                        chat_id, telegram_message_id, event_id, sender_user_id,
                        sender_display_name, direction, text, sent_at, ingested_at
                    )
                    VALUES ('group-b', '1', 'event-b', 'user-b', 'B', 'inbound',
                            'two', ?, ?)
                    """,
                    (now, now),
                ).lastrowid
                connection.execute(
                    """
                    INSERT INTO member_memory_items (
                        memory_id, chat_id, member_user_id, category, statement,
                        stored_confidence, first_observed_at, last_supported_at,
                        updated_at, recognition_policy_version
                    )
                    VALUES ('memory-a', 'group-a', 'user-a', 'fact', 'safe fact',
                            0.8, ?, ?, ?, 'policy-1')
                    """,
                    (now, now, now),
                )
                connection.commit()

                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """
                        INSERT INTO member_memory_sources (
                            memory_id, chat_id, source_message_id
                        )
                        VALUES ('memory-a', 'group-a', ?)
                        """,
                        (second_id,),
                    )

                connection.execute(
                    """
                    INSERT INTO member_memory_sources (
                        memory_id, chat_id, source_message_id
                    )
                    VALUES ('memory-a', 'group-a', ?)
                    """,
                    (first_id,),
                )
                connection.commit()
            finally:
                connection.close()


class RunRepositoryTests(unittest.TestCase):
    def test_external_effect_is_unique_across_kind_and_persona_version(self) -> None:
        with temporary_database() as database:
            repository = RunRepository(database)
            message = _message()
            first_persona = PersonaSnapshot("original", "v1", "digest-1")
            later_persona = PersonaSnapshot("original", "v2", "digest-2")

            first_id = repository.claim_external_effect(
                message=message,
                effect_kind=ExternalEffectKind.REPLY,
                persona=first_persona,
            )
            duplicate_id = repository.claim_external_effect(
                message=message,
                effect_kind=ExternalEffectKind.FAILURE_REPLY,
                persona=later_persona,
            )

            self.assertIsNotNone(first_id)
            self.assertIsNone(duplicate_id)
            record = repository.get_external_effect(
                chat_id=message.group_id,
                trigger_event_id=message.event_id,
            )
            self.assertIsNotNone(record)
            assert record is not None
            self.assertEqual(ExternalEffectStatus.SENDING, record.status)
            self.assertEqual(first_persona.persona_version, record.persona_version)

            assert first_id is not None
            repository.mark_external_sent(first_id, platform_message_id="telegram-99")
            with self.assertRaises(ValueError):
                repository.mark_external_failed(first_id, error_code="late_failure")

            sent = repository.get_external_effect(
                chat_id=message.group_id,
                trigger_event_id=message.event_id,
            )
            assert sent is not None
            self.assertEqual(ExternalEffectStatus.SENT, sent.status)
            self.assertEqual("telegram-99", sent.platform_message_id)

    def test_external_effect_terminal_crash_states_are_distinct(self) -> None:
        with temporary_database() as database:
            repository = RunRepository(database)
            persona = PersonaSnapshot("original", "v1", "digest-1")
            cases = (
                ("sent", repository.mark_external_sent, {"platform_message_id": "out-1"}),
                ("failed", repository.mark_external_failed, {"error_code": "rejected"}),
                ("uncertain", repository.mark_external_uncertain, {"error_code": "timeout"}),
            )
            for index, (expected, transition, arguments) in enumerate(cases, start=1):
                message = _message(event_id=f"event-{index}", message_id=str(index))
                effect_id = repository.claim_external_effect(
                    message=message,
                    effect_kind=ExternalEffectKind.REPLY,
                    persona=persona,
                )
                assert effect_id is not None
                transition(effect_id, **arguments)
                record = repository.get_external_effect(
                    chat_id=message.group_id,
                    trigger_event_id=message.event_id,
                )
                assert record is not None
                self.assertEqual(expected, record.status.value)

    def test_effect_run_records_metadata_but_not_response_text(self) -> None:
        with temporary_database() as database:
            repository = RunRepository(database)
            persona = PersonaSnapshot("original", "v1", "digest-1")
            request = EffectRequest(
                request_id="request-1",
                trigger_path=TriggerPath.DIRECT,
                trigger_reason="mention",
                message=_message(),
                persona=persona,
                deadline_at=datetime.now(UTC) + timedelta(seconds=20),
            )
            run_id = repository.start_effect_run(request)
            repository.complete_effect_run(
                effect_run_id=run_id,
                effect=FinalEffect(
                    kind=FinalEffectKind.REPLY,
                    reason_code="character_reply",
                    persona=persona,
                    text="this must not be persisted in effect_runs",
                ),
                model_call_count=2,
                tool_call_count=1,
            )

            connection = database.connect()
            try:
                row = connection.execute(
                    """
                    SELECT status, model_call_count, tool_call_count, reason_code
                    FROM effect_runs WHERE id = ?
                    """,
                    (run_id,),
                ).fetchone()
                columns = {
                    str(column["name"])
                    for column in connection.execute("PRAGMA table_info(effect_runs)")
                }
            finally:
                connection.close()

            self.assertEqual(("reply", 2, 1, "character_reply"), tuple(row))
            self.assertNotIn("text", columns)
            self.assertNotIn("prompt", columns)
            self.assertNotIn("response", columns)


if __name__ == "__main__":
    unittest.main()
