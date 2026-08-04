from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from helpers import temporary_database

from group_llm_agent.automation import (
    AutomationOccurrence,
    AutomationRepository,
    GroupAutomationConfig,
    MealSlot,
    OccurrenceStatus,
    occurrence_identity,
)
from group_llm_agent.automation_runtime import AutomationScheduler, next_scheduled
from group_llm_agent.events import PersonaSnapshot, ScheduledOccurrenceSource


class FakeOccurrenceProcessor:
    def __init__(
        self,
        outcome: OccurrenceStatus = OccurrenceStatus.SENT,
        *,
        fail: bool = False,
    ) -> None:
        self.outcome = outcome
        self.fail = fail
        self.sources: list[ScheduledOccurrenceSource] = []

    def process(
        self,
        *,
        occurrence: AutomationOccurrence,
        source: ScheduledOccurrenceSource,
        worker_id: str,
    ) -> OccurrenceStatus:
        del occurrence, worker_id
        self.sources.append(source)
        if self.fail:
            raise RuntimeError("scripted failure")
        return self.outcome


_PERSONA = PersonaSnapshot("lezhi", "v2", "a" * 64)


class AutomationSchedulerTests(unittest.TestCase):
    def test_due_occurrence_runs_once_and_has_typed_aggregate_source(self) -> None:
        with temporary_database() as database:
            repository = AutomationRepository(database)
            repository.enable_group(chat_id="-1001")
            repository.subscribe(chat_id="-1001", member_user_id="member-1")
            processor = FakeOccurrenceProcessor()
            scheduler = AutomationScheduler(
                repository=repository,
                processor=processor,
                bot_user_id="7",
                persona=_PERSONA,
                clock=lambda: datetime(2026, 8, 3, 3, 35, tzinfo=UTC),
            )
            self.assertEqual(1, scheduler.run_once(worker_id="worker-a"))
            self.assertEqual(0, scheduler.run_once(worker_id="worker-b"))
            self.assertEqual(1, len(processor.sources))
            self.assertEqual(1, processor.sources[0].subscriber_count)
            self.assertEqual(MealSlot.LUNCH.value, processor.sources[0].meal_slot)
            occurrence_id = processor.sources[0].occurrence_id
            occurrence = repository.get_occurrence(occurrence_id=occurrence_id)
            assert occurrence is not None
            self.assertEqual(OccurrenceStatus.SENT, occurrence.status)

    def test_no_subscriber_and_late_occurrences_skip_without_processor(self) -> None:
        with temporary_database() as database:
            repository = AutomationRepository(database)
            repository.enable_group(chat_id="-1001")
            processor = FakeOccurrenceProcessor()
            no_subscriber = AutomationScheduler(
                repository=repository,
                processor=processor,
                bot_user_id="7",
                persona=_PERSONA,
                clock=lambda: datetime(2026, 8, 3, 3, 35, tzinfo=UTC),
            )
            self.assertEqual(1, no_subscriber.run_once(worker_id="worker-a"))
            self.assertEqual([], processor.sources)

            repository.subscribe(chat_id="-1001", member_user_id="member-1")
            late = AutomationScheduler(
                repository=repository,
                processor=processor,
                bot_user_id="7",
                persona=_PERSONA,
                clock=lambda: datetime(2026, 8, 3, 10, 5, tzinfo=UTC),
            )
            self.assertEqual(1, late.run_once(worker_id="worker-a"))
            self.assertEqual([], processor.sources)

    def test_processor_failure_is_contained_and_terminal(self) -> None:
        with temporary_database() as database:
            repository = AutomationRepository(database)
            repository.enable_group(chat_id="-1001")
            repository.subscribe(chat_id="-1001", member_user_id="member-1")
            processor = FakeOccurrenceProcessor(fail=True)
            scheduler = AutomationScheduler(
                repository=repository,
                processor=processor,
                bot_user_id="7",
                persona=_PERSONA,
                clock=lambda: datetime(2026, 8, 3, 3, 31, tzinfo=UTC),
            )
            self.assertEqual(1, scheduler.run_once(worker_id="worker-a"))
            occurrence = repository.get_occurrence(occurrence_id=processor.sources[0].occurrence_id)
            assert occurrence is not None
            self.assertEqual(OccurrenceStatus.DEFINITE_FAILURE, occurrence.status)

    def test_prepared_occurrence_resumes_without_a_new_lease(self) -> None:
        with temporary_database() as database:
            repository = AutomationRepository(database)
            config = repository.enable_group(chat_id="-1001")
            repository.subscribe(chat_id="-1001", member_user_id="member-1")
            occurrence = repository.create_occurrence(
                bot_user_id="7",
                config=config,
                local_date=datetime(2026, 8, 3, tzinfo=UTC).date(),
                slot=MealSlot.LUNCH,
                persona=_PERSONA,
            )
            assert occurrence is not None
            leased = repository.lease(
                occurrence_id=occurrence.occurrence_id,
                worker_id="dead-worker",
                now=occurrence.scheduled_for,
                expected_config_version=config.config_version,
            )
            assert leased is not None
            self.assertTrue(
                repository.prepare(
                    occurrence_id=occurrence.occurrence_id,
                    worker_id="dead-worker",
                    effect_request_id="scheduled:prepared",
                    primary_key="dish:noodles",
                    payload={"kind": "food_recommendation"},
                    text="persisted recommendation",
                )
            )
            processor = FakeOccurrenceProcessor()
            scheduler = AutomationScheduler(
                repository=repository,
                processor=processor,
                bot_user_id="7",
                persona=_PERSONA,
                clock=lambda: datetime(2026, 8, 3, 3, 35, tzinfo=UTC),
            )

            self.assertEqual(1, scheduler.run_once(worker_id="replacement-worker"))
            self.assertEqual(1, len(processor.sources))
            stored = repository.get_occurrence(occurrence_id=occurrence.occurrence_id)
            assert stored is not None
            self.assertEqual(OccurrenceStatus.SENT, stored.status)

    def test_schedule_edit_refreshes_old_unleased_row_and_sends_new_slot_once(self) -> None:
        with temporary_database() as database:
            repository = AutomationRepository(database)
            old_config = repository.enable_group(chat_id="-1001")
            repository.subscribe(chat_id="-1001", member_user_id="member-1")
            old_occurrence = repository.create_occurrence(
                bot_user_id="7",
                config=old_config,
                local_date=datetime(2026, 8, 3, tzinfo=UTC).date(),
                slot=MealSlot.LUNCH,
                persona=_PERSONA,
            )
            assert old_occurrence is not None
            self.assertEqual(datetime(2026, 8, 3, 3, 30, tzinfo=UTC), old_occurrence.scheduled_for)

            new_config = repository.update_config(
                chat_id="-1001",
                timezone="Asia/Shanghai",
                lunch_time="11:40",
                dinner_time="17:30",
                location_text=None,
            )
            refreshed = repository.create_occurrence(
                bot_user_id="7",
                config=new_config,
                local_date=datetime(2026, 8, 3, tzinfo=UTC).date(),
                slot=MealSlot.LUNCH,
                persona=_PERSONA,
            )
            assert refreshed is not None
            self.assertIsNone(
                repository.create_occurrence(
                    bot_user_id="7",
                    config=old_config,
                    local_date=datetime(2026, 8, 3, tzinfo=UTC).date(),
                    slot=MealSlot.LUNCH,
                    persona=_PERSONA,
                )
            )
            processor = FakeOccurrenceProcessor()
            scheduler = AutomationScheduler(
                repository=repository,
                processor=processor,
                bot_user_id="7",
                persona=_PERSONA,
                clock=lambda: datetime(2026, 8, 3, 3, 40, tzinfo=UTC),
            )

            self.assertEqual(1, scheduler.run_once(worker_id="worker-after-edit"))
            self.assertEqual(0, scheduler.run_once(worker_id="worker-restart"))
            self.assertEqual(1, len(processor.sources))
            refreshed = repository.get_occurrence(occurrence_id=old_occurrence.occurrence_id)
            assert refreshed is not None
            self.assertEqual(OccurrenceStatus.SENT, refreshed.status)
            self.assertEqual(datetime(2026, 8, 3, 3, 40, tzinfo=UTC), refreshed.scheduled_for)
            self.assertEqual(new_config.config_version, refreshed.config_version)

    def test_config_change_after_refresh_before_lease_preserves_and_runs_new_slot_once(
        self,
    ) -> None:
        with temporary_database() as database:
            repository = AutomationRepository(database)
            original_config = repository.enable_group(chat_id="-1001")
            repository.subscribe(chat_id="-1001", member_user_id="member-1")
            processor = FakeOccurrenceProcessor()
            original_scheduler = AutomationScheduler(
                repository=repository,
                processor=processor,
                bot_user_id="7",
                persona=_PERSONA,
                clock=lambda: datetime(2026, 8, 3, 3, 30, tzinfo=UTC),
            )
            real_lease = repository.lease
            changed_configs: list[GroupAutomationConfig] = []

            def change_config_before_lease(
                *,
                occurrence_id: str,
                worker_id: str,
                now: datetime,
                expected_config_version: int,
            ) -> AutomationOccurrence | None:
                changed_configs.append(
                    repository.update_config(
                        chat_id="-1001",
                        timezone="Asia/Shanghai",
                        lunch_time="11:40",
                        dinner_time="17:30",
                        location_text=None,
                    )
                )
                return real_lease(
                    occurrence_id=occurrence_id,
                    worker_id=worker_id,
                    now=now,
                    expected_config_version=expected_config_version,
                )

            with patch.object(repository, "lease", side_effect=change_config_before_lease):
                self.assertEqual(0, original_scheduler.run_once(worker_id="stale-worker"))

            self.assertEqual(1, len(changed_configs))
            changed_config = changed_configs[0]
            self.assertEqual(original_config.config_version + 1, changed_config.config_version)
            occurrence_id, _ = occurrence_identity(
                bot_user_id="7",
                chat_id="-1001",
                local_date=datetime(2026, 8, 3, tzinfo=UTC).date(),
                slot=MealSlot.LUNCH,
            )
            stale_due = repository.get_occurrence(occurrence_id=occurrence_id)
            assert stale_due is not None
            self.assertEqual(OccurrenceStatus.DUE, stale_due.status)
            self.assertEqual(original_config.config_version, stale_due.config_version)
            self.assertEqual(datetime(2026, 8, 3, 3, 30, tzinfo=UTC), stale_due.scheduled_for)
            self.assertEqual(0, len(processor.sources))

            current_scheduler = AutomationScheduler(
                repository=repository,
                processor=processor,
                bot_user_id="7",
                persona=_PERSONA,
                clock=lambda: datetime(2026, 8, 3, 3, 40, tzinfo=UTC),
            )
            self.assertEqual(1, current_scheduler.run_once(worker_id="current-worker"))
            self.assertEqual(0, current_scheduler.run_once(worker_id="duplicate-worker"))
            self.assertEqual(1, len(processor.sources))
            stored = repository.get_occurrence(occurrence_id=occurrence_id)
            assert stored is not None
            self.assertEqual(OccurrenceStatus.SENT, stored.status)
            self.assertEqual("sent", stored.reason_code)
            self.assertEqual(changed_config.config_version, stored.config_version)
            self.assertEqual(datetime(2026, 8, 3, 3, 40, tzinfo=UTC), stored.scheduled_for)

    def test_config_change_after_lease_crash_terminalizes_expired_snapshot_once(self) -> None:
        with temporary_database() as database:
            repository = AutomationRepository(database)
            original_config = repository.enable_group(chat_id="-1001")
            repository.subscribe(chat_id="-1001", member_user_id="member-1")
            occurrence = repository.create_occurrence(
                bot_user_id="7",
                config=original_config,
                local_date=datetime(2026, 8, 3, tzinfo=UTC).date(),
                slot=MealSlot.LUNCH,
                persona=_PERSONA,
            )
            assert occurrence is not None
            leased = repository.lease(
                occurrence_id=occurrence.occurrence_id,
                worker_id="crashed-worker",
                now=occurrence.scheduled_for,
                expected_config_version=occurrence.config_version,
            )
            assert leased is not None
            changed_config = repository.update_config(
                chat_id="-1001",
                timezone="Asia/Shanghai",
                lunch_time="11:40",
                dinner_time="17:30",
                location_text=None,
            )
            self.assertEqual(original_config.config_version + 1, changed_config.config_version)

            processor = FakeOccurrenceProcessor()
            recovery_scheduler = AutomationScheduler(
                repository=repository,
                processor=processor,
                bot_user_id="7",
                persona=_PERSONA,
                clock=lambda: datetime(2026, 8, 3, 3, 40, tzinfo=UTC),
            )
            self.assertEqual(1, recovery_scheduler.run_once(worker_id="recovery-worker"))
            self.assertEqual(0, recovery_scheduler.run_once(worker_id="duplicate-worker"))
            self.assertEqual(0, len(processor.sources))
            with database.connect() as connection:
                effect_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM external_effects WHERE scheduled_occurrence_id = ?",
                    (occurrence.occurrence_id,),
                ).fetchone()
            assert effect_count is not None
            self.assertEqual(0, int(effect_count["count"]))

            stored = repository.get_occurrence(occurrence_id=occurrence.occurrence_id)
            assert stored is not None
            self.assertEqual(OccurrenceStatus.DEFINITE_FAILURE, stored.status)
            self.assertEqual("definite_failure", stored.reason_code)
            self.assertEqual(original_config.config_version, stored.config_version)
            self.assertEqual(datetime(2026, 8, 3, 3, 30, tzinfo=UTC), stored.scheduled_for)

    def test_next_schedule_skips_weekend(self) -> None:
        with temporary_database() as database:
            repository = AutomationRepository(database)
            config = repository.enable_group(chat_id="-1001")
            next_at = next_scheduled(
                config,
                after=datetime(2026, 8, 1, 2, tzinfo=UTC),
            )
            self.assertEqual(datetime(2026, 8, 3, 3, 30, tzinfo=UTC), next_at)


if __name__ == "__main__":
    unittest.main()
