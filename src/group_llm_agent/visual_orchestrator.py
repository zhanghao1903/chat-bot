from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from group_llm_agent.events import MediaKind, PersonaSnapshot, TelegramMessage
from group_llm_agent.expression import ExpressionCatalog, ExpressionCatalogError
from group_llm_agent.media import MediaProcessingError, TelegramMediaLoader
from group_llm_agent.messages import MessageRepository
from group_llm_agent.runs import RunRepository
from group_llm_agent.vision import (
    VisionApiError,
    VisionEvidence,
    VisionModelPort,
    VisionResultError,
)


@dataclass(frozen=True)
class VisualResolution:
    evidence: VisionEvidence | None = None
    error_code: str | None = None


class VisualEvidenceService:
    """Runs bounded visual IO only after the trigger produced an effect request."""

    def __init__(
        self,
        *,
        messages: MessageRepository,
        runs: RunRepository,
        media_loader: TelegramMediaLoader | None,
        vision: VisionModelPort | None,
        persona: PersonaSnapshot,
        expression_catalog_provider: Callable[[], ExpressionCatalog] | None = None,
    ) -> None:
        self.messages = messages
        self.runs = runs
        self.media_loader = media_loader
        self.vision = vision
        self.persona = persona
        self.expression_catalog_provider = expression_catalog_provider

    def resolve(self, *, event: TelegramMessage, deadline: datetime) -> VisualResolution:
        if event.media is None:
            return VisualResolution()
        catalog_evidence = self._known_sticker(event)
        if catalog_evidence is not None:
            self.runs.record_media_effect_audit(
                chat_id=event.group_id,
                trigger_event_id=event.event_id,
                media_kind=event.media.kind,
                model_id=catalog_evidence.model_id,
                result_status="catalog_match",
            )
            return VisualResolution(evidence=catalog_evidence)
        if self.media_loader is None or self.vision is None:
            self.runs.record_media_effect_audit(
                chat_id=event.group_id,
                trigger_event_id=event.event_id,
                media_kind=event.media.kind,
                result_status="failed",
                error_code="vision_disabled",
            )
            return VisualResolution(error_code="vision_disabled")
        try:
            normalized = self.media_loader.load(event.media)
            recent_scene = self.messages.recent(chat_id=event.group_id, limit=8)
            evidence = self.vision.analyze(
                media=normalized,
                caption=event.text,
                recent_scene=tuple(item.text for item in recent_scene),
                deadline=deadline,
            )
            self.runs.record_media_effect_audit(
                chat_id=event.group_id,
                trigger_event_id=event.event_id,
                media_kind=event.media.kind,
                media_bytes=len(normalized.content),
                media_pixels=normalized.width * normalized.height,
                model_id=evidence.model_id,
                result_status="completed",
            )
            return VisualResolution(evidence=evidence)
        except (MediaProcessingError, VisionApiError, VisionResultError) as error:
            error_code = str(getattr(error, "category", "invalid_result"))
            self.runs.record_media_effect_audit(
                chat_id=event.group_id,
                trigger_event_id=event.event_id,
                media_kind=event.media.kind,
                result_status="failed",
                error_code=error_code,
            )
            return VisualResolution(error_code=error_code)

    def _known_sticker(self, event: TelegramMessage) -> VisionEvidence | None:
        assert event.media is not None
        if (
            event.media.kind is not MediaKind.STATIC_STICKER
            or self.expression_catalog_provider is None
        ):
            return None
        try:
            catalog = self.expression_catalog_provider()
        except (ExpressionCatalogError, OSError):
            return None
        if (
            catalog.status != "enabled"
            or catalog.persona_id != self.persona.persona_id
            or catalog.persona_version != self.persona.persona_version
            or catalog.persona_digest != self.persona.persona_digest
        ):
            return None
        entry = next(
            (
                item
                for item in catalog.entries
                if item.status == "enabled"
                and item.telegram_file_unique_id == event.media.file_unique_id
            ),
            None,
        )
        if entry is None:
            return None
        return VisionEvidence(
            summary=entry.content_summary,
            visible_text=(entry.visible_text,),
            observations=(entry.action,),
            inferences=(f"interaction_intent={entry.interaction_intent}",),
            uncertainties=(),
            safety_flags=("known_enabled_sticker",),
            media_sha256=sha256(event.media.file_unique_id.encode("utf-8")).hexdigest(),
            model_id=f"catalog:{catalog.catalog_version}",
        )
