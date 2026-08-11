from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import cast

from group_llm_agent.events import EffectRequest, FinalEffect, FinalEffectKind
from group_llm_agent.temporal import (
    FinalizedTemporalText,
    FreshnessMode,
    TemporalContext,
    TemporalContextError,
    TemporalWebEvidence,
    finalize_temporal_text,
)
from group_llm_agent.temporal_audit import TemporalAnswerStatus, TemporalAuditRepository
from group_llm_agent.web_tools import WebToolExecutionResult, WebToolSession


@dataclass
class TemporalRunState:
    repository: TemporalAuditRepository
    request: EffectRequest
    effect_run_id: int
    last_context: TemporalContext | None = None
    web_audit_ids: set[int] = field(default_factory=set)
    web_requested: bool = False

    def record_sample(self, *, ordinal: int, context: TemporalContext) -> None:
        self.repository.record_sample(
            effect_run_id=self.effect_run_id,
            model_call_ordinal=ordinal,
            context=context,
        )
        self.last_context = context

    def record_failed_sample(self, *, ordinal: int, error_code: str) -> None:
        self.last_context = None
        self.repository.record_sample(
            effect_run_id=self.effect_run_id,
            model_call_ordinal=ordinal,
            context=None,
            error_code=error_code,
        )

    def note_web(self, result: WebToolExecutionResult) -> None:
        self.web_requested = True
        self.web_audit_ids.add(result.audit_id)

    def finalize(
        self,
        *,
        final: FinalEffect,
        freshness_mode: FreshnessMode | None,
        context: TemporalContext | None = None,
        latest_web_retrieved_at: datetime | None = None,
        degradation_reason: str | None = None,
    ) -> None:
        status: TemporalAnswerStatus = (
            "degraded"
            if final.kind is FinalEffectKind.FAILURE_REPLY
            else "silence"
            if final.kind is FinalEffectKind.SILENCE
            else "completed"
        )
        self.repository.finalize(
            effect_run_id=self.effect_run_id,
            chat_id=self.request.chat_id,
            trigger_event_id=self.request.trigger_event_id,
            source_kind="scheduled" if self.request.scheduled is not None else "inbound",
            context=context or self.last_context,
            freshness_mode=freshness_mode,
            web_requested=self.web_requested,
            web_audit_ids=tuple(sorted(self.web_audit_ids)),
            latest_web_retrieved_at=latest_web_retrieved_at,
            status=status,
            degradation_reason=degradation_reason,
        )


def finalize_decision_text(
    *,
    text: str,
    freshness_mode: FreshnessMode | None,
    source_result_ids: tuple[str, ...],
    temporal_context: TemporalContext,
    web_session: WebToolSession | None,
) -> FinalizedTemporalText:
    if freshness_mode is None:
        raise TemporalContextError("missing_freshness_mode")
    evidence: tuple[TemporalWebEvidence, ...] = ()
    if source_result_ids:
        if web_session is None:
            raise TemporalContextError("freshness_sources_invalid")
        try:
            evidence = tuple(
                cast(TemporalWebEvidence, item)
                for item in web_session.evidence_for(source_result_ids)
            )
        except ValueError:
            raise TemporalContextError("freshness_sources_invalid") from None
    return finalize_temporal_text(
        text=text,
        context=temporal_context,
        freshness_mode=freshness_mode,
        evidence=(evidence if freshness_mode is FreshnessMode.CURRENT_VERIFIED else ()),
    )
