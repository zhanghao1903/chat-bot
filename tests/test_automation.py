from __future__ import annotations

import unittest
from datetime import UTC, date, datetime, timedelta

from helpers import temporary_database

from group_llm_agent.automation import (
    AutomationRepository,
    MealSlot,
    OccurrenceStatus,
    SubscriptionPreferences,
    definition_for,
    occurrence_identity,
    scheduled_instant,
    validate_location,
)
from group_llm_agent.events import (
    EffectRequest,
    EffectSourceKind,
    PersonaSnapshot,
    ScheduledOccurrenceSource,
    TelegramTextMessage,
    TriggerCategory,
    TriggerPath,
)

_PERSONA = PersonaSnapshot("lezhi", "lezhi-v2.0", "a" * 64)


class AutomationContractTests(unittest.TestCase):
    def test_registry_is_closed(self) -> None:
        self.assertEqual(
            "weekday_food_recommendation", definition_for("weekday_food_recommendation").type_id
        )
        with self.assertRaisesRegex(ValueError, "unknown automation type"):
            definition_for("member_supplied_cron")

    def test_schedule_uses_weekday_timezone_and_two_stable_slots(self) -> None:
        monday = date(2026, 8, 3)
        lunch = scheduled_instant(
            local_date=monday,
            slot=MealSlot.LUNCH,
            timezone="Asia/Shanghai",
            lunch_time="11:30",
            dinner_time="17:30",
        )
        dinner = scheduled_instant(
            local_date=monday,
            slot=MealSlot.DINNER,
            timezone="Asia/Shanghai",
            lunch_time="11:30",
            dinner_time="17:30",
        )
        self.assertEqual(datetime(2026, 8, 3, 3, 30, tzinfo=UTC), lunch)
        self.assertEqual(datetime(2026, 8, 3, 9, 30, tzinfo=UTC), dinner)
        self.assertIsNone(
            scheduled_instant(
                local_date=date(2026, 8, 1),
                slot=MealSlot.LUNCH,
                timezone="Asia/Shanghai",
                lunch_time="11:30",
                dinner_time="17:30",
            )
        )

    def test_occurrence_identity_is_stable_and_scope_bound(self) -> None:
        first = occurrence_identity(
            bot_user_id="7", chat_id="-1001", local_date=date(2026, 8, 3), slot=MealSlot.LUNCH
        )
        self.assertEqual(
            first,
            occurrence_identity(
                bot_user_id="7", chat_id="-1001", local_date=date(2026, 8, 3), slot=MealSlot.LUNCH
            ),
        )
        self.assertNotEqual(
            first,
            occurrence_identity(
                bot_user_id="7", chat_id="-2002", local_date=date(2026, 8, 3), slot=MealSlot.LUNCH
            ),
        )

    def test_location_and_preferences_reject_urls_and_sensitive_reasons(self) -> None:
        self.assertEqual("上海 徐汇", validate_location(" 上海  徐汇 "))
        with self.assertRaises(ValueError):
            validate_location("https://example.com")
        with self.assertRaisesRegex(ValueError, "invalid avoid item"):
            SubscriptionPreferences(avoid_items=("花生过敏",))
        with self.assertRaisesRegex(ValueError, "invalid cuisine"):
            SubscriptionPreferences(cuisine_tags=("model_chosen_value",))


class AutomationRepositoryTests(unittest.TestCase):
    def test_enable_subscribe_is_idempotent_and_group_isolated(self) -> None:
        with temporary_database() as database:
            repository = AutomationRepository(database)
            config = repository.enable_group(chat_id="-1001")
            self.assertTrue(config.enabled)
            self.assertEqual("Asia/Shanghai", config.timezone)
            self.assertTrue(repository.subscribe(chat_id="-1001", member_user_id="member-1"))
            self.assertFalse(repository.subscribe(chat_id="-1001", member_user_id="member-1"))
            self.assertEqual(1, repository.aggregate_preferences(chat_id="-1001").subscriber_count)
            self.assertEqual(0, repository.aggregate_preferences(chat_id="-2002").subscriber_count)

    def test_subscribe_requires_enabled_group_and_unsubscribe_deletes_preferences(self) -> None:
        with temporary_database() as database:
            repository = AutomationRepository(database)
            with self.assertRaisesRegex(ValueError, "not enabled"):
                repository.subscribe(chat_id="-1001", member_user_id="member-1")
            repository.enable_group(chat_id="-1001")
            repository.subscribe(
                chat_id="-1001",
                member_user_id="member-1",
                preferences=SubscriptionPreferences(
                    cuisine_tags=("chinese",),
                    budget_band="medium",
                    dietary_tags=("light",),
                    avoid_items=("香菜",),
                ),
            )
            aggregate = repository.aggregate_preferences(chat_id="-1001")
            self.assertEqual(1, aggregate.subscriber_count)
            self.assertIn("chinese:1", aggregate.summary)
            self.assertTrue(repository.unsubscribe(chat_id="-1001", member_user_id="member-1"))
            self.assertEqual(0, repository.aggregate_preferences(chat_id="-1001").subscriber_count)

    def test_disable_removes_active_subscriptions(self) -> None:
        with temporary_database() as database:
            repository = AutomationRepository(database)
            repository.enable_group(chat_id="-1001")
            repository.subscribe(chat_id="-1001", member_user_id="member-1")
            self.assertTrue(repository.disable_group(chat_id="-1001"))
            self.assertEqual(0, repository.aggregate_preferences(chat_id="-1001").subscriber_count)
            config = repository.get_config(chat_id="-1001")
            assert config is not None
            self.assertFalse(config.enabled)

    def test_occurrence_insert_lease_prepare_and_replay_are_stable(self) -> None:
        with temporary_database() as database:
            repository = AutomationRepository(database)
            config = repository.enable_group(chat_id="-1001")
            repository.subscribe(chat_id="-1001", member_user_id="member-1")
            occurrence = repository.create_occurrence(
                bot_user_id="7",
                config=config,
                local_date=date(2026, 8, 3),
                slot=MealSlot.LUNCH,
                persona=_PERSONA,
            )
            assert occurrence is not None
            duplicate = repository.create_occurrence(
                bot_user_id="7",
                config=config,
                local_date=date(2026, 8, 3),
                slot=MealSlot.LUNCH,
                persona=_PERSONA,
            )
            self.assertEqual(
                occurrence.occurrence_id, duplicate.occurrence_id if duplicate else None
            )
            now = occurrence.scheduled_for
            leased = repository.lease(
                occurrence_id=occurrence.occurrence_id, worker_id="worker-a", now=now
            )
            self.assertIsNotNone(leased)
            self.assertIsNone(
                repository.lease(
                    occurrence_id=occurrence.occurrence_id, worker_id="worker-b", now=now
                )
            )
            self.assertTrue(
                repository.prepare(
                    occurrence_id=occurrence.occurrence_id,
                    worker_id="worker-a",
                    effect_request_id="effect-1",
                    primary_key="noodles",
                    payload={"primary": "面"},
                    text="主推：面\n备选：饭、饺子",
                )
            )
            prepared = repository.get_occurrence(occurrence_id=occurrence.occurrence_id)
            assert prepared is not None
            self.assertEqual(OccurrenceStatus.PREPARED, prepared.status)
            self.assertEqual("主推：面\n备选：饭、饺子", prepared.prepared_text)

    def test_expired_lease_can_be_recovered_but_prepared_cannot(self) -> None:
        with temporary_database() as database:
            repository = AutomationRepository(database)
            config = repository.enable_group(chat_id="-1001")
            occurrence = repository.create_occurrence(
                bot_user_id="7",
                config=config,
                local_date=date(2026, 8, 3),
                slot=MealSlot.DINNER,
                persona=_PERSONA,
            )
            assert occurrence is not None
            now = occurrence.scheduled_for
            self.assertIsNotNone(
                repository.lease(occurrence_id=occurrence.occurrence_id, worker_id="dead", now=now)
            )
            recovered = repository.lease(
                occurrence_id=occurrence.occurrence_id,
                worker_id="new",
                now=now + timedelta(minutes=3),
            )
            self.assertIsNotNone(recovered)

    def test_unleased_occurrence_refreshes_after_schedule_change_but_leased_is_immutable(
        self,
    ) -> None:
        with temporary_database() as database:
            repository = AutomationRepository(database)
            original_config = repository.enable_group(chat_id="-1001")
            due = repository.create_occurrence(
                bot_user_id="7",
                config=original_config,
                local_date=date(2026, 8, 3),
                slot=MealSlot.LUNCH,
                persona=_PERSONA,
            )
            assert due is not None
            changed_config = repository.update_config(
                chat_id="-1001",
                timezone="Asia/Shanghai",
                lunch_time="11:40",
                dinner_time="17:30",
                location_text=None,
            )
            refreshed = repository.create_occurrence(
                bot_user_id="7",
                config=changed_config,
                local_date=date(2026, 8, 3),
                slot=MealSlot.LUNCH,
                persona=_PERSONA,
            )
            assert refreshed is not None
            self.assertEqual(due.occurrence_id, refreshed.occurrence_id)
            self.assertEqual(datetime(2026, 8, 3, 3, 40, tzinfo=UTC), refreshed.scheduled_for)
            self.assertEqual(changed_config.config_version, refreshed.config_version)

            leased = repository.lease(
                occurrence_id=refreshed.occurrence_id,
                worker_id="worker-a",
                now=refreshed.scheduled_for,
            )
            assert leased is not None
            later_config = repository.update_config(
                chat_id="-1001",
                timezone="Asia/Shanghai",
                lunch_time="11:50",
                dinner_time="17:30",
                location_text=None,
            )
            immutable = repository.create_occurrence(
                bot_user_id="7",
                config=later_config,
                local_date=date(2026, 8, 3),
                slot=MealSlot.LUNCH,
                persona=_PERSONA,
            )
            assert immutable is not None
            self.assertEqual(OccurrenceStatus.LEASED, immutable.status)
            self.assertEqual(datetime(2026, 8, 3, 3, 40, tzinfo=UTC), immutable.scheduled_for)
            self.assertEqual(changed_config.config_version, immutable.config_version)


class ScheduledEffectSourceTests(unittest.TestCase):
    def test_scheduled_request_has_no_fake_telegram_message(self) -> None:
        source = ScheduledOccurrenceSource(
            occurrence_id="occurrence-1",
            occurrence_key="key-1",
            chat_id="-1001",
            automation_type="weekday_food_recommendation",
            local_date="2026-08-03",
            meal_slot="lunch",
            scheduled_for=datetime(2026, 8, 3, 3, 30, tzinfo=UTC),
            timezone="Asia/Shanghai",
            config_version=1,
            subscriber_count=1,
        )
        request = EffectRequest(
            request_id="effect-1",
            trigger_path=TriggerPath.SCHEDULED,
            trigger_category=TriggerCategory.SCHEDULED_AUTOMATION,
            trigger_reason="scheduled_food_due",
            message=None,
            persona=_PERSONA,
            deadline_at=datetime(2026, 8, 3, 3, 31, tzinfo=UTC),
            scheduled=source,
        )
        self.assertEqual(EffectSourceKind.SCHEDULED, request.source_kind)
        self.assertEqual("-1001", request.chat_id)
        self.assertIsNone(request.trigger_message_id)

    def test_effect_request_requires_exactly_one_source(self) -> None:
        message = TelegramTextMessage(
            event_id="update-1",
            group_id="-1001",
            message_id="1",
            sender_id="member-1",
            sender_display_name="A",
            text="乐枝",
            timestamp=datetime(2026, 8, 3, tzinfo=UTC),
        )
        with self.assertRaisesRegex(ValueError, "exactly one source"):
            EffectRequest(
                request_id="bad",
                trigger_path=TriggerPath.DIRECT,
                trigger_category=TriggerCategory.DIRECT_PLATFORM,
                trigger_reason="bad",
                message=None,
                persona=_PERSONA,
                deadline_at=datetime(2026, 8, 3, tzinfo=UTC),
            )
        inbound = EffectRequest(
            request_id="ok",
            trigger_path=TriggerPath.DIRECT,
            trigger_category=TriggerCategory.DIRECT_PLATFORM,
            trigger_reason="direct",
            message=message,
            persona=_PERSONA,
            deadline_at=datetime(2026, 8, 3, 0, 1, tzinfo=UTC),
        )
        self.assertEqual(EffectSourceKind.INBOUND, inbound.source_kind)


if __name__ == "__main__":
    unittest.main()
