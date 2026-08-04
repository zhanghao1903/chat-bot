from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from group_llm_agent.automation import (
    AutomationOccurrence,
    AutomationRepository,
    OccurrenceStatus,
)
from group_llm_agent.automation_delivery import AutomationDeliveryRepository
from group_llm_agent.effector import WriterEffector
from group_llm_agent.events import (
    EffectRequest,
    ExternalEffectKind,
    ExternalEffectStatus,
    FinalEffectKind,
    ScheduledOccurrenceSource,
    TriggerCategory,
    TriggerPath,
)
from group_llm_agent.messages import MessageRepository
from group_llm_agent.persona import CharacterBundle
from group_llm_agent.platforms.telegram import TelegramApiError, TelegramBotApiClient
from group_llm_agent.runs import RunRepository


class ScheduledFoodProcessor:
    """Prepare, atomically claim and deliver one scheduled food recommendation."""

    def __init__(
        self,
        *,
        repository: AutomationRepository,
        delivery_repository: AutomationDeliveryRepository,
        effector: WriterEffector,
        telegram: TelegramBotApiClient,
        messages: MessageRepository,
        runs: RunRepository,
        bundle: CharacterBundle,
        allowed_chat_id: str,
        bot_user_id: str,
        bot_display_name: str,
        deadline_seconds: int = 60,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not 15 <= deadline_seconds <= 90:
            raise ValueError("deadline_seconds must be in [15, 90]")
        if not allowed_chat_id or not bot_user_id or not bot_display_name:
            raise ValueError("bot identity must not be empty")
        self.repository = repository
        self.delivery_repository = delivery_repository
        self.effector = effector
        self.telegram = telegram
        self.messages = messages
        self.runs = runs
        self.bundle = bundle
        self.allowed_chat_id = allowed_chat_id
        self.bot_user_id = bot_user_id
        self.bot_display_name = bot_display_name
        self.deadline_seconds = deadline_seconds
        self.clock = clock or (lambda: datetime.now(UTC))

    def recover_inflight(self) -> int:
        return self.delivery_repository.recover_sending_as_uncertain()

    def process(
        self,
        *,
        occurrence: AutomationOccurrence,
        source: ScheduledOccurrenceSource,
        worker_id: str,
    ) -> OccurrenceStatus:
        if (
            occurrence.chat_id != self.allowed_chat_id
            or occurrence.persona != self.bundle.snapshot
            or source.chat_id != occurrence.chat_id
        ):
            return OccurrenceStatus.DEFINITE_FAILURE
        current = occurrence
        if current.status is OccurrenceStatus.LEASED:
            prepared = self._prepare(
                occurrence=current,
                source=source,
                worker_id=worker_id,
            )
            if prepared is None:
                return OccurrenceStatus.DEFINITE_FAILURE
            current = prepared
        if current.status is not OccurrenceStatus.PREPARED:
            return current.status
        return self._deliver(current)

    def _prepare(
        self,
        *,
        occurrence: AutomationOccurrence,
        source: ScheduledOccurrenceSource,
        worker_id: str,
    ) -> AutomationOccurrence | None:
        now = self.clock()
        if now.tzinfo is None or now >= occurrence.grace_deadline:
            return None
        deadline = min(
            now + timedelta(seconds=self.deadline_seconds),
            occurrence.grace_deadline,
        )
        request = EffectRequest(
            request_id=f"scheduled:{occurrence.occurrence_id}",
            trigger_path=TriggerPath.SCHEDULED,
            trigger_category=TriggerCategory.SCHEDULED_AUTOMATION,
            trigger_reason="scheduled_food_due",
            message=None,
            scheduled=source,
            persona=occurrence.persona,
            deadline_at=deadline,
        )
        final = self.effector.execute(request=request, bundle=self.bundle)
        if (
            final.kind is not FinalEffectKind.REPLY
            or final.text is None
            or final.primary_key is None
        ):
            return None
        prepared = self.repository.prepare(
            occurrence_id=occurrence.occurrence_id,
            worker_id=worker_id,
            effect_request_id=request.request_id,
            primary_key=final.primary_key,
            payload={
                "kind": "food_recommendation",
                "primary_key": final.primary_key,
                "source_urls": list(final.source_urls),
            },
            text=final.text,
        )
        if not prepared:
            return None
        return self.repository.get_occurrence(occurrence_id=occurrence.occurrence_id)

    def _deliver(self, occurrence: AutomationOccurrence) -> OccurrenceStatus:
        assert occurrence.prepared_text is not None
        now = self.clock()
        if now.tzinfo is None:
            return OccurrenceStatus.DEFINITE_FAILURE
        try:
            effect_id = self.delivery_repository.claim_prepared(
                occurrence_id=occurrence.occurrence_id,
                persona=self.bundle.snapshot,
                now=now,
            )
        except ValueError:
            return OccurrenceStatus.DEFINITE_FAILURE
        if effect_id is None:
            existing = self.runs.get_external_effect(
                chat_id=occurrence.chat_id,
                trigger_event_id=occurrence.occurrence_id,
            )
            if existing is None:
                return OccurrenceStatus.DEFINITE_FAILURE
            return _occurrence_status(existing.status)
        try:
            sent = self.telegram.send_message(
                chat_id=occurrence.chat_id,
                text=occurrence.prepared_text,
                reply_to_message_id=None,
            )
        except TelegramApiError as error:
            if _delivery_uncertain(error):
                self.runs.mark_external_uncertain(effect_id, error_code=error.category)
                status = OccurrenceStatus.UNCERTAIN
            else:
                self.runs.mark_external_failed(effect_id, error_code=error.category)
                status = OccurrenceStatus.DEFINITE_FAILURE
            self.repository.mark_occurrence(
                occurrence_id=occurrence.occurrence_id,
                status=status,
                reason_code=error.category,
            )
            return status
        except Exception:  # noqa: BLE001 - any post-claim ambiguity must fail closed
            self.runs.mark_external_uncertain(effect_id, error_code="unexpected_send_error")
            self.repository.mark_occurrence(
                occurrence_id=occurrence.occurrence_id,
                status=OccurrenceStatus.UNCERTAIN,
                reason_code="unexpected_send_error",
            )
            return OccurrenceStatus.UNCERTAIN
        self.runs.mark_external_sent(
            effect_id,
            platform_message_id=sent.message_id,
            delivered_effect_kind=ExternalEffectKind.REPLY,
        )
        self.messages.record_outbound(
            chat_id=occurrence.chat_id,
            telegram_message_id=sent.message_id,
            event_id=f"outbound:{occurrence.occurrence_id}",
            bot_user_id=self.bot_user_id,
            bot_display_name=self.bot_display_name,
            text=occurrence.prepared_text,
            sent_at=now,
            replied_to_message_id=None,
        )
        self.repository.mark_occurrence(
            occurrence_id=occurrence.occurrence_id,
            status=OccurrenceStatus.SENT,
            reason_code="telegram_sent",
        )
        return OccurrenceStatus.SENT


def _occurrence_status(status: ExternalEffectStatus) -> OccurrenceStatus:
    if status is ExternalEffectStatus.SENT:
        return OccurrenceStatus.SENT
    if status in {ExternalEffectStatus.SENDING, ExternalEffectStatus.UNCERTAIN}:
        return OccurrenceStatus.UNCERTAIN
    return OccurrenceStatus.DEFINITE_FAILURE


def _delivery_uncertain(error: TelegramApiError) -> bool:
    return error.category in {
        "timeout",
        "transport_error",
        "invalid_json",
        "invalid_response",
        "invalid_result",
    }
