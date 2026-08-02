from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from group_llm_agent.events import (
    ExternalEffectKind,
    FinalEffect,
    FinalEffectKind,
    PersonaSnapshot,
    TelegramMessage,
)
from group_llm_agent.expression import (
    ExpressionCatalog,
    ExpressionCatalogError,
    validate_runtime_selection,
)
from group_llm_agent.messages import MessageRepository
from group_llm_agent.platforms.telegram import TelegramApiError, TelegramBotApiClient
from group_llm_agent.runs import RunRepository

logger = logging.getLogger(__name__)


class ExternalEffectDelivery:
    """Owns the unique claim and exactly one confirmed visible delivery."""

    def __init__(
        self,
        *,
        client: TelegramBotApiClient,
        messages: MessageRepository,
        runs: RunRepository,
        bot_user_id: str,
        bot_display_name: str,
        expression_catalog_provider: Callable[[], ExpressionCatalog] | None = None,
    ) -> None:
        self.client = client
        self.messages = messages
        self.runs = runs
        self.bot_user_id = bot_user_id
        self.bot_display_name = bot_display_name
        self.expression_catalog_provider = expression_catalog_provider

    def deliver(
        self,
        *,
        event: TelegramMessage,
        final: FinalEffect,
        active_persona: PersonaSnapshot,
    ) -> str:
        if final.kind is FinalEffectKind.SILENCE:
            return "silence"
        if final.kind is FinalEffectKind.STICKER:
            return self._sticker(event=event, final=final, active_persona=active_persona)
        assert final.text is not None
        requested = (
            ExternalEffectKind.REPLY
            if final.kind is FinalEffectKind.REPLY
            else ExternalEffectKind.FAILURE_REPLY
        )
        return self._text(
            event=event,
            text=final.text,
            requested_kind=requested,
            active_persona=active_persona,
        )

    def _text(
        self,
        *,
        event: TelegramMessage,
        text: str,
        requested_kind: ExternalEffectKind,
        active_persona: PersonaSnapshot,
    ) -> str:
        effect_id = self.runs.claim_external_effect(
            message=event,
            effect_kind=requested_kind,
            persona=active_persona,
        )
        if effect_id is None:
            return "duplicate"
        try:
            sent = self.client.send_message(
                chat_id=event.group_id,
                text=text,
                reply_to_message_id=event.message_id,
            )
        except TelegramApiError as error:
            self._record_delivery_error(effect_id, error)
            return "send_failed"
        self.runs.mark_external_sent(
            effect_id,
            platform_message_id=sent.message_id,
            delivered_effect_kind=requested_kind,
        )
        self._record_outbound(event=event, sent_id=sent.message_id, text=text)
        return "sent"

    def _sticker(
        self,
        *,
        event: TelegramMessage,
        final: FinalEffect,
        active_persona: PersonaSnapshot,
    ) -> str:
        assert final.sticker_id is not None
        assert final.catalog_version is not None
        assert final.catalog_digest is not None
        try:
            if self.expression_catalog_provider is None:
                raise ExpressionCatalogError("catalog_unavailable")
            catalog = self.expression_catalog_provider()
            entry = validate_runtime_selection(
                catalog,
                semantic_id=final.sticker_id,
                persona_version=final.persona.persona_version,
                persona_digest=final.persona.persona_digest,
                expected_catalog_version=final.catalog_version,
                expected_catalog_digest=final.catalog_digest,
            )
        except (ExpressionCatalogError, OSError) as error:
            code = getattr(error, "code", "catalog_unavailable")
            logger.info("sticker_degraded reason=sticker_%s", code)
            if not final.fallback_text:
                return "silence"
            return self._text(
                event=event,
                text=final.fallback_text,
                requested_kind=ExternalEffectKind.FAILURE_REPLY,
                active_persona=active_persona,
            )
        effect_id = self.runs.claim_external_effect(
            message=event,
            effect_kind=ExternalEffectKind.STICKER,
            persona=active_persona,
            asset_semantic_id=entry.semantic_id,
        )
        if effect_id is None:
            return "duplicate"
        assert entry.telegram_file_id is not None
        try:
            sent = self.client.send_sticker(
                chat_id=event.group_id,
                sticker=entry.telegram_file_id,
                reply_to_message_id=event.message_id,
            )
        except TelegramApiError as error:
            if _delivery_uncertain(error):
                self.runs.mark_external_uncertain(effect_id, error_code=error.category)
                return "send_uncertain"
            if final.fallback_text:
                return self._claimed_fallback(
                    effect_id=effect_id,
                    event=event,
                    text=final.fallback_text,
                    sticker_error=error.category,
                )
            self.runs.mark_external_failed(effect_id, error_code=error.category)
            return "send_failed"
        if sent.asset_file_unique_id != entry.telegram_file_unique_id:
            self.runs.mark_external_uncertain(
                effect_id,
                error_code="sticker_identity_mismatch",
            )
            return "send_uncertain"
        self.runs.mark_external_sent(
            effect_id,
            platform_message_id=sent.message_id,
            delivered_effect_kind=ExternalEffectKind.STICKER,
        )
        self._record_outbound(
            event=event,
            sent_id=sent.message_id,
            text=f"[sticker:{entry.semantic_id}]",
        )
        return "sticker_sent"

    def _claimed_fallback(
        self,
        *,
        effect_id: int,
        event: TelegramMessage,
        text: str,
        sticker_error: str,
    ) -> str:
        try:
            sent = self.client.send_message(
                chat_id=event.group_id,
                text=text,
                reply_to_message_id=event.message_id,
            )
        except TelegramApiError as error:
            self._record_delivery_error(effect_id, error)
            return "fallback_failed"
        self.runs.mark_external_sent(
            effect_id,
            platform_message_id=sent.message_id,
            delivered_effect_kind=ExternalEffectKind.FAILURE_REPLY,
        )
        self._record_outbound(event=event, sent_id=sent.message_id, text=text)
        logger.info("sticker_degraded reason=%s", sticker_error)
        return "fallback_sent"

    def _record_delivery_error(self, effect_id: int, error: TelegramApiError) -> None:
        if _delivery_uncertain(error):
            self.runs.mark_external_uncertain(effect_id, error_code=error.category)
        else:
            self.runs.mark_external_failed(effect_id, error_code=error.category)

    def _record_outbound(self, *, event: TelegramMessage, sent_id: str, text: str) -> None:
        self.messages.record_outbound(
            chat_id=event.group_id,
            telegram_message_id=sent_id,
            event_id=f"outbound:{event.event_id}",
            bot_user_id=self.bot_user_id,
            bot_display_name=self.bot_display_name,
            text=text,
            sent_at=datetime.now(UTC),
            replied_to_message_id=event.message_id,
        )


def _delivery_uncertain(error: TelegramApiError) -> bool:
    return error.category in {
        "timeout",
        "transport_error",
        "invalid_json",
        "invalid_response",
        "invalid_result",
    }
