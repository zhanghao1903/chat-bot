from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from group_llm_agent.database import SQLiteDatabase
from group_llm_agent.events import (
    ControlAuthorizationStatus,
    EffectRequest,
    EffectRunStatus,
    ExternalEffectKind,
    ExternalEffectStatus,
    FinalEffect,
    PersonaSnapshot,
    PersonaTriggerDecision,
    PlatformTriggerKind,
    TelegramTextMessage,
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
    trigger_message_id: str
    effect_kind: ExternalEffectKind
    status: ExternalEffectStatus
    persona_version: str | None
    persona_digest: str | None
    platform_message_id: str | None
    error_code: str | None


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
        decision: PersonaTriggerDecision,
        model_status: TriggerModelStatus,
        deadline_at: datetime,
    ) -> int:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO trigger_runs (
                    request_id, chat_id, trigger_event_id, trigger_message_id,
                    candidate_kind, persona_id, persona_version, persona_digest,
                    result_kind, reason_code, model_status, deadline_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            return _lastrowid(cursor)

    def start_effect_run(self, request: EffectRequest) -> int:
        now = _utc_now()
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO effect_runs (
                    request_id, chat_id, trigger_event_id, trigger_message_id,
                    trigger_path, persona_id, persona_version, persona_digest,
                    status, deadline_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'processing', ?, ?, ?)
                """,
                (
                    request.request_id,
                    request.message.group_id,
                    request.message.event_id,
                    request.message.message_id,
                    request.trigger_path.value,
                    request.persona.persona_id,
                    request.persona.persona_version,
                    request.persona.persona_digest,
                    request.deadline_at.isoformat(),
                    now,
                    now,
                ),
            )
            return _lastrowid(cursor)

    def complete_effect_run(
        self,
        *,
        effect_run_id: int,
        effect: FinalEffect,
        model_call_count: int,
        tool_call_count: int,
    ) -> None:
        status = EffectRunStatus(effect.kind.value)
        self._finish_effect_run(
            effect_run_id=effect_run_id,
            status=status,
            model_call_count=model_call_count,
            tool_call_count=tool_call_count,
            reason_code=effect.reason_code,
            error_code=None,
        )

    def fail_effect_run(
        self,
        *,
        effect_run_id: int,
        model_call_count: int,
        tool_call_count: int,
        error_code: str,
    ) -> None:
        self._finish_effect_run(
            effect_run_id=effect_run_id,
            status=EffectRunStatus.FAILED,
            model_call_count=model_call_count,
            tool_call_count=tool_call_count,
            reason_code=None,
            error_code=error_code,
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
    ) -> int:
        if min(latency_ms, result_count, result_char_count) < 0:
            raise ValueError("Audit counts must be non-negative")
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO tool_call_audit (
                    owner_kind, owner_id, chat_id, capability, purpose_code,
                    source_scope, status, latency_ms, result_count,
                    result_char_count, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    _utc_now(),
                ),
            )
            return _lastrowid(cursor)

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
    ) -> int | None:
        now = _utc_now()
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO external_effects (
                    chat_id, trigger_event_id, trigger_message_id, effect_kind,
                    status, persona_version, persona_digest, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'sending', ?, ?, ?, ?)
                """,
                (
                    message.group_id,
                    message.event_id,
                    message.message_id,
                    effect_kind.value,
                    persona.persona_version if persona is not None else None,
                    persona.persona_digest if persona is not None else None,
                    now,
                    now,
                ),
            )
            if cursor.rowcount == 0:
                return None
            return _lastrowid(cursor)

    def mark_external_sent(self, effect_id: int, *, platform_message_id: str) -> None:
        self._set_external_status(
            effect_id,
            status=ExternalEffectStatus.SENT,
            platform_message_id=platform_message_id,
            error_code=None,
        )

    def mark_external_failed(self, effect_id: int, *, error_code: str) -> None:
        self._set_external_status(
            effect_id,
            status=ExternalEffectStatus.FAILED,
            platform_message_id=None,
            error_code=error_code,
        )

    def mark_external_uncertain(self, effect_id: int, *, error_code: str) -> None:
        self._set_external_status(
            effect_id,
            status=ExternalEffectStatus.UNCERTAIN,
            platform_message_id=None,
            error_code=error_code,
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
                       effect_kind, status, persona_version, persona_digest,
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
            trigger_message_id=str(row["trigger_message_id"]),
            effect_kind=ExternalEffectKind(str(row["effect_kind"])),
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
    ) -> None:
        if min(model_call_count, tool_call_count) < 0:
            raise ValueError("Run counts must be non-negative")
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE effect_runs
                SET status = ?, model_call_count = ?, tool_call_count = ?,
                    reason_code = ?, error_code = ?, updated_at = ?
                WHERE id = ? AND status = 'processing'
                """,
                (
                    status.value,
                    model_call_count,
                    tool_call_count,
                    reason_code,
                    error_code,
                    _utc_now(),
                    effect_run_id,
                ),
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
    ) -> None:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE external_effects
                SET status = ?, platform_message_id = ?, error_code = ?, updated_at = ?
                WHERE id = ? AND status = 'sending'
                """,
                (status.value, platform_message_id, error_code, _utc_now(), effect_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Unknown or completed external effect id: {effect_id}")
