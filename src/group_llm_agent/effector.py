from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from group_llm_agent.context import ContextAssembler, EffectContext
from group_llm_agent.events import (
    EffectRequest,
    FinalEffect,
    FinalEffectKind,
    TriggerPath,
)
from group_llm_agent.expression import (
    ExpressionCatalog,
    ExpressionCatalogError,
    validate_runtime_selection,
)
from group_llm_agent.expression_policy import sticker_selection_error
from group_llm_agent.food_recommendation import validate_food_recommendation
from group_llm_agent.model import (
    ModelApiError,
    ModelResultError,
    ModelRole,
    StructuredModelPort,
    WriterDecisionKind,
    parse_writer_decision,
)
from group_llm_agent.persona import CharacterBundle
from group_llm_agent.runs import RunRepository
from group_llm_agent.tools import ReadOnlyToolRegistry, ToolExecutionResult, ToolExecutionScope
from group_llm_agent.temporal import (
    FreshnessMode,
    SELECT_ANSWER_TIMEZONE,
    FinalizedTemporalText,
    GroupTimezoneProvider,
    StaticGroupTimezoneProvider,
    TemporalContext,
    TemporalContextError,
    TemporalContextFactory,
    TemporalSession,
    TemporalWebEvidence,
    finalize_temporal_text,
)
from group_llm_agent.temporal_audit import TemporalAnswerStatus, TemporalAuditRepository
from group_llm_agent.vision import VisionEvidence
from group_llm_agent.web_tools import (
    WEB_TOOLS,
    WebToolExecutionResult,
    WebToolScope,
    WebToolSession,
)
from group_llm_agent.writer_contract import WRITER_RESPONSE_SCHEMA
from group_llm_agent.writer_prompt import build_writer_model_messages

_DEFAULT_FAILURE_REPLY = "我这会儿有点卡住了，稍后再试试。"
_LEAKAGE_MARKER_PATTERN = re.compile(
    r"(?:BEGIN|END)_UNTRUSTED|"
    r"AVAILABLE_TOOLS|CHARACTER_(?:EFFECTOR|TRIGGER|RECOGNITION)_POLICY|"
    r"CHARACTER_EXAMPLES|UNTRUSTED_(?:GROUP_CONTEXT|GROUP_EVIDENCE|TOOL_RESULT|VISION_EVIDENCE)|"
    r"\b(?:member_memory|memory_id|source_message_ids?|effective_confidence|"
    r"persona_digest|persona_version|recognition_policy_version|tool_name|"
    r"tool_arguments|tool_purpose_code|used_memory_ids|used_tool_call_ids|"
    r"protocol_history|model_calls_remaining|tool_calls_remaining)\b|"
    r"\b(?:system prompt|internal instructions?)\b|系统提示词|内部指令",
    re.IGNORECASE,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class _TemporalRunState:
    repository: TemporalAuditRepository
    request: EffectRequest
    effect_run_id: int
    last_context: TemporalContext | None = None
    web_audit_ids: set[int] | None = None
    web_requested: bool = False

    def __post_init__(self) -> None:
        if self.web_audit_ids is None:
            self.web_audit_ids = set()

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
        assert self.web_audit_ids is not None
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
        final_context = context or self.last_context
        scheduled = self.request.scheduled
        message = self.request.message
        status: TemporalAnswerStatus = (
            "degraded"
            if final.kind is FinalEffectKind.FAILURE_REPLY
            else "silence"
            if final.kind is FinalEffectKind.SILENCE
            else "completed"
        )
        assert self.web_audit_ids is not None
        self.repository.finalize(
            effect_run_id=self.effect_run_id,
            chat_id=scheduled.chat_id if scheduled is not None else message.group_id,  # type: ignore[union-attr]
            trigger_event_id=(
                scheduled.occurrence_id if scheduled is not None else message.event_id  # type: ignore[union-attr]
            ),
            source_kind="scheduled" if scheduled is not None else "inbound",
            context=final_context,
            freshness_mode=freshness_mode,
            web_requested=self.web_requested,
            web_audit_ids=tuple(sorted(self.web_audit_ids)),
            latest_web_retrieved_at=latest_web_retrieved_at,
            status=status,
            degradation_reason=degradation_reason,
        )


@dataclass(frozen=True)
class EffectorBudgets:
    maximum_model_calls: int = 12
    ordinary_tool_calls: int = 3
    maximum_tool_calls: int = 5
    maximum_web_tool_calls: int = 5
    maximum_result_characters: int = 16_384

    def __post_init__(self) -> None:
        if not 1 <= self.maximum_model_calls <= 12:
            raise ValueError("maximum_model_calls must be in [1, 12]")
        if not 0 <= self.ordinary_tool_calls <= 3:
            raise ValueError("ordinary_tool_calls must be in [0, 3]")
        if not self.ordinary_tool_calls <= self.maximum_tool_calls <= 5:
            raise ValueError("maximum_tool_calls must be in [ordinary, 5]")
        if self.maximum_tool_calls >= self.maximum_model_calls:
            raise ValueError("Tool calls must leave one final model call")
        if not 0 <= self.maximum_web_tool_calls <= 5:
            raise ValueError("maximum_web_tool_calls must be in [0, 5]")
        if not 1_024 <= self.maximum_result_characters <= 16_384:
            raise ValueError("maximum_result_characters must be in [1024, 16384]")


class WriterEffector:
    def __init__(
        self,
        *,
        model: StructuredModelPort,
        contexts: ContextAssembler,
        tools: ReadOnlyToolRegistry,
        runs: RunRepository,
        budgets: EffectorBudgets | None = None,
        failure_reply_text: str = _DEFAULT_FAILURE_REPLY,
        clock: Callable[[], datetime] = _utc_now,
        expression_catalog_provider: Callable[[], ExpressionCatalog] | None = None,
        web_session_factory: Callable[[], WebToolSession] | None = None,
        timezone_provider: GroupTimezoneProvider | None = None,
        temporal_factory: TemporalContextFactory | None = None,
        temporal_audit: TemporalAuditRepository | None = None,
    ) -> None:
        if not failure_reply_text.strip() or len(failure_reply_text) > 4_096:
            raise ValueError("failure_reply_text must be non-empty and at most 4096 characters")
        self.model = model
        self.contexts = contexts
        self.tools = tools
        self.runs = runs
        self.budgets = budgets or EffectorBudgets()
        self.failure_reply_text = failure_reply_text
        self.clock = clock
        self.expression_catalog_provider = expression_catalog_provider
        self.web_session_factory = web_session_factory
        self.timezone_provider = timezone_provider or StaticGroupTimezoneProvider()
        self.temporal_factory = temporal_factory or TemporalContextFactory(clock=clock)
        self.temporal_audit = temporal_audit or TemporalAuditRepository(runs.database)

    def execute(
        self,
        *,
        request: EffectRequest,
        bundle: CharacterBundle,
        vision_evidence: VisionEvidence | None = None,
        vision_error_code: str | None = None,
    ) -> FinalEffect:
        effect_run_id = self.runs.start_effect_run(request)
        temporal_run = _TemporalRunState(
            repository=self.temporal_audit,
            request=request,
            effect_run_id=effect_run_id,
        )
        if request.persona != bundle.snapshot:
            return self._degrade(
                request=request,
                effect_run_id=effect_run_id,
                model_call_count=0,
                tool_call_count=0,
                used_tool_call_ids=(),
                reason_code="persona_snapshot_mismatch",
                temporal_run=temporal_run,
            )
        chat_id = (
            request.scheduled.chat_id
            if request.scheduled is not None
            else request.message.group_id  # type: ignore[union-attr]
        )
        try:
            temporal_session = TemporalSession(
                group_timezone=self.timezone_provider.timezone_for(chat_id=chat_id),
                factory=self.temporal_factory,
            )
        except TemporalContextError as error:
            temporal_run.record_failed_sample(ordinal=1, error_code=error.code)
            return self._degrade(
                request=request,
                effect_run_id=effect_run_id,
                model_call_count=0,
                tool_call_count=0,
                used_tool_call_ids=(),
                reason_code=error.code,
                temporal_run=temporal_run,
            )
        if request.scheduled is not None:
            context = self.contexts.scheduled_effect_context(
                bundle=bundle,
                scheduled=request.scheduled,
                model_calls_remaining=self.budgets.maximum_model_calls,
                tool_calls_remaining=self.budgets.maximum_tool_calls,
                web_tool_calls_remaining=self.budgets.maximum_web_tool_calls,
                deadline_at=request.deadline_at,
            )
        else:
            assert request.message is not None
            context = self.contexts.effect_context(
                bundle=bundle,
                message=request.message,
                trigger_path=request.trigger_path,
                model_calls_remaining=self.budgets.maximum_model_calls,
                tool_calls_remaining=self.budgets.maximum_tool_calls,
                deadline_at=request.deadline_at,
                vision_evidence=vision_evidence,
                vision_error_code=vision_error_code,
            )
        catalog = self._load_catalog()
        web_session = self.web_session_factory() if self.web_session_factory is not None else None
        history: list[str] = []
        tool_results: list[ToolExecutionResult | WebToolExecutionResult] = []
        result_fingerprints: set[str] = set()
        last_context_result_novel = False
        tool_call_count = 0
        context_tool_call_count = 0
        web_tool_call_count = 0
        result_character_count = 0

        for model_call_number in range(1, self.budgets.maximum_model_calls + 1):
            try:
                temporal_context = temporal_session.sample_for_model_call()
            except TemporalContextError as error:
                temporal_run.record_failed_sample(
                    ordinal=model_call_number,
                    error_code=error.code,
                )
                return self._degrade(
                    request=request,
                    effect_run_id=effect_run_id,
                    model_call_count=model_call_number - 1,
                    tool_call_count=tool_call_count,
                    used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                    reason_code=error.code,
                    temporal_run=temporal_run,
                )
            temporal_run.record_sample(ordinal=model_call_number, context=temporal_context)
            can_call_tool = model_call_number < self.budgets.maximum_model_calls
            allowed_context_tools = (
                self.tools.allowed_tools
                if can_call_tool and context_tool_call_count < self.budgets.maximum_tool_calls
                else frozenset()
            )
            allowed_web_tools = (
                WEB_TOOLS
                if can_call_tool
                and web_session is not None
                and web_tool_call_count < self.budgets.maximum_web_tool_calls
                else frozenset()
            )
            allowed_temporal_tools = (
                frozenset({SELECT_ANSWER_TIMEZONE})
                if can_call_tool and temporal_session.selection_available
                else frozenset()
            )
            allowed_tools = allowed_context_tools | allowed_web_tools | allowed_temporal_tools
            tools_enabled = bool(allowed_tools)
            messages = build_writer_model_messages(
                context,
                temporal_context=temporal_context,
                allowed_tools=allowed_tools,
                history=tuple(history),
                tool_results=tuple(tool_results),
                model_calls_remaining=self.budgets.maximum_model_calls - model_call_number + 1,
                tool_calls_remaining=self.budgets.maximum_tool_calls - context_tool_call_count,
                web_tool_calls_remaining=self.budgets.maximum_web_tool_calls - web_tool_call_count,
                catalog=catalog,
            )
            try:
                result = self.model.complete(
                    model_role=ModelRole.WRITER,
                    messages=messages,
                    response_schema=WRITER_RESPONSE_SCHEMA,
                    deadline=request.deadline_at,
                    max_output_tokens=1_200,
                    temperature=0.7,
                )
            except ModelApiError as error:
                return self._degrade(
                    request=request,
                    effect_run_id=effect_run_id,
                    model_call_count=model_call_number,
                    tool_call_count=tool_call_count,
                    used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                    reason_code=f"model_{error.category.value}",
                    temporal_run=temporal_run,
                )
            try:
                decision = parse_writer_decision(
                    result,
                    allowed_tools=allowed_tools,
                    expected_temporal_context_id=temporal_context.context_id,
                )
            except ModelResultError as error:
                raw_kind = result.payload.get("kind")
                if raw_kind == WriterDecisionKind.CALL_TOOL.value and can_call_tool:
                    capability = str(result.payload.get("tool_name") or "invalid")
                    purpose_code = str(result.payload.get("tool_purpose_code") or "invalid")
                    rejected: ToolExecutionResult | WebToolExecutionResult | None = None
                    budget_ordinal = 0
                    if capability == SELECT_ANSWER_TIMEZONE:
                        history.append("writer_protocol_error:invalid_timezone_selection")
                    elif capability in WEB_TOOLS:
                        if (
                            web_session is not None
                            and web_tool_call_count < self.budgets.maximum_web_tool_calls
                        ):
                            rejected = web_session.record_rejected_attempt(
                                scope=self._web_tool_scope(
                                    context=context,
                                    effect_run_id=effect_run_id,
                                ),
                                capability=capability,
                                purpose_code=purpose_code,
                                status=error.category,
                            )
                            web_tool_call_count += 1
                            budget_ordinal = web_tool_call_count
                        else:
                            history.append("writer_protocol_error:web_tool_budget_exhausted")
                    elif context_tool_call_count < self.budgets.maximum_tool_calls:
                        rejected = self.tools.record_rejected_attempt(
                            scope=self._tool_scope(
                                context=context,
                                effect_run_id=effect_run_id,
                            ),
                            capability=capability,
                            purpose_code=purpose_code,
                            status=error.category,
                        )
                        context_tool_call_count += 1
                        budget_ordinal = context_tool_call_count
                    if rejected is not None:
                        if isinstance(rejected, WebToolExecutionResult):
                            temporal_run.note_web(rejected)
                        tool_results.append(rejected)
                        tool_call_count += 1
                        result_character_count += rejected.result_char_count
                        self.runs.annotate_tool_call(
                            rejected.audit_id,
                            budget_ordinal=budget_ordinal,
                            extension_reason_code=None,
                            result_novel=False,
                        )
                        if capability not in WEB_TOOLS:
                            last_context_result_novel = False
                        if result_character_count > self.budgets.maximum_result_characters:
                            return self._degrade(
                                request=request,
                                effect_run_id=effect_run_id,
                                model_call_count=model_call_number,
                                tool_call_count=tool_call_count,
                                used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                                reason_code="tool_result_budget_exhausted",
                                temporal_run=temporal_run,
                            )
                if model_call_number < self.budgets.maximum_model_calls:
                    history.append(f"writer_protocol_error:{error.category}")
                    continue
                return self._silence(
                    request=request,
                    effect_run_id=effect_run_id,
                    model_call_count=model_call_number,
                    tool_call_count=tool_call_count,
                    used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                    reason_code=f"writer_{error.category}",
                    temporal_run=temporal_run,
                )

            if decision.kind is WriterDecisionKind.FOOD_RECOMMENDATION:
                if request.scheduled is None:
                    return self._degrade(
                        request=request,
                        effect_run_id=effect_run_id,
                        model_call_count=model_call_number,
                        tool_call_count=tool_call_count,
                        used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                        reason_code="food_not_scheduled",
                        temporal_run=temporal_run,
                    )
                completed_at = self.clock()

                def validate_food_text(
                    text: str | None,
                    completed_at: datetime = completed_at,
                ) -> str | None:
                    return _final_effect_validation_error(
                        request=request,
                        bundle=bundle,
                        text=text,
                        completed_at=completed_at,
                    )

                food, validation_error = validate_food_recommendation(
                    decision=decision,
                    request=request,
                    citations=(web_session.citations if web_session is not None else {}),
                    validate_text=validate_food_text,
                )
                if food is None:
                    return self._degrade(
                        request=request,
                        effect_run_id=effect_run_id,
                        model_call_count=model_call_number,
                        tool_call_count=tool_call_count,
                        used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                        reason_code=validation_error or "food_invalid",
                        temporal_run=temporal_run,
                    )
                final = FinalEffect(
                    kind=FinalEffectKind.REPLY,
                    reason_code=decision.reason_code,
                    persona=request.persona,
                    text=food.text,
                    used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                    primary_key=food.primary_key,
                    source_urls=food.source_urls,
                )
                self._complete_effect(
                    effect_run_id=effect_run_id,
                    effect=final,
                    model_call_count=model_call_number,
                    tool_call_count=tool_call_count,
                    temporal_run=temporal_run,
                    freshness_mode=None,
                    context=temporal_context,
                )
                return final

            if (
                decision.kind is WriterDecisionKind.CALL_TOOL
                and decision.tool_name == SELECT_ANSWER_TIMEZONE
            ):
                arguments = decision.tool_arguments
                try:
                    if not isinstance(arguments, dict) or set(arguments) != {"timezone"}:
                        raise TemporalContextError("invalid_timezone_selection_arguments")
                    timezone = arguments["timezone"]
                    if not isinstance(timezone, str):
                        raise TemporalContextError("invalid_timezone_selection_arguments")
                    temporal_session.select_answer_timezone(timezone)
                except TemporalContextError as error:
                    if model_call_number < self.budgets.maximum_model_calls:
                        history.append(f"writer_protocol_error:{error.code}")
                        continue
                    return self._silence(
                        request=request,
                        effect_run_id=effect_run_id,
                        model_call_count=model_call_number,
                        tool_call_count=tool_call_count,
                        used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                        reason_code=error.code,
                        temporal_run=temporal_run,
                    )
                history.append(
                    f"answer_timezone_selected:{temporal_session.answer_timezone}"
                )
                continue

            if request.scheduled is not None and decision.kind not in {
                WriterDecisionKind.SILENCE,
                WriterDecisionKind.CALL_TOOL,
            }:
                return self._degrade(
                    request=request,
                    effect_run_id=effect_run_id,
                    model_call_count=model_call_number,
                    tool_call_count=tool_call_count,
                    used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                    reason_code="scheduled_invalid_final_kind",
                    temporal_run=temporal_run,
                )

            if decision.kind is WriterDecisionKind.REPLY:
                assert decision.text is not None
                try:
                    temporal_text = _finalize_decision_text(
                        text=decision.text,
                        freshness_mode=decision.freshness_mode,
                        source_result_ids=decision.source_result_ids,
                        temporal_context=temporal_context,
                        web_session=web_session,
                    )
                except TemporalContextError as error:
                    return self._degrade(
                        request=request,
                        effect_run_id=effect_run_id,
                        model_call_count=model_call_number,
                        tool_call_count=tool_call_count,
                        used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                        reason_code=error.code,
                        temporal_run=temporal_run,
                    )
                validation_error = _final_effect_validation_error(
                    request=request,
                    bundle=bundle,
                    text=temporal_text.text,
                    completed_at=self.clock(),
                )
                if validation_error is not None:
                    return self._degrade(
                        request=request,
                        effect_run_id=effect_run_id,
                        model_call_count=model_call_number,
                        tool_call_count=tool_call_count,
                        used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                        reason_code=validation_error,
                        temporal_run=temporal_run,
                    )
                final = FinalEffect(
                    kind=FinalEffectKind.REPLY,
                    reason_code=decision.reason_code,
                    persona=request.persona,
                    text=temporal_text.text,
                    catalog_version=(catalog.catalog_version if catalog is not None else None),
                    catalog_digest=(catalog.digest if catalog is not None else None),
                    sticker_eligible=False,
                    sticker_eligibility_reason="model_selected_text",
                    mood_signal=decision.mood_signal,
                    used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                    source_urls=temporal_text.source_urls,
                )
                self._complete_effect(
                    effect_run_id=effect_run_id,
                    effect=final,
                    model_call_count=model_call_number,
                    tool_call_count=tool_call_count,
                    temporal_run=temporal_run,
                    freshness_mode=decision.freshness_mode,
                    context=temporal_context,
                    latest_web_retrieved_at=temporal_text.latest_retrieved_at,
                )
                return final
            if decision.kind is WriterDecisionKind.REPLY_WITH_STICKER:
                assert decision.text is not None
                try:
                    temporal_text = _finalize_decision_text(
                        text=decision.text,
                        freshness_mode=decision.freshness_mode,
                        source_result_ids=decision.source_result_ids,
                        temporal_context=temporal_context,
                        web_session=web_session,
                    )
                except TemporalContextError as error:
                    return self._degrade(
                        request=request,
                        effect_run_id=effect_run_id,
                        model_call_count=model_call_number,
                        tool_call_count=tool_call_count,
                        used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                        reason_code=error.code,
                        temporal_run=temporal_run,
                    )
                completed_at = self.clock()
                validation_error = _final_effect_validation_error(
                    request=request,
                    bundle=bundle,
                    text=temporal_text.text,
                    completed_at=completed_at,
                )
                if validation_error is not None:
                    return self._degrade(
                        request=request,
                        effect_run_id=effect_run_id,
                        model_call_count=model_call_number,
                        tool_call_count=tool_call_count,
                        used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                        reason_code=validation_error,
                        temporal_run=temporal_run,
                    )
                try:
                    current_catalog = self._load_catalog(required=True)
                    assert current_catalog is not None
                    entry = validate_runtime_selection(
                        current_catalog,
                        semantic_id=str(decision.sticker_id),
                        persona_version=request.persona.persona_version,
                        persona_digest=request.persona.persona_digest,
                        expected_catalog_version=str(decision.catalog_version),
                        expected_catalog_digest=str(decision.catalog_digest),
                    )
                    selection_error = sticker_selection_error(
                        context=context,
                        catalog=current_catalog,
                        entry=entry,
                    )
                    if selection_error is not None:
                        raise ExpressionCatalogError(selection_error)
                except ExpressionCatalogError as error:
                    final = FinalEffect(
                        kind=FinalEffectKind.REPLY,
                        reason_code=f"sticker_{error.code}",
                        persona=request.persona,
                        text=temporal_text.text,
                        catalog_version=(catalog.catalog_version if catalog is not None else None),
                        catalog_digest=(catalog.digest if catalog is not None else None),
                        sticker_eligible=False,
                        sticker_eligibility_reason=f"sticker_{error.code}",
                        mood_signal=decision.mood_signal,
                        used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                        source_urls=temporal_text.source_urls,
                    )
                    self._complete_effect(
                        effect_run_id=effect_run_id,
                        effect=final,
                        model_call_count=model_call_number,
                        tool_call_count=tool_call_count,
                        temporal_run=temporal_run,
                        freshness_mode=decision.freshness_mode,
                        context=temporal_context,
                        latest_web_retrieved_at=temporal_text.latest_retrieved_at,
                    )
                    return final
                final = FinalEffect(
                    kind=FinalEffectKind.REPLY_WITH_STICKER,
                    reason_code=decision.reason_code,
                    persona=request.persona,
                    text=temporal_text.text,
                    sticker_id=entry.semantic_id,
                    catalog_version=current_catalog.catalog_version,
                    catalog_digest=current_catalog.digest,
                    sticker_eligible=True,
                    sticker_eligibility_reason="model_selected_nonsemantic_valid",
                    mood_signal=decision.mood_signal,
                    used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                    source_urls=temporal_text.source_urls,
                )
                self._complete_effect(
                    effect_run_id=effect_run_id,
                    effect=final,
                    model_call_count=model_call_number,
                    tool_call_count=tool_call_count,
                    temporal_run=temporal_run,
                    freshness_mode=decision.freshness_mode,
                    context=temporal_context,
                    latest_web_retrieved_at=temporal_text.latest_retrieved_at,
                )
                return final
            if decision.kind is WriterDecisionKind.STICKER:
                try:
                    current_catalog = self._load_catalog(required=True)
                    assert current_catalog is not None
                    entry = validate_runtime_selection(
                        current_catalog,
                        semantic_id=str(decision.sticker_id),
                        persona_version=request.persona.persona_version,
                        persona_digest=request.persona.persona_digest,
                        expected_catalog_version=str(decision.catalog_version),
                        expected_catalog_digest=str(decision.catalog_digest),
                    )
                    sticker_error = sticker_selection_error(
                        context=context,
                        catalog=current_catalog,
                        entry=entry,
                    )
                    if sticker_error is not None:
                        raise ExpressionCatalogError(sticker_error)
                    fallback_error = _final_effect_validation_error(
                        request=request,
                        bundle=bundle,
                        text=decision.fallback_text,
                        completed_at=self.clock(),
                    )
                    if fallback_error is not None:
                        raise ExpressionCatalogError(fallback_error)
                except ExpressionCatalogError as error:
                    return self._silence(
                        request=request,
                        effect_run_id=effect_run_id,
                        model_call_count=model_call_number,
                        tool_call_count=tool_call_count,
                        used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                        reason_code=f"sticker_{error.code}",
                        temporal_run=temporal_run,
                    )
                final = FinalEffect(
                    kind=FinalEffectKind.STICKER,
                    reason_code=decision.reason_code,
                    persona=request.persona,
                    sticker_id=entry.semantic_id,
                    catalog_version=current_catalog.catalog_version,
                    catalog_digest=current_catalog.digest,
                    fallback_text=decision.fallback_text,
                    sticker_eligible=True,
                    sticker_eligibility_reason="model_selected_nonsemantic_valid",
                    mood_signal=decision.mood_signal,
                    used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                )
                self._complete_effect(
                    effect_run_id=effect_run_id,
                    effect=final,
                    model_call_count=model_call_number,
                    tool_call_count=tool_call_count,
                    temporal_run=temporal_run,
                    freshness_mode=None,
                    context=temporal_context,
                )
                return final
            if decision.kind is WriterDecisionKind.SILENCE:
                validation_error = _final_effect_validation_error(
                    request=request,
                    bundle=bundle,
                    text=None,
                    completed_at=self.clock(),
                )
                if validation_error is not None:
                    return self._degrade(
                        request=request,
                        effect_run_id=effect_run_id,
                        model_call_count=model_call_number,
                        tool_call_count=tool_call_count,
                        used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                        reason_code=validation_error,
                        temporal_run=temporal_run,
                    )
                final = FinalEffect(
                    kind=FinalEffectKind.SILENCE,
                    reason_code=decision.reason_code,
                    persona=request.persona,
                    mood_signal=decision.mood_signal,
                    used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                )
                self._complete_effect(
                    effect_run_id=effect_run_id,
                    effect=final,
                    model_call_count=model_call_number,
                    tool_call_count=tool_call_count,
                    temporal_run=temporal_run,
                    freshness_mode=None,
                    context=temporal_context,
                )
                return final

            if not tools_enabled:
                return self._degrade(
                    request=request,
                    effect_run_id=effect_run_id,
                    model_call_count=model_call_number,
                    tool_call_count=tool_call_count,
                    used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                    reason_code="tool_requested_after_budget",
                    temporal_run=temporal_run,
                )
            extension_reason = decision.tool_extension_reason_code
            is_web_tool = decision.tool_name in WEB_TOOLS
            tool_result: ToolExecutionResult | WebToolExecutionResult
            if is_web_tool:
                if web_session is None:
                    return self._degrade(
                        request=request,
                        effect_run_id=effect_run_id,
                        model_call_count=model_call_number,
                        tool_call_count=tool_call_count,
                        used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                        reason_code="web_tool_unavailable",
                        temporal_run=temporal_run,
                    )
                tool_result = web_session.execute(
                    decision,
                    scope=self._web_tool_scope(
                        context=context,
                        effect_run_id=effect_run_id,
                    ),
                )
                web_tool_call_count += 1
                budget_ordinal = web_tool_call_count
                annotated_extension_reason = None
            else:
                scope = self._tool_scope(context=context, effect_run_id=effect_run_id)
                if context_tool_call_count >= self.budgets.ordinary_tool_calls and (
                    extension_reason is None or not last_context_result_novel
                ):
                    rejected = self.tools.record_rejected_attempt(
                        scope=scope,
                        capability=decision.tool_name or "invalid",
                        purpose_code=decision.tool_purpose_code or "invalid",
                        status="extension_not_justified",
                    )
                    tool_results.append(rejected)
                    context_tool_call_count += 1
                    tool_call_count += 1
                    result_character_count += rejected.result_char_count
                    self.runs.annotate_tool_call(
                        rejected.audit_id,
                        budget_ordinal=context_tool_call_count,
                        extension_reason_code=extension_reason,
                        result_novel=False,
                    )
                    history.append("writer_protocol_error:extension_not_justified")
                    last_context_result_novel = False
                    if result_character_count > self.budgets.maximum_result_characters:
                        return self._degrade(
                            request=request,
                            effect_run_id=effect_run_id,
                            model_call_count=model_call_number,
                            tool_call_count=tool_call_count,
                            used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                            reason_code="tool_result_budget_exhausted",
                            temporal_run=temporal_run,
                        )
                    continue
                tool_result = self.tools.execute(decision, scope=scope)
                context_tool_call_count += 1
                budget_ordinal = context_tool_call_count
                annotated_extension_reason = (
                    extension_reason
                    if context_tool_call_count > self.budgets.ordinary_tool_calls
                    else None
                )

            tool_results.append(tool_result)
            if isinstance(tool_result, WebToolExecutionResult):
                temporal_run.note_web(tool_result)
            tool_call_count += 1
            result_character_count += tool_result.result_char_count
            if result_character_count > self.budgets.maximum_result_characters:
                self.runs.annotate_tool_call(
                    tool_result.audit_id,
                    budget_ordinal=budget_ordinal,
                    extension_reason_code=annotated_extension_reason,
                    result_novel=False,
                )
                return self._degrade(
                    request=request,
                    effect_run_id=effect_run_id,
                    model_call_count=model_call_number,
                    tool_call_count=tool_call_count,
                    used_tool_call_ids=tuple(item.audit_id for item in tool_results),
                    reason_code="tool_result_budget_exhausted",
                    temporal_run=temporal_run,
                )
            fingerprint = _tool_result_fingerprint(tool_result)
            novel = (
                tool_result.status == "success"
                and tool_result.result_count > 0
                and fingerprint not in result_fingerprints
            )
            if novel:
                result_fingerprints.add(fingerprint)
            if not is_web_tool:
                last_context_result_novel = novel
            self.runs.annotate_tool_call(
                tool_result.audit_id,
                budget_ordinal=budget_ordinal,
                extension_reason_code=annotated_extension_reason,
                result_novel=novel,
            )

        return self._degrade(
            request=request,
            effect_run_id=effect_run_id,
            model_call_count=self.budgets.maximum_model_calls,
            tool_call_count=tool_call_count,
            used_tool_call_ids=tuple(item.audit_id for item in tool_results),
            reason_code="writer_budget_exhausted",
            temporal_run=temporal_run,
        )

    def _tool_scope(
        self,
        *,
        context: EffectContext,
        effect_run_id: int,
    ) -> ToolExecutionScope:
        return ToolExecutionScope(
            effect_run_id=effect_run_id,
            chat_id=(
                context.scheduled.chat_id
                if context.scheduled is not None
                else context.current_message.group_id  # type: ignore[union-attr]
            ),
            allowed_member_ids=frozenset(member.member_user_id for member in context.member_memory),
            persona=context.persona,
            recognition_policy_version=self.contexts.recognition_policy_version,
            deadline_at=context.deadline_at,
        )

    def _web_tool_scope(
        self,
        *,
        context: EffectContext,
        effect_run_id: int,
    ) -> WebToolScope:
        scheduled = context.scheduled
        current_message = context.current_message
        return WebToolScope(
            effect_run_id=effect_run_id,
            chat_id=(scheduled.chat_id if scheduled is not None else current_message.group_id),  # type: ignore[union-attr]
            deadline_at=context.deadline_at,
            scheduled=scheduled is not None,
            location_text=scheduled.location_text if scheduled is not None else None,
        )

    def _degrade(
        self,
        *,
        request: EffectRequest,
        effect_run_id: int,
        model_call_count: int,
        tool_call_count: int,
        used_tool_call_ids: tuple[int, ...],
        reason_code: str,
        temporal_run: _TemporalRunState | None = None,
    ) -> FinalEffect:
        if request.trigger_path is TriggerPath.DIRECT:
            final = FinalEffect(
                kind=FinalEffectKind.FAILURE_REPLY,
                reason_code=reason_code,
                persona=request.persona,
                text=self.failure_reply_text,
                used_tool_call_ids=used_tool_call_ids,
            )
        else:
            final = FinalEffect(
                kind=FinalEffectKind.SILENCE,
                reason_code=reason_code,
                persona=request.persona,
                used_tool_call_ids=used_tool_call_ids,
            )
        self._complete_effect(
            effect_run_id=effect_run_id,
            effect=final,
            model_call_count=model_call_count,
            tool_call_count=tool_call_count,
            temporal_run=temporal_run,
            freshness_mode=None,
            degradation_reason=reason_code,
        )
        return final

    def _silence(
        self,
        *,
        request: EffectRequest,
        effect_run_id: int,
        model_call_count: int,
        tool_call_count: int,
        used_tool_call_ids: tuple[int, ...],
        reason_code: str,
        temporal_run: _TemporalRunState | None = None,
    ) -> FinalEffect:
        final = FinalEffect(
            kind=FinalEffectKind.SILENCE,
            reason_code=reason_code,
            persona=request.persona,
            used_tool_call_ids=used_tool_call_ids,
        )
        self._complete_effect(
            effect_run_id=effect_run_id,
            effect=final,
            model_call_count=model_call_count,
            tool_call_count=tool_call_count,
            temporal_run=temporal_run,
            freshness_mode=None,
            degradation_reason=reason_code,
        )
        return final

    def _complete_effect(
        self,
        *,
        effect_run_id: int,
        effect: FinalEffect,
        model_call_count: int,
        tool_call_count: int,
        temporal_run: _TemporalRunState | None,
        freshness_mode: FreshnessMode | None,
        context: TemporalContext | None = None,
        latest_web_retrieved_at: datetime | None = None,
        degradation_reason: str | None = None,
    ) -> None:
        if temporal_run is not None:
            temporal_run.finalize(
                final=effect,
                freshness_mode=freshness_mode,
                context=context,
                latest_web_retrieved_at=latest_web_retrieved_at,
                degradation_reason=degradation_reason,
            )
        self.runs.complete_effect_run(
            effect_run_id=effect_run_id,
            effect=effect,
            model_call_count=model_call_count,
            tool_call_count=tool_call_count,
        )

    def _load_catalog(self, *, required: bool = False) -> ExpressionCatalog | None:
        if self.expression_catalog_provider is None:
            if required:
                raise ExpressionCatalogError("catalog_unavailable")
            return None
        try:
            catalog = self.expression_catalog_provider()
        except (ExpressionCatalogError, OSError):
            if required:
                raise ExpressionCatalogError("catalog_unavailable") from None
            return None
        if catalog.status != "enabled":
            if required:
                raise ExpressionCatalogError("catalog_not_enabled")
            return None
        return catalog


def _final_effect_validation_error(
    *,
    request: EffectRequest,
    bundle: CharacterBundle,
    text: str | None,
    completed_at: datetime,
) -> str | None:
    """Fail closed at the application-owned boundary before an effect can be sent."""

    if request.persona != bundle.snapshot:
        return "final_persona_snapshot_mismatch"
    if completed_at.tzinfo is None or request.deadline_at.tzinfo is None:
        return "final_invalid_deadline"
    if completed_at >= request.deadline_at:
        return "final_deadline_exceeded"
    if text is None:
        return None
    if not text.strip() or len(text) > 4_096:
        return "final_invalid_text"
    if _LEAKAGE_MARKER_PATTERN.search(text):
        return "final_internal_content"
    stripped = text.strip()
    if stripped[:1] in {"{", "["} and stripped[-1:] in {"}", "]"}:
        try:
            parsed = json.loads(stripped)
        except (TypeError, ValueError):
            pass
        else:
            if isinstance(parsed, (dict, list)):
                return "final_protocol_text"
    return None


def _tool_result_fingerprint(result: ToolExecutionResult | WebToolExecutionResult) -> str:
    return f"{result.capability}:{result.content_json}"


def _finalize_decision_text(
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
