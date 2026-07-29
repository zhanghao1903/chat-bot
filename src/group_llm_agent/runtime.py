from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event, Thread
from time import sleep as default_sleep
from typing import Protocol

from group_llm_agent.control import MemoryControlService
from group_llm_agent.delivery import SQLiteDeliveryLedger
from group_llm_agent.effector import WriterEffector
from group_llm_agent.events import (
    ExternalEffectKind,
    FinalEffectKind,
    PlatformTriggerKind,
    TelegramTextMessage,
)
from group_llm_agent.messages import MessageRepository
from group_llm_agent.persona import CharacterBundle
from group_llm_agent.platforms.telegram import (
    TelegramAdapter,
    TelegramApiError,
    TelegramBotApiClient,
)
from group_llm_agent.runs import RunRepository
from group_llm_agent.trigger import TriggerCoordinator

logger = logging.getLogger(__name__)

FIXED_REPLY_ACTION = "fixed_reply"
FIXED_REPLY_TEXT = "1"


@dataclass(frozen=True)
class ProcessingOutcome:
    status: str
    chat_id: str | None = None
    message_id: str | None = None


class MessageProcessor(Protocol):
    def handle_message(self, event: TelegramTextMessage) -> ProcessingOutcome: ...


class RecognitionProcessor(Protocol):
    def run_once(self, *, bundle: CharacterBundle) -> bool: ...


class FixedReplyProcessor:
    def __init__(
        self,
        *,
        allowed_chat_id: str,
        bot_user_id: str,
        client: TelegramBotApiClient,
        store: SQLiteDeliveryLedger,
    ) -> None:
        self.allowed_chat_id = allowed_chat_id
        self.bot_user_id = bot_user_id
        self.client = client
        self.store = store

    def handle_message(self, event: TelegramTextMessage) -> ProcessingOutcome:
        if event.group_id != self.allowed_chat_id:
            logger.info(
                "message_ignored reason=other_group chat_id=%s message_id=%s",
                event.group_id,
                event.message_id,
            )
            return ProcessingOutcome("ignored_group", event.group_id, event.message_id)

        if event.sender_id == self.bot_user_id:
            logger.info(
                "message_ignored reason=self_message chat_id=%s message_id=%s",
                event.group_id,
                event.message_id,
            )
            return ProcessingOutcome("ignored_self", event.group_id, event.message_id)

        logger.info(
            "message_received chat_id=%s sender_id=%s message_id=%s",
            event.group_id,
            event.sender_id,
            event.message_id,
        )
        if event.text != FIXED_REPLY_TEXT:
            return ProcessingOutcome("unmatched", event.group_id, event.message_id)

        delivery_id = self.store.claim(
            chat_id=event.group_id,
            message_id=event.message_id,
            action_kind=FIXED_REPLY_ACTION,
        )
        if delivery_id is None:
            logger.info(
                "reply_skipped reason=duplicate chat_id=%s message_id=%s",
                event.group_id,
                event.message_id,
            )
            return ProcessingOutcome("duplicate", event.group_id, event.message_id)

        try:
            self.client.send_message(
                chat_id=event.group_id,
                text=FIXED_REPLY_TEXT,
                reply_to_message_id=event.message_id,
            )
        except TelegramApiError as exc:
            self.store.mark_failed(delivery_id, error_code=exc.category)
            logger.error(
                "reply_failed chat_id=%s message_id=%s error=%s",
                event.group_id,
                event.message_id,
                exc,
            )
            return ProcessingOutcome("send_failed", event.group_id, event.message_id)
        except Exception:
            self.store.mark_failed(delivery_id, error_code="unexpected_error")
            logger.exception(
                "reply_failed chat_id=%s message_id=%s error=unexpected_error",
                event.group_id,
                event.message_id,
            )
            return ProcessingOutcome("send_failed", event.group_id, event.message_id)

        self.store.mark_sent(delivery_id)
        logger.info(
            "reply_sent chat_id=%s message_id=%s",
            event.group_id,
            event.message_id,
        )
        return ProcessingOutcome("sent", event.group_id, event.message_id)


class TelegramPollingService:
    def __init__(
        self,
        *,
        client: TelegramBotApiClient,
        adapter: TelegramAdapter,
        processor: MessageProcessor,
        polling_timeout_seconds: int,
        retry_delay_seconds: int,
        sleep: Callable[[float], None] = default_sleep,
    ) -> None:
        self.client = client
        self.adapter = adapter
        self.processor = processor
        self.polling_timeout_seconds = polling_timeout_seconds
        self.retry_delay_seconds = retry_delay_seconds
        self.sleep = sleep
        self.offset: int | None = None

    def run_once(self) -> int:
        updates = self.client.get_updates(
            offset=self.offset,
            timeout_seconds=self.polling_timeout_seconds,
        )
        for update in updates:
            update_id = _update_id(update)
            if update_id is not None:
                next_offset = update_id + 1
                self.offset = max(self.offset or next_offset, next_offset)
            else:
                logger.warning("update_skipped reason=invalid_update_id")

            try:
                events = self.adapter.normalize_update(update)
            except Exception:
                logger.exception(
                    "update_skipped reason=normalization_error update_id=%s", update_id
                )
                continue

            for event in events:
                try:
                    self.processor.handle_message(event)
                except Exception:
                    logger.exception(
                        "message_failed reason=processing_error update_id=%s chat_id=%s message_id=%s",
                        update_id,
                        event.group_id,
                        event.message_id,
                    )
        return len(updates)

    def run_forever(self) -> None:
        while True:
            try:
                self.run_once()
            except TelegramApiError as exc:
                logger.error("poll_failed error=%s retry_seconds=%s", exc, self.retry_delay_seconds)
                self.sleep(float(self.retry_delay_seconds))


class PersonaMessageProcessor:
    def __init__(
        self,
        *,
        mode: str,
        allowed_chat_id: str,
        bot_user_id: str,
        bot_display_name: str,
        client: TelegramBotApiClient,
        bundle: CharacterBundle,
        messages: MessageRepository,
        runs: RunRepository,
        controls: MemoryControlService,
        triggers: TriggerCoordinator,
        effector: WriterEffector,
        recognition_policy_version: str = "recognition-v1",
    ) -> None:
        if mode not in {"persona_direct", "persona_full"}:
            raise ValueError("Persona runtime requires a persona mode")
        self.mode = mode
        self.allowed_chat_id = allowed_chat_id
        self.bot_user_id = bot_user_id
        self.bot_display_name = bot_display_name
        self.client = client
        self.bundle = bundle
        self.messages = messages
        self.runs = runs
        self.controls = controls
        self.triggers = triggers
        self.effector = effector
        self.recognition_policy_version = recognition_policy_version

    def handle_message(self, event: TelegramTextMessage) -> ProcessingOutcome:
        platform = self.triggers.platform_gate.decide(event)
        if platform.kind is PlatformTriggerKind.CONTROL:
            if (
                self.runs.get_external_effect(
                    chat_id=event.group_id,
                    trigger_event_id=event.event_id,
                )
                is not None
            ):
                return ProcessingOutcome("duplicate", event.group_id, event.message_id)
            outcome = self.controls.handle(event, persona=self.bundle.snapshot)
            return ProcessingOutcome(outcome.status, event.group_id, event.message_id)
        if platform.reason_code in {"other_group", "self_message"}:
            return ProcessingOutcome(platform.reason_code, event.group_id, event.message_id)

        ingested = self.messages.ingest_inbound(
            event,
            persona=self.bundle.snapshot,
            recognition_policy_version=self.recognition_policy_version,
        )
        if (
            self.runs.get_external_effect(
                chat_id=event.group_id,
                trigger_event_id=event.event_id,
            )
            is not None
        ):
            return ProcessingOutcome("duplicate", event.group_id, event.message_id)
        if ingested.duplicate and self.runs.has_terminal_silence(
            chat_id=event.group_id,
            trigger_event_id=event.event_id,
        ):
            return ProcessingOutcome("duplicate", event.group_id, event.message_id)
        post_ingest_platform = self.triggers.platform_gate.decide(event)
        if (
            self.mode == "persona_direct"
            and post_ingest_platform.kind is PlatformTriggerKind.CONTEXTUAL_CANDIDATE
        ):
            return ProcessingOutcome("persona_direct_only", event.group_id, event.message_id)
        evaluation = self.triggers.evaluate(
            message=event,
            bundle=self.bundle,
        )
        if evaluation.effect_request is None:
            return ProcessingOutcome(
                evaluation.platform.reason_code,
                event.group_id,
                event.message_id,
            )
        final = self.effector.execute(
            request=evaluation.effect_request,
            bundle=self.bundle,
        )
        if final.kind is FinalEffectKind.SILENCE:
            return ProcessingOutcome("silence", event.group_id, event.message_id)
        assert final.text is not None
        effect_kind = (
            ExternalEffectKind.REPLY
            if final.kind is FinalEffectKind.REPLY
            else ExternalEffectKind.FAILURE_REPLY
        )
        effect_id = self.runs.claim_external_effect(
            message=event,
            effect_kind=effect_kind,
            persona=self.bundle.snapshot,
        )
        if effect_id is None:
            return ProcessingOutcome("duplicate", event.group_id, event.message_id)
        try:
            sent = self.client.send_message(
                chat_id=event.group_id,
                text=final.text,
                reply_to_message_id=event.message_id,
            )
        except TelegramApiError as error:
            if error.category in {
                "timeout",
                "transport_error",
                "invalid_json",
                "invalid_response",
                "invalid_result",
            }:
                self.runs.mark_external_uncertain(effect_id, error_code=error.category)
            else:
                self.runs.mark_external_failed(effect_id, error_code=error.category)
            return ProcessingOutcome("send_failed", event.group_id, event.message_id)

        self.runs.mark_external_sent(
            effect_id,
            platform_message_id=sent.message_id,
        )
        self.messages.record_outbound(
            chat_id=event.group_id,
            telegram_message_id=sent.message_id,
            event_id=f"outbound:{event.event_id}",
            bot_user_id=self.bot_user_id,
            bot_display_name=self.bot_display_name,
            text=final.text,
            sent_at=datetime.now(UTC),
            replied_to_message_id=event.message_id,
        )
        return ProcessingOutcome("sent", event.group_id, event.message_id)


class RecognitionBackgroundWorker:
    def __init__(
        self,
        *,
        worker: RecognitionProcessor,
        bundle: CharacterBundle,
        idle_seconds: float = 1.0,
    ) -> None:
        if not 0.05 <= idle_seconds <= 60:
            raise ValueError("idle_seconds must be in [0.05, 60]")
        self.worker = worker
        self.bundle = bundle
        self.idle_seconds = idle_seconds
        self._stop = Event()
        self._thread: Thread | None = None

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_alive:
            raise RuntimeError("Recognition worker is already running")
        self._stop.clear()
        self._thread = Thread(
            target=self._run,
            name="member-recognition",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout_seconds: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout_seconds)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                processed = self.worker.run_once(bundle=self.bundle)
            except Exception:
                logger.exception("recognition_worker_iteration_failed")
                processed = False
            if not processed:
                self._stop.wait(self.idle_seconds)


def _update_id(update: dict[str, object]) -> int | None:
    value = update.get("update_id")
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, str, bytes, bytearray)):
        return None
    try:
        return int(value)
    except ValueError:
        return None
