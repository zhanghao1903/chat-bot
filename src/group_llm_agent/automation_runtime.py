from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from threading import Event, Thread
from typing import Protocol
from zoneinfo import ZoneInfo

from group_llm_agent.automation import (
    AutomationOccurrence,
    AutomationRepository,
    GroupAutomationConfig,
    MealSlot,
    OccurrenceStatus,
    scheduled_instant,
)
from group_llm_agent.events import PersonaSnapshot, ScheduledOccurrenceSource

logger = logging.getLogger(__name__)


class ScheduledOccurrenceProcessor(Protocol):
    def process(
        self,
        *,
        occurrence: AutomationOccurrence,
        source: ScheduledOccurrenceSource,
    ) -> OccurrenceStatus: ...


class AutomationScheduler:
    def __init__(
        self,
        *,
        repository: AutomationRepository,
        processor: ScheduledOccurrenceProcessor,
        bot_user_id: str,
        persona: PersonaSnapshot,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not bot_user_id:
            raise ValueError("bot_user_id must not be empty")
        self.repository = repository
        self.processor = processor
        self.bot_user_id = bot_user_id
        self.persona = persona
        self.clock = clock or (lambda: datetime.now(UTC))

    def run_once(self, *, worker_id: str) -> int:
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("scheduler clock must be timezone-aware")
        processed = 0
        for config in self.repository.list_configs():
            for local_date, slot in _due_candidates(config=config, now=now):
                occurrence = self.repository.create_occurrence(
                    bot_user_id=self.bot_user_id,
                    config=config,
                    local_date=local_date,
                    slot=slot,
                    persona=self.persona,
                )
                if occurrence is None or occurrence.status is not OccurrenceStatus.DUE:
                    continue
                outcome = self._eligibility(config=config, occurrence=occurrence, now=now)
                if outcome is not None:
                    self.repository.mark_occurrence(
                        occurrence_id=occurrence.occurrence_id,
                        status=outcome,
                        reason_code=outcome.value,
                    )
                    processed += 1
                    continue
                leased = self.repository.lease(
                    occurrence_id=occurrence.occurrence_id,
                    worker_id=worker_id,
                    now=now,
                )
                if leased is None:
                    continue
                try:
                    current = self.repository.get_config(chat_id=config.chat_id)
                    if current is None or not current.enabled or current.paused:
                        result = OccurrenceStatus.SKIPPED_DISABLED
                    elif current.config_version != leased.config_version:
                        result = OccurrenceStatus.DEFINITE_FAILURE
                    else:
                        aggregate = self.repository.aggregate_preferences(chat_id=config.chat_id)
                        if aggregate.subscriber_count == 0:
                            result = OccurrenceStatus.SKIPPED_NO_SUBSCRIBERS
                        elif now > leased.grace_deadline:
                            result = OccurrenceStatus.SKIPPED_LATE
                        else:
                            source = self.repository.scheduled_source(occurrence=leased)
                            result = self.processor.process(occurrence=leased, source=source)
                except Exception:
                    logger.exception(
                        "automation_occurrence_failed occurrence_id=%s",
                        leased.occurrence_id,
                    )
                    result = OccurrenceStatus.DEFINITE_FAILURE
                if result not in {OccurrenceStatus.PREPARED, OccurrenceStatus.SENDING}:
                    self.repository.mark_occurrence(
                        occurrence_id=leased.occurrence_id,
                        status=result,
                        reason_code=result.value,
                    )
                processed += 1
        return processed

    def _eligibility(
        self,
        *,
        config: GroupAutomationConfig,
        occurrence: AutomationOccurrence,
        now: datetime,
    ) -> OccurrenceStatus | None:
        if not config.enabled or config.paused:
            return OccurrenceStatus.SKIPPED_DISABLED
        if self.repository.aggregate_preferences(chat_id=config.chat_id).subscriber_count == 0:
            return OccurrenceStatus.SKIPPED_NO_SUBSCRIBERS
        if now > occurrence.grace_deadline:
            return OccurrenceStatus.SKIPPED_LATE
        return None


class AutomationBackgroundWorker:
    def __init__(
        self,
        *,
        scheduler: AutomationScheduler,
        worker_id: str,
        idle_seconds: float = 15.0,
    ) -> None:
        if not 0.05 <= idle_seconds <= 60:
            raise ValueError("idle_seconds must be in [0.05, 60]")
        if not worker_id:
            raise ValueError("worker_id must not be empty")
        self.scheduler = scheduler
        self.worker_id = worker_id
        self.idle_seconds = idle_seconds
        self._stop = Event()
        self._thread: Thread | None = None

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_alive:
            return
        self._stop.clear()
        self._thread = Thread(target=self._run, name="automation-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.idle_seconds + 1.0))

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.scheduler.run_once(worker_id=self.worker_id)
            except Exception:
                logger.exception("automation_scheduler_tick_failed")
            self._stop.wait(self.idle_seconds)


def next_scheduled(config: GroupAutomationConfig, *, after: datetime) -> datetime | None:
    if after.tzinfo is None:
        raise ValueError("after must be timezone-aware")
    local = after.astimezone(ZoneInfo(config.timezone))
    for offset in range(8):
        candidate_date = local.date() + timedelta(days=offset)
        for slot in (MealSlot.LUNCH, MealSlot.DINNER):
            candidate = scheduled_instant(
                local_date=candidate_date,
                slot=slot,
                timezone=config.timezone,
                lunch_time=config.lunch_time,
                dinner_time=config.dinner_time,
            )
            if candidate is not None and candidate > after.astimezone(UTC):
                return candidate
    return None


def _due_candidates(
    *, config: GroupAutomationConfig, now: datetime
) -> tuple[tuple[date, MealSlot], ...]:
    local_now = now.astimezone(ZoneInfo(config.timezone))
    candidates: list[tuple[date, MealSlot, datetime]] = []
    for local_date in (local_now.date() - timedelta(days=1), local_now.date()):
        for slot in (MealSlot.LUNCH, MealSlot.DINNER):
            scheduled = scheduled_instant(
                local_date=local_date,
                slot=slot,
                timezone=config.timezone,
                lunch_time=config.lunch_time,
                dinner_time=config.dinner_time,
            )
            if scheduled is None or scheduled > now.astimezone(UTC):
                continue
            if local_date != local_now.date() and now - scheduled > timedelta(minutes=30):
                continue
            candidates.append((local_date, slot, scheduled))
    candidates.sort(key=lambda item: item[2])
    return tuple((local_date, slot) for local_date, slot, _ in candidates)
