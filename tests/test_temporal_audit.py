from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from helpers import temporary_database

from group_llm_agent.events import (
    EffectRequest,
    FinalEffect,
    FinalEffectKind,
    TelegramTextMessage,
    TriggerCategory,
    TriggerPath,
)
from group_llm_agent.persona import load_character_bundle
from group_llm_agent.runs import RunRepository
from group_llm_agent.temporal import FreshnessMode, TemporalContextFactory
from group_llm_agent.temporal_audit import TemporalAuditRepository


class TemporalAuditRepositoryTests(unittest.TestCase):
    def test_records_samples_and_terminal_audit_idempotently(self) -> None:
        with temporary_database() as database:
            request = _request()
            effect_run_id = RunRepository(database).start_effect_run(request)
            context = TemporalContextFactory(
                clock=lambda: datetime(2026, 8, 11, 4, 34, 20, tzinfo=UTC)
            ).sample(group_timezone="Asia/Shanghai")
            repository = TemporalAuditRepository(database)

            sample_id = repository.record_sample(
                effect_run_id=effect_run_id,
                execution_attempt=1,
                model_call_ordinal=1,
                context=context,
            )
            self.assertEqual(
                sample_id,
                repository.record_sample(
                    effect_run_id=effect_run_id,
                    execution_attempt=1,
                    model_call_ordinal=1,
                    context=context,
                ),
            )
            repository.finalize(
                effect_run_id=effect_run_id,
                execution_attempt=1,
                chat_id="group-a",
                trigger_event_id="event-a",
                source_kind="inbound",
                context=context,
                freshness_mode=FreshnessMode.CLOCK,
                web_requested=False,
                status="completed",
            )
            repository.finalize(
                effect_run_id=effect_run_id,
                execution_attempt=1,
                chat_id="group-a",
                trigger_event_id="event-a",
                source_kind="inbound",
                context=context,
                freshness_mode=FreshnessMode.CLOCK,
                web_requested=False,
                status="completed",
            )

            stored = repository.get(effect_run_id=effect_run_id)
            assert stored is not None
            self.assertEqual(context.context_id, stored.final_context_id)
            self.assertEqual(FreshnessMode.CLOCK, stored.freshness_mode)
            self.assertEqual((), stored.web_audit_ids)

    def test_failed_clock_and_conflicting_terminal_rows_fail_closed(self) -> None:
        with temporary_database() as database:
            effect_run_id = RunRepository(database).start_effect_run(_request())
            repository = TemporalAuditRepository(database)
            repository.record_sample(
                effect_run_id=effect_run_id,
                execution_attempt=1,
                model_call_ordinal=1,
                context=None,
                error_code="invalid_clock",
            )
            repository.finalize(
                effect_run_id=effect_run_id,
                execution_attempt=1,
                chat_id="group-a",
                trigger_event_id="event-a",
                source_kind="inbound",
                context=None,
                freshness_mode=None,
                web_requested=False,
                status="failed",
                degradation_reason="invalid_clock",
            )
            with self.assertRaisesRegex(ValueError, "conflicting terminal"):
                repository.finalize(
                    effect_run_id=effect_run_id,
                    execution_attempt=1,
                    chat_id="group-a",
                    trigger_event_id="event-a",
                    source_kind="inbound",
                    context=None,
                    freshness_mode=None,
                    web_requested=False,
                    status="silence",
                    degradation_reason="invalid_clock",
                )

    def test_verified_sources_require_same_effect_web_audit(self) -> None:
        with temporary_database() as database:
            runs = RunRepository(database)
            first_id = runs.start_effect_run(_request())
            other_id = runs.start_effect_run(_request(event_id="event-b", message_id="message-b"))
            valid_web = _web_audit(runs, effect_run_id=first_id)
            foreign_web = _web_audit(runs, effect_run_id=other_id)
            context = TemporalContextFactory(
                clock=lambda: datetime(2026, 8, 11, 4, 34, 20, tzinfo=UTC)
            ).sample(group_timezone="Asia/Shanghai")
            repository = TemporalAuditRepository(database)

            with self.assertRaisesRegex(ValueError, "ownership mismatch"):
                repository.finalize(
                    effect_run_id=first_id,
                    execution_attempt=1,
                    chat_id="group-a",
                    trigger_event_id="event-a",
                    source_kind="inbound",
                    context=context,
                    freshness_mode=FreshnessMode.CURRENT_VERIFIED,
                    web_requested=True,
                    web_audit_ids=(foreign_web,),
                    latest_web_retrieved_at=context.current_utc,
                    status="completed",
                )
            repository.finalize(
                effect_run_id=first_id,
                execution_attempt=1,
                chat_id="group-a",
                trigger_event_id="event-a",
                source_kind="inbound",
                context=context,
                freshness_mode=FreshnessMode.CURRENT_VERIFIED,
                web_requested=True,
                web_audit_ids=(valid_web,),
                latest_web_retrieved_at=context.current_utc,
                status="completed",
            )

    def test_new_attempt_replaces_precompletion_audit_and_stale_attempt_cannot_finish(self) -> None:
        with temporary_database() as database:
            request = _request()
            runs = RunRepository(database)
            repository = TemporalAuditRepository(database)
            first = runs.start_effect_attempt(request)
            first_context = TemporalContextFactory(
                clock=lambda: datetime(2026, 8, 11, 4, 34, tzinfo=UTC)
            ).sample(group_timezone="Asia/Shanghai")
            repository.record_sample(
                effect_run_id=first.effect_run_id,
                execution_attempt=first.execution_attempt,
                model_call_ordinal=1,
                context=first_context,
            )
            repository.finalize(
                effect_run_id=first.effect_run_id,
                execution_attempt=first.execution_attempt,
                chat_id="group-a",
                trigger_event_id="event-a",
                source_kind="inbound",
                context=first_context,
                freshness_mode=FreshnessMode.CLOCK,
                web_requested=False,
                status="completed",
            )

            second = runs.start_effect_attempt(request)
            second_context = TemporalContextFactory(
                clock=lambda: datetime(2026, 8, 11, 4, 35, tzinfo=UTC)
            ).sample(group_timezone="Asia/Shanghai")
            repository.record_sample(
                effect_run_id=second.effect_run_id,
                execution_attempt=second.execution_attempt,
                model_call_ordinal=1,
                context=second_context,
            )
            repository.finalize(
                effect_run_id=second.effect_run_id,
                execution_attempt=second.execution_attempt,
                chat_id="group-a",
                trigger_event_id="event-a",
                source_kind="inbound",
                context=second_context,
                freshness_mode=FreshnessMode.CLOCK,
                web_requested=False,
                status="completed",
            )
            effect = FinalEffect(
                kind=FinalEffectKind.REPLY,
                reason_code="restart_answer",
                persona=request.persona,
                text="重新回答。",
            )
            with self.assertRaisesRegex(ValueError, "Unknown or completed"):
                runs.complete_effect_run(
                    effect_run_id=first.effect_run_id,
                    effect=effect,
                    model_call_count=1,
                    tool_call_count=0,
                    execution_attempt=first.execution_attempt,
                )
            runs.complete_effect_run(
                effect_run_id=second.effect_run_id,
                effect=effect,
                model_call_count=1,
                tool_call_count=0,
                execution_attempt=second.execution_attempt,
            )

            stored = repository.get(effect_run_id=second.effect_run_id)
            assert stored is not None
            self.assertEqual(2, stored.execution_attempt)
            self.assertEqual(second_context.context_id, stored.final_context_id)

    def test_migration_seven_is_additive_and_database_is_healthy(self) -> None:
        with temporary_database() as database:
            with database.connect() as connection:
                versions = connection.execute(
                    "SELECT version, name FROM schema_migrations ORDER BY version"
                ).fetchall()
                quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
                temporal_columns = {
                    str(row["name"])
                    for row in connection.execute("PRAGMA table_info(temporal_answer_audit)")
                }
                sample_columns = {
                    str(row["name"])
                    for row in connection.execute("PRAGMA table_info(temporal_context_samples)")
                }
                effect_columns = {
                    str(row["name"]) for row in connection.execute("PRAGMA table_info(effect_runs)")
                }
            self.assertEqual((7, "temporal_awareness_v1"), tuple(versions[-1]))
            self.assertEqual("ok", quick_check)
            self.assertIn("web_audit_ids_json", temporal_columns)
            self.assertIn("execution_attempt", temporal_columns)
            self.assertIn("execution_attempt", sample_columns)
            self.assertIn("execution_attempt", effect_columns)


def _request(
    *,
    event_id: str = "event-a",
    message_id: str = "message-a",
) -> EffectRequest:
    bundle = load_character_bundle(Path("src/group_llm_agent/persona_bundles/lezhi/lezhi-v2.0"))
    message = TelegramTextMessage(
        event_id=event_id,
        group_id="group-a",
        message_id=message_id,
        sender_id="member-a",
        sender_display_name="A",
        text="现在几点？",
        timestamp=datetime(2026, 8, 11, 4, 34, tzinfo=UTC),
    )
    return EffectRequest(
        request_id=f"effect:{event_id}",
        trigger_path=TriggerPath.DIRECT,
        trigger_category=TriggerCategory.DIRECT_PLATFORM,
        trigger_reason="direct",
        message=message,
        persona=bundle.snapshot,
        deadline_at=message.timestamp + timedelta(seconds=30),
    )


def _web_audit(runs: RunRepository, *, effect_run_id: int) -> int:
    return runs.record_tool_call(
        owner_kind="effect",
        owner_id=effect_run_id,
        chat_id="group-a",
        capability="web_search",
        purpose_code="current_fact",
        source_scope="current_turn_web",
        status="success",
        latency_ms=1,
        result_count=1,
        result_char_count=20,
        budget_kind="web",
        retrieved_at=datetime(2026, 8, 11, 4, 34, tzinfo=UTC),
    )


if __name__ == "__main__":
    unittest.main()
