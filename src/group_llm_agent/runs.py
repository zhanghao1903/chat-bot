from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from group_llm_agent.database import SQLiteDatabase
from group_llm_agent.events import (
    ControlAuthorizationStatus,
    ConversationContinuityDecision,
    EffectRequest,
    EffectRunStatus,
    ExternalEffectKind,
    ExternalEffectStatus,
    FinalEffect,
    FinalEffectKind,
    MediaKind,
    PersonaSnapshot,
    PersonaTriggerDecision,
    PlatformTriggerKind,
    TelegramTextMessage,
    TriggerCategory,
    TriggerEvaluationDecisionKind,
    TriggerModelStatus,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _lastrowid(cursor: sqlite3.Cursor) -> int:
    value = cursor.lastrowid
    if value is None:
        raise sqlite3.DatabaseError("Insert did not produce a row id")
    return int(value)


@dataclass(frozen=True)
class ExternalEffectRecord:
    id: int
    chat_id: str
    trigger_event_id: str
    trigger_message_id: str | None
    effect_kind: ExternalEffectKind
    requested_effect_kind: ExternalEffectKind
    delivered_effect_kind: ExternalEffectKind | None
    asset_semantic_id: str | None
    status: ExternalEffectStatus
    persona_version: str | None
    persona_digest: str | None
    platform_message_id: str | None
    error_code: str | None


@dataclass(frozen=True)
class TriggerEvaluationRecord:
    trigger_category: TriggerCategory
    decision_kind: TriggerEvaluationDecisionKind
    reason_code: str
    model_status: TriggerModelStatus
    persona_name_hit: bool
    continuity_anchor_message_id: str | None


@dataclass(frozen=True)
class EffectRunAttempt:
    effect_run_id: int
    execution_attempt: int


class RunRepository:
    """Persists run metadata without message, prompt, or model-response content."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def record_trigger_run(
        self,
        *,
        request_id: str,
        message: TelegramTextMessage,
        candidate_kind: PlatformTriggerKind,
        decision: PersonaTriggerDecision | ConversationContinuityDecision,
        model_status: TriggerModelStatus,
        deadline_at: datetime,
    ) -> int:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO trigger_runs (
                    request_id, chat_id, trigger_event_id, trigger_message_id,
                    candidate_kind, persona_id, persona_version, persona_digest,
                    result_kind, reason_code, model_status, deadline_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    chat_id = excluded.chat_id,
                    trigger_event_id = excluded.trigger_event_id,
                    trigger_message_id = excluded.trigger_message_id,
                    candidate_kind = excluded.candidate_kind,
                    persona_id = excluded.persona_id,
                    persona_version = excluded.persona_version,
                    persona_digest = excluded.persona_digest,
                    result_kind = excluded.result_kind,
                    reason_code = excluded.reason_code,
                    model_status = excluded.model_status,
                    deadline_at = excluded.deadline_at,
                    created_at = excluded.created_at
                """,
                (
                    request_id,
                    message.group_id,
                    message.event_id,
                    message.message_id,
                    candidate_kind.value,
                    decision.persona.persona_id,
                    decision.persona.persona_version,
                    decision.persona.persona_digest,
                    decision.kind.value,
                    decision.reason_code,
                    model_status.value,
                    deadline_at.isoformat(),
                    _utc_now(),
                ),
            )
            row = connection.execute(
                "SELECT id FROM trigger_runs WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            assert row is not None
            return int(row["id"])

    def start_effect_attempt(self, request: EffectRequest) -> EffectRunAttempt:
        now = _utc_now()
        with self.database.transaction() as connection:
            claimed = connection.execute(
                """
                SELECT 1 FROM external_effects
                WHERE chat_id = ? AND trigger_event_id = ?
                """,
                (request.chat_id, request.trigger_event_id),
            ).fetchone()
            if claimed is not None:
                raise ValueError("External effect already claimed")
            connection.execute(
                """
                INSERT INTO effect_runs (
                    request_id, chat_id, trigger_event_id, trigger_message_id,
                    trigger_path, trigger_category, persona_id, persona_version,
                    persona_digest, source_kind, scheduled_occurrence_id,
                    status, execution_attempt, deadline_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'processing', 1, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    chat_id = excluded.chat_id,
                    trigger_event_id = excluded.trigger_event_id,
                    trigger_message_id = excluded.trigger_message_id,
                    trigger_path = excluded.trigger_path,
                    trigger_category = excluded.trigger_category,
                    source_kind = excluded.source_kind,
                    scheduled_occurrence_id = excluded.scheduled_occurrence_id,
                    persona_id = excluded.persona_id,
                    persona_version = excluded.persona_version,
                    persona_digest = excluded.persona_digest,
                    status = 'processing',
                    execution_attempt = effect_runs.execution_attempt + 1,
                    model_call_count = 0,
                    tool_call_count = 0,
                    reason_code = NULL,
                    error_code = NULL,
                    deadline_at = excluded.deadline_at,
                    updated_at = excluded.updated_at
                """,
                (
                    request.request_id,
                    request.chat_id,
                    request.trigger_event_id,
                    request.trigger_message_id,
                    request.trigger_path.value,
                    request.trigger_category.value,
                    request.persona.persona_id,
                    request.persona.persona_version,
                    request.persona.persona_digest,
                    request.source_kind.value,
                    request.scheduled.occurrence_id if request.scheduled is not None else None,
                    request.deadline_at.isoformat(),
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT id, execution_attempt FROM effect_runs WHERE request_id = ?",
                (request.request_id,),
            ).fetchone()
            assert row is not None
            return EffectRunAttempt(
                effect_run_id=int(row["id"]),
                execution_attempt=int(row["execution_attempt"]),
            )

    def start_effect_run(self, request: EffectRequest) -> int:
        """Compatibility wrapper for callers that do not own temporal attempt state."""

        return self.start_effect_attempt(request).effect_run_id

    def record_trigger_evaluation(
        self,
        *,
        request_id: str,
        message: TelegramTextMessage,
        trigger_category: TriggerCategory,
        persona_name_hit: bool,
        continuity_anchor_message_id: str | None,
        decision_kind: TriggerEvaluationDecisionKind,
        reason_code: str,
        model_status: TriggerModelStatus,
        persona: PersonaSnapshot,
    ) -> int:
        now = _utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO trigger_evaluations (
                    request_id, chat_id, trigger_event_id, trigger_message_id,
                    trigger_category, persona_name_hit,
                    continuity_anchor_message_id, decision_kind, reason_code,
                    model_status, persona_id, persona_version, persona_digest,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    chat_id = excluded.chat_id,
                    trigger_event_id = excluded.trigger_event_id,
                    trigger_message_id = excluded.trigger_message_id,
                    trigger_category = excluded.trigger_category,
                    persona_name_hit = excluded.persona_name_hit,
                    continuity_anchor_message_id = excluded.continuity_anchor_message_id,
                    decision_kind = excluded.decision_kind,
                    reason_code = excluded.reason_code,
                    model_status = excluded.model_status,
                    persona_id = excluded.persona_id,
                    persona_version = excluded.persona_version,
                    persona_digest = excluded.persona_digest,
                    updated_at = excluded.updated_at
                """,
                (
                    request_id,
                    message.group_id,
                    message.event_id,
                    message.message_id,
                    trigger_category.value,
                    int(persona_name_hit),
                    continuity_anchor_message_id,
                    decision_kind.value,
                    reason_code,
                    model_status.value,
                    persona.persona_id,
                    persona.persona_version,
                    persona.persona_digest,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT id FROM trigger_evaluations WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            assert row is not None
            return int(row["id"])

    def get_trigger_evaluation(
        self,
        *,
        chat_id: str,
        trigger_event_id: str,
    ) -> TriggerEvaluationRecord | None:
        connection = self.database.connect()
        try:
            row = connection.execute(
                """
                SELECT trigger_category, decision_kind, reason_code,
                       model_status, persona_name_hit,
                       continuity_anchor_message_id
                FROM trigger_evaluations
                WHERE chat_id = ? AND trigger_event_id = ?
                """,
                (chat_id, trigger_event_id),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return TriggerEvaluationRecord(
            trigger_category=TriggerCategory(str(row["trigger_category"])),
            decision_kind=TriggerEvaluationDecisionKind(str(row["decision_kind"])),
            reason_code=str(row["reason_code"]),
            model_status=TriggerModelStatus(str(row["model_status"])),
            persona_name_hit=bool(row["persona_name_hit"]),
            continuity_anchor_message_id=(
                str(row["continuity_anchor_message_id"])
                if row["continuity_anchor_message_id"] is not None
                else None
            ),
        )

    def has_terminal_trigger_evaluation(
        self,
        *,
        chat_id: str,
        trigger_event_id: str,
    ) -> bool:
        evaluation = self.get_trigger_evaluation(
            chat_id=chat_id,
            trigger_event_id=trigger_event_id,
        )
        return evaluation is not None and evaluation.decision_kind in {
            TriggerEvaluationDecisionKind.SILENCE,
            TriggerEvaluationDecisionKind.IGNORED,
            TriggerEvaluationDecisionKind.CONTROL,
        }

    def has_terminal_silence(
        self,
        *,
        chat_id: str,
        trigger_event_id: str,
    ) -> bool:
        """Return whether processing reached an intentional no-effect terminal state."""

        connection = self.database.connect()
        try:
            effect = connection.execute(
                """
                SELECT status FROM effect_runs
                WHERE chat_id = ? AND trigger_event_id = ?
                """,
                (chat_id, trigger_event_id),
            ).fetchone()
            if effect is not None:
                return str(effect["status"]) == EffectRunStatus.SILENCE.value
            trigger = connection.execute(
                """
                SELECT result_kind FROM trigger_runs
                WHERE chat_id = ? AND trigger_event_id = ?
                """,
                (chat_id, trigger_event_id),
            ).fetchone()
            return trigger is not None and str(trigger["result_kind"]) == "silence"
        finally:
            connection.close()

    def complete_effect_run(
        self,
        *,
        effect_run_id: int,
        effect: FinalEffect,
        model_call_count: int,
        tool_call_count: int,
        execution_attempt: int | None = None,
    ) -> None:
        status = (
            EffectRunStatus.REPLY
            if effect.kind is FinalEffectKind.REPLY_WITH_STICKER
            else EffectRunStatus(effect.kind.value)
        )
        self._finish_effect_run(
            effect_run_id=effect_run_id,
            status=status,
            model_call_count=model_call_count,
            tool_call_count=tool_call_count,
            reason_code=effect.reason_code,
            error_code=None,
            execution_attempt=execution_attempt,
        )

    def fail_effect_run(
        self,
        *,
        effect_run_id: int,
        model_call_count: int,
        tool_call_count: int,
        error_code: str,
        execution_attempt: int | None = None,
    ) -> None:
        self._finish_effect_run(
            effect_run_id=effect_run_id,
            status=EffectRunStatus.FAILED,
            model_call_count=model_call_count,
            tool_call_count=tool_call_count,
            reason_code=None,
            error_code=error_code,
            execution_attempt=execution_attempt,
        )

    def record_tool_call(
        self,
        *,
        owner_kind: Literal["effect", "recognition"],
        owner_id: int,
        chat_id: str,
        capability: str,
        purpose_code: str,
        source_scope: str,
        status: str,
        latency_ms: int,
        result_count: int,
        result_char_count: int,
        budget_ordinal: int = 0,
        extension_reason_code: str | None = None,
        result_novel: bool = False,
        budget_kind: Literal["context", "web"] = "context",
        provider_request_id: str | None = None,
        provider_credits: float | None = None,
        source_domains_json: str | None = None,
        retrieved_at: datetime | None = None,
        provider_error_code: str | None = None,
    ) -> int:
        if min(latency_ms, result_count, result_char_count, budget_ordinal) < 0:
            raise ValueError("Audit counts must be non-negative")
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO tool_call_audit (
                    owner_kind, owner_id, chat_id, capability, purpose_code,
                    source_scope, status, latency_ms, result_count,
                    result_char_count, budget_ordinal, extension_reason_code,
                    result_novel, budget_kind, provider_request_id,
                    provider_credits, source_domains_json, retrieved_at,
                    provider_error_code, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    owner_kind,
                    owner_id,
                    chat_id,
                    capability,
                    purpose_code,
                    source_scope,
                    status,
                    latency_ms,
                    result_count,
                    result_char_count,
                    budget_ordinal,
                    extension_reason_code,
                    int(result_novel),
                    budget_kind,
                    provider_request_id,
                    provider_credits,
                    source_domains_json,
                    retrieved_at.isoformat() if retrieved_at is not None else None,
                    provider_error_code,
                    _utc_now(),
                ),
            )
            return _lastrowid(cursor)

    def record_media_effect_audit(
        self,
        *,
        chat_id: str,
        trigger_event_id: str,
        media_kind: MediaKind,
        result_status: str,
        media_bytes: int | None = None,
        media_pixels: int | None = None,
        model_id: str | None = None,
        latency_ms: int = 0,
        error_code: str | None = None,
    ) -> int:
        if latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO media_effect_audit (
                    chat_id, trigger_event_id, media_kind, result_status,
                    byte_bucket, pixel_bucket, model_id, latency_ms,
                    error_code, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    trigger_event_id,
                    media_kind.value,
                    result_status,
                    _size_bucket(media_bytes),
                    _pixel_bucket(media_pixels),
                    model_id,
                    latency_ms,
                    error_code,
                    _utc_now(),
                ),
            )
            return _lastrowid(cursor)

    def annotate_tool_call(
        self,
        audit_id: int,
        *,
        budget_ordinal: int,
        extension_reason_code: str | None,
        result_novel: bool,
    ) -> None:
        if budget_ordinal <= 0:
            raise ValueError("budget_ordinal must be positive")
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE tool_call_audit
                SET budget_ordinal = ?, extension_reason_code = ?, result_novel = ?
                WHERE id = ?
                """,
                (budget_ordinal, extension_reason_code, int(result_novel), audit_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Unknown tool audit id")

    def record_mood_observation(
        self,
        *,
        bot_user_id: str,
        chat_id: str,
        member_user_id: str,
        trigger_event_id: str,
        persona: PersonaSnapshot,
        mood_code: str,
        catalog_version: str | None = None,
        catalog_digest: str | None = None,
        bot_scope_count: int,
    ) -> int | None:
        if not chat_id or not member_user_id:
            raise ValueError("mood provenance must be non-empty")
        if bot_scope_count < 1:
            raise ValueError("bot_scope_count must be positive")
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO persona_mood_observations (
                    bot_user_id, chat_id, member_user_id, trigger_event_id, persona_version,
                    persona_digest, catalog_version, catalog_digest,
                    mood_code, bot_scope_count, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bot_user_id,
                    chat_id,
                    member_user_id,
                    trigger_event_id,
                    persona.persona_version,
                    persona.persona_digest,
                    catalog_version,
                    catalog_digest,
                    mood_code,
                    bot_scope_count,
                    _utc_now(),
                ),
            )
            return _lastrowid(cursor) if cursor.rowcount else None

    def record_control_action(
        self,
        *,
        chat_id: str,
        command: str,
        requesting_user_id: str,
        target_user_id: str | None,
        authorization_status: ControlAuthorizationStatus,
        outcome: str,
        error_code: str | None = None,
    ) -> int:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO control_action_audit (
                    chat_id, command, requesting_user_id, target_user_id,
                    authorization_status, outcome, error_code, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    command,
                    requesting_user_id,
                    target_user_id,
                    authorization_status.value,
                    outcome,
                    error_code,
                    _utc_now(),
                ),
            )
            return _lastrowid(cursor)

    def claim_external_effect(
        self,
        *,
        message: TelegramTextMessage,
        effect_kind: ExternalEffectKind,
        persona: PersonaSnapshot | None,
        asset_semantic_id: str | None = None,
    ) -> int | None:
        now = _utc_now()
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO external_effects (
                    chat_id, trigger_event_id, trigger_message_id, effect_kind,
                    requested_effect_kind, asset_semantic_id, status,
                    persona_version, persona_digest, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'sending', ?, ?, ?, ?)
                """,
                (
                    message.group_id,
                    message.event_id,
                    message.message_id,
                    effect_kind.value,
                    effect_kind.value,
                    asset_semantic_id,
                    persona.persona_version if persona is not None else None,
                    persona.persona_digest if persona is not None else None,
                    now,
                    now,
                ),
            )
            if cursor.rowcount == 0:
                return None
            return _lastrowid(cursor)

    def mark_external_sent(
        self,
        effect_id: int,
        *,
        platform_message_id: str,
        delivered_effect_kind: ExternalEffectKind | None = None,
    ) -> None:
        self._set_external_status(
            effect_id,
            status=ExternalEffectStatus.SENT,
            platform_message_id=platform_message_id,
            error_code=None,
            delivered_effect_kind=delivered_effect_kind,
        )

    def mark_external_failed(self, effect_id: int, *, error_code: str) -> None:
        self._set_external_status(
            effect_id,
            status=ExternalEffectStatus.FAILED,
            platform_message_id=None,
            error_code=error_code,
            delivered_effect_kind=None,
        )

    def mark_external_uncertain(self, effect_id: int, *, error_code: str) -> None:
        self._set_external_status(
            effect_id,
            status=ExternalEffectStatus.UNCERTAIN,
            platform_message_id=None,
            error_code=error_code,
            delivered_effect_kind=None,
        )

    def get_external_effect(
        self,
        *,
        chat_id: str,
        trigger_event_id: str,
    ) -> ExternalEffectRecord | None:
        connection = self.database.connect()
        try:
            row = connection.execute(
                """
                SELECT id, chat_id, trigger_event_id, trigger_message_id,
                       effect_kind, requested_effect_kind, delivered_effect_kind,
                       asset_semantic_id, status, persona_version, persona_digest,
                       platform_message_id, error_code
                FROM external_effects
                WHERE chat_id = ? AND trigger_event_id = ?
                """,
                (chat_id, trigger_event_id),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return ExternalEffectRecord(
            id=int(row["id"]),
            chat_id=str(row["chat_id"]),
            trigger_event_id=str(row["trigger_event_id"]),
            trigger_message_id=(
                str(row["trigger_message_id"]) if row["trigger_message_id"] is not None else None
            ),
            effect_kind=ExternalEffectKind(str(row["effect_kind"])),
            requested_effect_kind=ExternalEffectKind(str(row["requested_effect_kind"])),
            delivered_effect_kind=(
                ExternalEffectKind(str(row["delivered_effect_kind"]))
                if row["delivered_effect_kind"] is not None
                else None
            ),
            asset_semantic_id=(
                str(row["asset_semantic_id"]) if row["asset_semantic_id"] is not None else None
            ),
            status=ExternalEffectStatus(str(row["status"])),
            persona_version=(
                str(row["persona_version"]) if row["persona_version"] is not None else None
            ),
            persona_digest=(
                str(row["persona_digest"]) if row["persona_digest"] is not None else None
            ),
            platform_message_id=(
                str(row["platform_message_id"]) if row["platform_message_id"] is not None else None
            ),
            error_code=str(row["error_code"]) if row["error_code"] is not None else None,
        )

    def _finish_effect_run(
        self,
        *,
        effect_run_id: int,
        status: EffectRunStatus,
        model_call_count: int,
        tool_call_count: int,
        reason_code: str | None,
        error_code: str | None,
        execution_attempt: int | None = None,
    ) -> None:
        if min(model_call_count, tool_call_count) < 0:
            raise ValueError("Run counts must be non-negative")
        with self.database.transaction() as connection:
            attempt_clause = " AND execution_attempt = ?" if execution_attempt is not None else ""
            parameters: tuple[object, ...] = (
                status.value,
                model_call_count,
                tool_call_count,
                reason_code,
                error_code,
                _utc_now(),
                effect_run_id,
            )
            if execution_attempt is not None:
                parameters += (execution_attempt,)
            cursor = connection.execute(
                f"""
                UPDATE effect_runs
                SET status = ?, model_call_count = ?, tool_call_count = ?,
                    reason_code = ?, error_code = ?, updated_at = ?
                WHERE id = ? AND status = 'processing'{attempt_clause}
                """,
                parameters,
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Unknown or completed effect run id: {effect_run_id}")

    def _set_external_status(
        self,
        effect_id: int,
        *,
        status: ExternalEffectStatus,
        platform_message_id: str | None,
        error_code: str | None,
        delivered_effect_kind: ExternalEffectKind | None,
    ) -> None:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE external_effects
                SET status = ?, platform_message_id = ?, error_code = ?,
                    delivered_effect_kind = CASE
                        WHEN ? IS NOT NULL THEN ?
                        WHEN ? = 'sent' THEN requested_effect_kind
                        ELSE delivered_effect_kind
                    END,
                    updated_at = ?
                WHERE id = ? AND status = 'sending'
                """,
                (
                    status.value,
                    platform_message_id,
                    error_code,
                    delivered_effect_kind.value if delivered_effect_kind is not None else None,
                    delivered_effect_kind.value if delivered_effect_kind is not None else None,
                    status.value,
                    _utc_now(),
                    effect_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Unknown or completed external effect id: {effect_id}")


def _size_bucket(value: int | None) -> str | None:
    if value is None:
        return None
    if value < 256 * 1024:
        return "lt_256k"
    if value < 1024 * 1024:
        return "lt_1m"
    if value < 4 * 1024 * 1024:
        return "lt_4m"
    return "gte_4m"


def _pixel_bucket(value: int | None) -> str | None:
    if value is None:
        return None
    if value < 1_000_000:
        return "lt_1mp"
    if value < 4_000_000:
        return "lt_4mp"
    if value < 12_000_000:
        return "lt_12mp"
    return "gte_12mp"
