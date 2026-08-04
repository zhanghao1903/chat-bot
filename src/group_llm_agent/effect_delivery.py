from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from group_llm_agent.effect_bundle import (
    BundleComponent,
    BundleStatus,
    EffectBundleRecord,
    EffectBundleRepository,
)
from group_llm_agent.events import FinalEffect, FinalEffectKind, PersonaSnapshot, TelegramMessage
from group_llm_agent.expression import (
    ExpressionCatalog,
    ExpressionCatalogError,
    ExpressionEntry,
    validate_runtime_selection,
)
from group_llm_agent.messages import MessageRepository
from group_llm_agent.platforms.telegram import TelegramApiError, TelegramBotApiClient
from group_llm_agent.runs import RunRepository

logger = logging.getLogger(__name__)


class ExternalEffectDelivery:
    """Delivers one bounded inbound persona bundle with at-most-once components."""

    def __init__(
        self,
        *,
        client: TelegramBotApiClient,
        messages: MessageRepository,
        bot_user_id: str,
        bot_display_name: str,
        bundles: EffectBundleRepository | None = None,
        runs: RunRepository | None = None,
        expression_catalog_provider: Callable[[], ExpressionCatalog] | None = None,
    ) -> None:
        self.client = client
        self.messages = messages
        if bundles is None and runs is None:
            raise ValueError("bundle repository is required")
        if bundles is None:
            assert runs is not None
            bundles = EffectBundleRepository(runs.database)
        self.bundles = bundles
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
        bundle = self.bundles.prepare(
            event=event,
            final=final,
            bot_user_id=self.bot_user_id,
        )
        if bundle is None:
            self.bundles.reconcile_incomplete(
                chat_id=event.group_id,
                trigger_event_id=event.event_id,
            )
            return "duplicate"

        for component in bundle.components:
            outcome = self._deliver_component(
                bundle=bundle,
                component=component,
                event=event,
                final=final,
                active_persona=active_persona,
            )
            if outcome in {"failed", "uncertain"} and component.component_kind == "text":
                self.bundles.skip_planned(
                    bundle_id=bundle.bundle_id,
                    error_code=f"text_{outcome}",
                )
                break
            if outcome == "uncertain":
                self.bundles.skip_planned(
                    bundle_id=bundle.bundle_id,
                    error_code="prior_component_uncertain",
                )
                break

        status = self.bundles.finalize(bundle_id=bundle.bundle_id)
        return _delivery_status(bundle.requested_form, status)

    def _deliver_component(
        self,
        *,
        bundle: EffectBundleRecord,
        component: BundleComponent,
        event: TelegramMessage,
        final: FinalEffect,
        active_persona: PersonaSnapshot,
    ) -> str:
        component_id = self.bundles.claim_component(
            bundle_id=bundle.bundle_id,
            ordinal=component.ordinal,
        )
        if component_id is None:
            return "duplicate"
        if component.component_kind == "text":
            assert final.text is not None
            try:
                sent = self.client.send_message(
                    chat_id=event.group_id,
                    text=final.text,
                    reply_to_message_id=event.message_id,
                )
            except TelegramApiError as error:
                return self._record_error(component_id, error)
            self.bundles.mark_sent(component_id, platform_message_id=sent.message_id)
            self._record_outbound(
                event=event,
                ordinal=component.ordinal,
                sent_id=sent.message_id,
                text=final.text,
            )
            return "sent"

        try:
            entry = self._sticker_entry(final=final, active_persona=active_persona)
        except (ExpressionCatalogError, OSError) as error:
            code = getattr(error, "code", "catalog_unavailable")
            self.bundles.mark_failed(component_id, error_code=f"sticker_{code}")
            return "failed"
        assert entry.telegram_file_id is not None
        try:
            sent = self.client.send_sticker(
                chat_id=event.group_id,
                sticker=entry.telegram_file_id,
                reply_to_message_id=event.message_id,
            )
        except TelegramApiError as error:
            return self._record_error(component_id, error)
        if sent.asset_file_unique_id != entry.telegram_file_unique_id:
            self.bundles.mark_uncertain(
                component_id,
                error_code="sticker_identity_mismatch",
            )
            return "uncertain"
        self.bundles.mark_sent(component_id, platform_message_id=sent.message_id)
        self._record_outbound(
            event=event,
            ordinal=component.ordinal,
            sent_id=sent.message_id,
            text=f"[sticker:{entry.semantic_id}]",
        )
        return "sent"

    def _sticker_entry(
        self,
        *,
        final: FinalEffect,
        active_persona: PersonaSnapshot,
    ) -> ExpressionEntry:
        if self.expression_catalog_provider is None:
            raise ExpressionCatalogError("catalog_unavailable")
        if (
            final.sticker_id is None
            or final.catalog_version is None
            or final.catalog_digest is None
        ):
            raise ExpressionCatalogError("invalid_final_sticker")
        catalog = self.expression_catalog_provider()
        return validate_runtime_selection(
            catalog,
            semantic_id=final.sticker_id,
            persona_version=active_persona.persona_version,
            persona_digest=active_persona.persona_digest,
            expected_catalog_version=final.catalog_version,
            expected_catalog_digest=final.catalog_digest,
        )

    def _record_error(self, component_id: int, error: TelegramApiError) -> str:
        if _delivery_uncertain(error):
            self.bundles.mark_uncertain(component_id, error_code=error.category)
            return "uncertain"
        self.bundles.mark_failed(component_id, error_code=error.category)
        return "failed"

    def _record_outbound(
        self,
        *,
        event: TelegramMessage,
        ordinal: int,
        sent_id: str,
        text: str,
    ) -> None:
        self.messages.record_outbound(
            chat_id=event.group_id,
            telegram_message_id=sent_id,
            event_id=f"outbound:{event.event_id}:{ordinal}",
            bot_user_id=self.bot_user_id,
            bot_display_name=self.bot_display_name,
            text=text,
            sent_at=datetime.now(UTC),
            replied_to_message_id=event.message_id,
        )


def _delivery_uncertain(error: TelegramApiError) -> bool:
    if error.category in {
        "timeout",
        "transport_error",
        "invalid_json",
        "invalid_response",
        "invalid_result",
    }:
        return True
    return error.category in {"http_error", "api_error"} and (
        error.status_code is None or error.status_code >= 500
    )


def _delivery_status(requested_form: str, status: BundleStatus) -> str:
    if status is BundleStatus.COMPLETED:
        if requested_form == "sticker":
            return "sticker_sent"
        if requested_form == "text_sticker":
            return "composite_sent"
        return "sent"
    if status is BundleStatus.DEGRADED:
        return "text_sent_sticker_failed"
    if status is BundleStatus.UNCERTAIN:
        return "send_uncertain"
    if status is BundleStatus.FAILED:
        return "send_failed"
    return "send_interrupted"
