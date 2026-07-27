from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from time import sleep as default_sleep

from group_llm_agent.delivery import SQLiteDeliveryLedger
from group_llm_agent.events import TelegramTextMessage
from group_llm_agent.platforms.telegram import (
    TelegramAdapter,
    TelegramApiError,
    TelegramBotApiClient,
)

logger = logging.getLogger(__name__)

FIXED_REPLY_ACTION = "fixed_reply"
FIXED_REPLY_TEXT = "1"


@dataclass(frozen=True)
class ProcessingOutcome:
    status: str
    chat_id: str | None = None
    message_id: str | None = None


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
        processor: FixedReplyProcessor,
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
