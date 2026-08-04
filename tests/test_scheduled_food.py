from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from helpers import temporary_database

from group_llm_agent.automation import (
    AutomationOccurrence,
    AutomationRepository,
    MealSlot,
    OccurrenceStatus,
)
from group_llm_agent.automation_delivery import AutomationDeliveryRepository
from group_llm_agent.events import FinalEffect, FinalEffectKind, ScheduledOccurrenceSource
from group_llm_agent.messages import MessageRepository
from group_llm_agent.persona import CharacterBundle, load_character_bundle
from group_llm_agent.platforms.telegram import SentMessage, TelegramApiError
from group_llm_agent.runs import RunRepository
from group_llm_agent.scheduled_food import ScheduledFoodProcessor


class ScheduledFoodProcessorTests(unittest.TestCase):
    def test_other_group_occurrence_is_rejected_before_model_or_send(self) -> None:
        with ScheduledFixtureContext() as fixture:
            result = fixture.processor.process(
                occurrence=replace(fixture.occurrence, chat_id="-2002"),
                source=replace(fixture.source, chat_id="-2002"),
                worker_id="worker-a",
            )

            self.assertEqual(OccurrenceStatus.DEFINITE_FAILURE, result)
            self.assertEqual(0, fixture.effector.calls)
            self.assertEqual(0, fixture.telegram.calls)

    def test_leased_occurrence_is_prepared_claimed_and_sent_once(self) -> None:
        with ScheduledFixtureContext() as fixture:
            result = fixture.processor.process(
                occurrence=fixture.occurrence,
                source=fixture.source,
                worker_id="worker-a",
            )

            self.assertEqual(OccurrenceStatus.SENT, result)
            self.assertEqual(1, fixture.telegram.calls)
            stored = fixture.repository.get_occurrence(
                occurrence_id=fixture.occurrence.occurrence_id
            )
            assert stored is not None
            self.assertEqual(OccurrenceStatus.SENT, stored.status)
            self.assertEqual("dish:noodles", stored.prepared_primary_key)
            external = fixture.runs.get_external_effect(
                chat_id=fixture.occurrence.chat_id,
                trigger_event_id=fixture.occurrence.occurrence_id,
            )
            assert external is not None
            self.assertEqual("sent", external.status.value)
            self.assertIsNone(external.trigger_message_id)

            replay = fixture.processor.process(
                occurrence=stored,
                source=fixture.source,
                worker_id="worker-b",
            )
            self.assertEqual(OccurrenceStatus.SENT, replay)
            self.assertEqual(1, fixture.telegram.calls)

    def test_prepared_replay_uses_persisted_text_without_model_recomputation(self) -> None:
        with ScheduledFixtureContext() as fixture:
            prepared = fixture.prepare_manually(text="稳定主推与两个备选")
            fixture.effector.calls = 0

            result = fixture.processor.process(
                occurrence=prepared,
                source=fixture.source,
                worker_id="worker-b",
            )

            self.assertEqual(OccurrenceStatus.SENT, result)
            self.assertEqual(0, fixture.effector.calls)
            self.assertEqual("稳定主推与两个备选", fixture.telegram.texts[0])

    def test_preclaim_config_change_fails_without_external_effect(self) -> None:
        with ScheduledFixtureContext() as fixture:
            prepared = fixture.prepare_manually()
            fixture.repository.update_config(
                chat_id=fixture.occurrence.chat_id,
                timezone="Asia/Shanghai",
                lunch_time="11:31",
                dinner_time="17:30",
                location_text="上海浦东",
            )

            result = fixture.processor.process(
                occurrence=prepared,
                source=fixture.source,
                worker_id="worker-b",
            )

            self.assertEqual(OccurrenceStatus.DEFINITE_FAILURE, result)
            self.assertEqual(0, fixture.telegram.calls)
            self.assertIsNone(
                fixture.runs.get_external_effect(
                    chat_id=fixture.occurrence.chat_id,
                    trigger_event_id=fixture.occurrence.occurrence_id,
                )
            )

    def test_restart_after_claim_becomes_uncertain_and_never_resends(self) -> None:
        with ScheduledFixtureContext() as fixture:
            prepared = fixture.prepare_manually()
            claimed = fixture.delivery_repository.claim_prepared(
                occurrence_id=prepared.occurrence_id,
                persona=fixture.bundle.snapshot,
                now=fixture.now,
            )
            self.assertIsNotNone(claimed)

            self.assertEqual(1, fixture.processor.recover_inflight())
            recovered = fixture.repository.get_occurrence(occurrence_id=prepared.occurrence_id)
            assert recovered is not None
            self.assertEqual(OccurrenceStatus.UNCERTAIN, recovered.status)
            self.assertEqual(
                OccurrenceStatus.UNCERTAIN,
                fixture.processor.process(
                    occurrence=recovered,
                    source=fixture.source,
                    worker_id="worker-after-restart",
                ),
            )
            self.assertEqual(0, fixture.telegram.calls)

    def test_restart_after_durable_send_ack_reconciles_occurrence_as_sent(self) -> None:
        with ScheduledFixtureContext() as fixture:
            prepared = fixture.prepare_manually()
            effect_id = fixture.delivery_repository.claim_prepared(
                occurrence_id=prepared.occurrence_id,
                persona=fixture.bundle.snapshot,
                now=fixture.now,
            )
            assert effect_id is not None
            fixture.runs.mark_external_sent(
                effect_id,
                platform_message_id="already-sent-telegram-message",
            )

            self.assertEqual(1, fixture.processor.recover_inflight())
            recovered = fixture.repository.get_occurrence(occurrence_id=prepared.occurrence_id)
            assert recovered is not None
            self.assertEqual(OccurrenceStatus.SENT, recovered.status)
            self.assertEqual("delivery_ack_reconciled", recovered.reason_code)
            self.assertEqual(
                ("dish:noodles",),
                fixture.repository.recent_primary_keys(chat_id=prepared.chat_id),
            )
            self.assertEqual(
                OccurrenceStatus.SENT,
                fixture.processor.process(
                    occurrence=recovered,
                    source=fixture.source,
                    worker_id="worker-after-restart",
                ),
            )
            self.assertEqual(0, fixture.telegram.calls)

    def test_timeout_after_claim_is_uncertain_and_replay_does_not_send(self) -> None:
        with ScheduledFixtureContext(
            send_error=TelegramApiError("sendMessage", "timeout")
        ) as fixture:
            result = fixture.processor.process(
                occurrence=fixture.occurrence,
                source=fixture.source,
                worker_id="worker-a",
            )
            self.assertEqual(OccurrenceStatus.UNCERTAIN, result)
            self.assertEqual(1, fixture.telegram.calls)
            stored = fixture.repository.get_occurrence(
                occurrence_id=fixture.occurrence.occurrence_id
            )
            assert stored is not None
            self.assertEqual(
                OccurrenceStatus.UNCERTAIN,
                fixture.processor.process(
                    occurrence=stored,
                    source=fixture.source,
                    worker_id="worker-b",
                ),
            )
            self.assertEqual(1, fixture.telegram.calls)


class ScriptedEffector:
    def __init__(self, bundle: CharacterBundle) -> None:
        self.bundle = bundle
        self.calls = 0

    def execute(self, **kwargs: Any) -> FinalEffect:
        del kwargs
        self.calls += 1
        return FinalEffect(
            kind=FinalEffectKind.REPLY,
            reason_code="weekday_food_choice",
            persona=self.bundle.snapshot,
            text="主推：热汤面\n备选一：盖饭\n备选二：煎饺",
            primary_key="dish:noodles",
        )


class RecordingTelegram:
    def __init__(self, error: TelegramApiError | None = None) -> None:
        self.error = error
        self.calls = 0
        self.texts: list[str] = []

    def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        reply_to_message_id: str | None = None,
    ) -> SentMessage:
        del chat_id, reply_to_message_id
        self.calls += 1
        self.texts.append(text)
        if self.error is not None:
            raise self.error
        return SentMessage(message_id=f"sent-{self.calls}")


class ScheduledFixture:
    def __init__(
        self,
        *,
        bundle: CharacterBundle,
        repository: AutomationRepository,
        delivery_repository: AutomationDeliveryRepository,
        runs: RunRepository,
        occurrence: AutomationOccurrence,
        source: ScheduledOccurrenceSource,
        effector: ScriptedEffector,
        telegram: RecordingTelegram,
        processor: ScheduledFoodProcessor,
        now: datetime,
    ) -> None:
        self.bundle = bundle
        self.repository = repository
        self.delivery_repository = delivery_repository
        self.runs = runs
        self.occurrence = occurrence
        self.source = source
        self.effector = effector
        self.telegram = telegram
        self.processor = processor
        self.now = now

    def prepare_manually(self, *, text: str = "持久化的推荐") -> AutomationOccurrence:
        self.repository.prepare(
            occurrence_id=self.occurrence.occurrence_id,
            worker_id="worker-a",
            effect_request_id=f"scheduled:{self.occurrence.occurrence_id}",
            primary_key="dish:noodles",
            payload={"kind": "food_recommendation"},
            text=text,
        )
        prepared = self.repository.get_occurrence(occurrence_id=self.occurrence.occurrence_id)
        assert prepared is not None
        return prepared


class ScheduledFixtureContext:
    def __init__(self, *, send_error: TelegramApiError | None = None) -> None:
        self.send_error = send_error
        self.database_context = temporary_database()

    def __enter__(self) -> ScheduledFixture:
        database = self.database_context.__enter__()
        bundle = load_character_bundle(Path(__file__).parent / "fixtures/personas/test-original/v1")
        repository = AutomationRepository(database)
        delivery_repository = AutomationDeliveryRepository(database)
        config = repository.enable_group(chat_id="-1001", location_text="上海浦东")
        repository.subscribe(chat_id="-1001", member_user_id="member-1")
        occurrence = repository.create_occurrence(
            bot_user_id="7",
            config=config,
            local_date=date(2026, 8, 3),
            slot=MealSlot.LUNCH,
            persona=bundle.snapshot,
        )
        assert occurrence is not None
        now = occurrence.scheduled_for + timedelta(minutes=1)
        leased = repository.lease(
            occurrence_id=occurrence.occurrence_id,
            worker_id="worker-a",
            now=now,
            expected_config_version=config.config_version,
        )
        assert leased is not None
        source = repository.scheduled_source(occurrence=leased)
        runs = RunRepository(database)
        messages = MessageRepository(database)
        messages.policies.ensure(chat_id="-1001")
        messages.policies.activate_persona(chat_id="-1001", persona=bundle.snapshot)
        effector = ScriptedEffector(bundle)
        telegram = RecordingTelegram(self.send_error)
        processor = ScheduledFoodProcessor(
            repository=repository,
            delivery_repository=delivery_repository,
            effector=effector,  # type: ignore[arg-type]
            telegram=telegram,  # type: ignore[arg-type]
            messages=messages,
            runs=runs,
            bundle=bundle,
            allowed_chat_id="-1001",
            bot_user_id="7",
            bot_display_name="agent",
            clock=lambda: now,
        )
        self.fixture = ScheduledFixture(
            bundle=bundle,
            repository=repository,
            delivery_repository=delivery_repository,
            runs=runs,
            occurrence=leased,
            source=source,
            effector=effector,
            telegram=telegram,
            processor=processor,
            now=now,
        )
        return self.fixture

    def __exit__(self, *args: object) -> None:
        self.database_context.__exit__(*args)


if __name__ == "__main__":
    unittest.main()
