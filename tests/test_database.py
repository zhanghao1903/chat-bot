from __future__ import annotations

import sqlite3
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from helpers import temporary_database

from group_llm_agent.database import _MIGRATIONS, SQLiteDatabase
from group_llm_agent.delivery import SQLiteDeliveryLedger
from group_llm_agent.events import (
    EffectRequest,
    ExternalEffectKind,
    ExternalEffectStatus,
    FinalEffect,
    FinalEffectKind,
    PersonaSnapshot,
    TelegramTextMessage,
    TriggerCategory,
    TriggerEvaluationDecisionKind,
    TriggerModelStatus,
    TriggerPath,
)
from group_llm_agent.runs import RunRepository

_EXPECTED_RUNTIME_TABLES = {
    "automation_action_audit",
    "automation_group_configs",
    "automation_occurrences",
    "automation_subscriptions",
    "avatar_change_audit",
    "control_action_audit",
    "effect_runs",
    "external_effects",
    "group_messages",
    "group_policies",
    "member_memory_items",
    "member_memory_sources",
    "memory_reset_barriers",
    "media_effect_audit",
    "persona_mood_observations",
    "recognition_change_audit",
    "recognition_jobs",
    "schema_migrations",
    "tool_call_audit",
    "trigger_evaluations",
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
            self.assertEqual(
                [
                    (1, "persona_runtime"),
                    (2, "conversation_triggers_v0_2"),
                    (3, "visual_expression_v0_3"),
                    (4, "avatar_global_provenance"),
                    (5, "scheduled_food_automation_v0_4"),
                ],
                [tuple(row) for row in migrations],
            )
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

    def test_exact_v4_database_migrates_to_v5_without_losing_effect_audit(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime-v4.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    """
                    CREATE TABLE schema_migrations (
                        version INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        applied_at TEXT NOT NULL
                    )
                    """
                )
                for version, name, script in _MIGRATIONS[:4]:
                    connection.executescript(script)
                    connection.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (version, name, "2026-08-03T00:00:00+00:00"),
                    )
                connection.execute(
                    """
                    INSERT INTO external_effects (
                        chat_id, trigger_event_id, trigger_message_id, effect_kind,
                        requested_effect_kind, delivered_effect_kind, status,
                        persona_version, persona_digest, platform_message_id,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, 'reply', 'reply', 'reply', 'sent', ?, ?, ?, ?, ?)
                    """,
                    (
                        "-1001",
                        "legacy-event",
                        "legacy-message",
                        "lezhi-v2.0",
                        "a" * 64,
                        "legacy-outbound",
                        "2026-08-03T00:00:00+00:00",
                        "2026-08-03T00:00:00+00:00",
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO tool_call_audit (
                        owner_kind, owner_id, chat_id, capability, purpose_code,
                        source_scope, status, result_count, result_char_count,
                        created_at
                    ) VALUES ('effect', 7, '-1001', 'recent_messages',
                              'context_gap', 'group', 'completed', 1, 12, ?)
                    """,
                    ("2026-08-03T00:00:00+00:00",),
                )
                connection.commit()
            finally:
                connection.close()

            SQLiteDatabase(path).initialize()
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            try:
                effect = connection.execute(
                    "SELECT * FROM external_effects WHERE trigger_event_id = 'legacy-event'"
                ).fetchone()
                tool = connection.execute(
                    "SELECT * FROM tool_call_audit WHERE owner_id = 7"
                ).fetchone()
                quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
                migration = connection.execute(
                    "SELECT name FROM schema_migrations WHERE version = 5"
                ).fetchone()
            finally:
                connection.close()

            assert effect is not None
            assert tool is not None
            assert migration is not None
            self.assertEqual("inbound", effect["source_kind"])
            self.assertIsNone(effect["scheduled_occurrence_id"])
            self.assertEqual("legacy-outbound", effect["platform_message_id"])
            self.assertEqual("context", tool["budget_kind"])
            self.assertEqual("scheduled_food_automation_v0_4", migration["name"])
            self.assertEqual("ok", quick_check)

    def test_memory_sources_cannot_cross_group_foreign_key_boundary(self) -> None:
        with temporary_database() as database:
            connection = database.connect()
            try:
                now = datetime(2026, 7, 29, tzinfo=UTC).isoformat()
                first_id = connection.execute(
                    """
                    INSERT INTO group_messages (
                        chat_id, telegram_message_id, event_id, sender_user_id,
                        sender_display_name, direction, text, text_sha256,
                        sent_at, ingested_at
                    )
                    VALUES ('group-a', '1', 'event-a', 'user-a', 'A', 'inbound',
                            'one', 'digest-one', ?, ?)
                    """,
                    (now, now),
                ).lastrowid
                second_id = connection.execute(
                    """
                    INSERT INTO group_messages (
                        chat_id, telegram_message_id, event_id, sender_user_id,
                        sender_display_name, direction, text, text_sha256,
                        sent_at, ingested_at
                    )
                    VALUES ('group-b', '1', 'event-b', 'user-b', 'B', 'inbound',
                            'two', 'digest-two', ?, ?)
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
    def test_sticker_effect_records_requested_and_fallback_delivery_kinds(self) -> None:
        with temporary_database() as database:
            repository = RunRepository(database)
            message = _message()
            persona = PersonaSnapshot("original", "v1", "digest-1")

            effect_id = repository.claim_external_effect(
                message=message,
                effect_kind=ExternalEffectKind.STICKER,
                persona=persona,
                asset_semantic_id="reaction.delighted.v1",
            )
            assert effect_id is not None
            repository.mark_external_sent(
                effect_id,
                platform_message_id="telegram-fallback-99",
                delivered_effect_kind=ExternalEffectKind.REPLY,
            )

            record = repository.get_external_effect(
                chat_id=message.group_id,
                trigger_event_id=message.event_id,
            )
            assert record is not None
            self.assertEqual(ExternalEffectKind.STICKER, record.effect_kind)
            self.assertEqual(ExternalEffectKind.STICKER, record.requested_effect_kind)
            self.assertEqual(ExternalEffectKind.REPLY, record.delivered_effect_kind)
            self.assertEqual("reaction.delighted.v1", record.asset_semantic_id)

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

    def test_expression_usage_metrics_are_aggregate_only(self) -> None:
        with temporary_database() as database:
            repository = RunRepository(database)
            persona = PersonaSnapshot("original", "v1", "digest-1")
            effects = (
                ("sticker", "a", "sticker", "sent"),
                ("sticker", "a", "sticker", "sent"),
                ("sticker", "b", "sticker", "sent"),
                ("sticker", "c", "failure_reply", "sent"),
                ("sticker", "d", None, "uncertain"),
                ("reply", None, "reply", "sent"),
            )
            for index, (requested, semantic_id, delivered, status) in enumerate(effects, start=1):
                effect_id = repository.claim_external_effect(
                    message=_message(event_id=f"metric-{index}", message_id=str(index)),
                    effect_kind=ExternalEffectKind(requested),
                    persona=persona,
                    asset_semantic_id=semantic_id,
                )
                assert effect_id is not None
                if status == "sent":
                    repository.mark_external_sent(
                        effect_id,
                        platform_message_id=f"out-{index}",
                        delivered_effect_kind=ExternalEffectKind(delivered),
                    )
                else:
                    repository.mark_external_uncertain(effect_id, error_code="timeout")

            metrics = repository.expression_usage_metrics(
                chat_id="-1001",
                since=datetime(2026, 1, 1, tzinfo=UTC),
            )

            self.assertEqual(5, metrics.visible_effect_count)
            self.assertEqual(5, metrics.sticker_requested_count)
            self.assertEqual(3, metrics.sticker_sent_count)
            self.assertEqual(1, metrics.repeated_sticker_count)
            self.assertEqual(2, metrics.degraded_sticker_count)
            self.assertEqual(0.6, metrics.sticker_visible_rate)
            self.assertEqual(0.4, metrics.sticker_degradation_rate)

    def test_effect_run_records_metadata_but_not_response_text(self) -> None:
        with temporary_database() as database:
            repository = RunRepository(database)
            persona = PersonaSnapshot("original", "v1", "digest-1")
            request = EffectRequest(
                request_id="request-1",
                trigger_path=TriggerPath.DIRECT,
                trigger_category=TriggerCategory.DIRECT_PLATFORM,
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
                    SELECT status, model_call_count, tool_call_count, reason_code,
                           trigger_category
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

            self.assertEqual(
                ("reply", 2, 1, "character_reply", "direct_platform"),
                tuple(row),
            )
            self.assertNotIn("text", columns)
            self.assertNotIn("prompt", columns)
            self.assertNotIn("response", columns)

    def test_final_trigger_evaluation_is_minimal_upserted_and_terminal_by_kind(self) -> None:
        with temporary_database() as database:
            repository = RunRepository(database)
            message = _message()
            persona = PersonaSnapshot("original", "v1", "digest-1")

            evaluation_id = repository.record_trigger_evaluation(
                request_id="evaluation-1",
                message=message,
                trigger_category=TriggerCategory.CONVERSATION_CONTINUITY,
                persona_name_hit=False,
                continuity_anchor_message_id="outbound-9",
                decision_kind=TriggerEvaluationDecisionKind.EFFECT_REQUESTED,
                reason_code="answered_anchor_question",
                model_status=TriggerModelStatus.COMPLETED,
                persona=persona,
            )
            self.assertFalse(
                repository.has_terminal_trigger_evaluation(
                    chat_id=message.group_id,
                    trigger_event_id=message.event_id,
                )
            )
            same_id = repository.record_trigger_evaluation(
                request_id="evaluation-1",
                message=message,
                trigger_category=TriggerCategory.CONVERSATION_CONTINUITY,
                persona_name_hit=False,
                continuity_anchor_message_id="outbound-9",
                decision_kind=TriggerEvaluationDecisionKind.SILENCE,
                reason_code="natural_close",
                model_status=TriggerModelStatus.COMPLETED,
                persona=persona,
            )

            self.assertEqual(evaluation_id, same_id)
            self.assertTrue(
                repository.has_terminal_trigger_evaluation(
                    chat_id=message.group_id,
                    trigger_event_id=message.event_id,
                )
            )
            record = repository.get_trigger_evaluation(
                chat_id=message.group_id,
                trigger_event_id=message.event_id,
            )
            assert record is not None
            self.assertEqual(TriggerEvaluationDecisionKind.SILENCE, record.decision_kind)
            self.assertEqual("outbound-9", record.continuity_anchor_message_id)

            connection = database.connect()
            try:
                columns = {
                    str(column["name"])
                    for column in connection.execute("PRAGMA table_info(trigger_evaluations)")
                }
            finally:
                connection.close()
            self.assertTrue(
                {"trigger_category", "persona_name_hit", "continuity_anchor_message_id"} <= columns
            )
            self.assertTrue({"text", "prompt", "response", "confidence"}.isdisjoint(columns))


if __name__ == "__main__":
    unittest.main()
