from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from group_llm_agent.database import SQLiteDatabase
from group_llm_agent.temporal import FreshnessMode, TemporalContext

TemporalAnswerStatus = Literal["completed", "degraded", "failed", "silence"]
SourceKind = Literal["inbound", "scheduled"]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class TemporalAnswerAudit:
    effect_run_id: int
    execution_attempt: int
    chat_id: str
    trigger_event_id: str
    source_kind: SourceKind
    final_context_id: str | None
    final_captured_at_utc: datetime | None
    answer_timezone: str | None
    utc_offset: str | None
    freshness_mode: FreshnessMode | None
    web_requested: bool
    web_audit_ids: tuple[int, ...]
    latest_web_retrieved_at: datetime | None
    status: TemporalAnswerStatus
    degradation_reason: str | None


class TemporalAuditRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def record_sample(
        self,
        *,
        effect_run_id: int,
        execution_attempt: int,
        model_call_ordinal: int,
        context: TemporalContext | None,
        error_code: str | None = None,
    ) -> int:
        if effect_run_id <= 0 or execution_attempt <= 0 or not 1 <= model_call_ordinal <= 12:
            raise ValueError("invalid temporal sample identity")
        if (context is None) == (error_code is None):
            raise ValueError("sample requires exactly one of context or error_code")
        if error_code is not None and not _safe_code(error_code):
            raise ValueError("invalid temporal sample error code")
        now = _utc_now()
        with self.database.transaction() as connection:
            self._validate_active_attempt(
                connection,
                effect_run_id=effect_run_id,
                execution_attempt=execution_attempt,
            )
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO temporal_context_samples (
                        effect_run_id, execution_attempt, model_call_ordinal, context_version,
                        context_id, captured_at_utc, answer_timezone, utc_offset,
                        timezone_selection, source_class, status, error_code, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        effect_run_id,
                        execution_attempt,
                        model_call_ordinal,
                        context.version if context is not None else None,
                        context.context_id if context is not None else None,
                        (context.captured_at_utc.isoformat() if context is not None else None),
                        context.answer_timezone if context is not None else None,
                        context.utc_offset if context is not None else None,
                        (context.timezone_selection.value if context is not None else None),
                        context.source_class if context is not None else None,
                        "valid" if context is not None else "failed",
                        error_code,
                        now,
                    ),
                )
            except sqlite3.IntegrityError:
                row = connection.execute(
                    """
                    SELECT id, context_id, status, error_code
                    FROM temporal_context_samples
                    WHERE effect_run_id = ? AND execution_attempt = ?
                      AND model_call_ordinal = ?
                    """,
                    (effect_run_id, execution_attempt, model_call_ordinal),
                ).fetchone()
                if (
                    row is None
                    or (str(row["context_id"]) if row["context_id"] is not None else None)
                    != (context.context_id if context is not None else None)
                    or str(row["status"]) != ("valid" if context is not None else "failed")
                    or (str(row["error_code"]) if row["error_code"] is not None else None)
                    != error_code
                ):
                    raise ValueError("conflicting temporal sample") from None
                return int(row["id"])
            row_id = cursor.lastrowid
            if row_id is None:
                raise sqlite3.DatabaseError("temporal sample insert produced no id")
            return int(row_id)

    def finalize(
        self,
        *,
        effect_run_id: int,
        execution_attempt: int,
        chat_id: str,
        trigger_event_id: str,
        source_kind: SourceKind,
        context: TemporalContext | None,
        freshness_mode: FreshnessMode | None,
        web_requested: bool,
        web_audit_ids: tuple[int, ...] = (),
        latest_web_retrieved_at: datetime | None = None,
        status: TemporalAnswerStatus,
        degradation_reason: str | None = None,
    ) -> None:
        if effect_run_id <= 0 or execution_attempt <= 0 or not chat_id or not trigger_event_id:
            raise ValueError("invalid temporal answer identity")
        if source_kind not in {"inbound", "scheduled"}:
            raise ValueError("invalid temporal answer source")
        if status not in {"completed", "degraded", "failed", "silence"}:
            raise ValueError("invalid temporal answer status")
        if degradation_reason is not None and not _safe_code(degradation_reason):
            raise ValueError("invalid degradation reason")
        if len(web_audit_ids) > 5 or any(value <= 0 for value in web_audit_ids):
            raise ValueError("invalid Web audit ids")
        if tuple(sorted(set(web_audit_ids))) != web_audit_ids:
            raise ValueError("Web audit ids must be sorted and unique")
        if latest_web_retrieved_at is not None and (
            latest_web_retrieved_at.tzinfo is None or latest_web_retrieved_at.utcoffset() is None
        ):
            raise ValueError("latest Web retrieval time must be timezone-aware")
        if freshness_mode is FreshnessMode.CURRENT_VERIFIED and not web_audit_ids:
            raise ValueError("verified current answer requires Web audit ids")
        now = _utc_now()
        web_json = json.dumps(web_audit_ids, separators=(",", ":"))
        values = (
            effect_run_id,
            execution_attempt,
            chat_id,
            trigger_event_id,
            source_kind,
            context.context_id if context is not None else None,
            context.captured_at_utc.isoformat() if context is not None else None,
            context.answer_timezone if context is not None else None,
            context.utc_offset if context is not None else None,
            freshness_mode.value if freshness_mode is not None else None,
            int(web_requested),
            web_json,
            (latest_web_retrieved_at.isoformat() if latest_web_retrieved_at is not None else None),
            status,
            degradation_reason,
            now,
            now,
        )
        with self.database.transaction() as connection:
            self._validate_effect_scope(
                connection,
                effect_run_id=effect_run_id,
                execution_attempt=execution_attempt,
                chat_id=chat_id,
                trigger_event_id=trigger_event_id,
                source_kind=source_kind,
            )
            self._validate_web_audits(
                connection,
                effect_run_id=effect_run_id,
                audit_ids=web_audit_ids,
            )
            cursor = connection.execute(
                """
                INSERT INTO temporal_answer_audit (
                    effect_run_id, execution_attempt, chat_id, trigger_event_id, source_kind,
                    final_context_id, final_captured_at_utc, answer_timezone,
                    utc_offset, freshness_mode, web_requested,
                    web_audit_ids_json, latest_web_retrieved_at, status,
                    degradation_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(effect_run_id) DO UPDATE SET
                    execution_attempt = excluded.execution_attempt,
                    chat_id = excluded.chat_id,
                    trigger_event_id = excluded.trigger_event_id,
                    source_kind = excluded.source_kind,
                    final_context_id = excluded.final_context_id,
                    final_captured_at_utc = excluded.final_captured_at_utc,
                    answer_timezone = excluded.answer_timezone,
                    utc_offset = excluded.utc_offset,
                    freshness_mode = excluded.freshness_mode,
                    web_requested = excluded.web_requested,
                    web_audit_ids_json = excluded.web_audit_ids_json,
                    latest_web_retrieved_at = excluded.latest_web_retrieved_at,
                    status = excluded.status,
                    degradation_reason = excluded.degradation_reason,
                    updated_at = excluded.updated_at
                WHERE temporal_answer_audit.execution_attempt < excluded.execution_attempt
                """,
                values,
            )
            if cursor.rowcount == 1:
                return
            row = connection.execute(
                "SELECT * FROM temporal_answer_audit WHERE effect_run_id = ?",
                (effect_run_id,),
            ).fetchone()
            if row is None or _stored_final_values(row) != values[1:15]:
                raise ValueError("conflicting terminal temporal audit")

    def get(self, *, effect_run_id: int) -> TemporalAnswerAudit | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM temporal_answer_audit WHERE effect_run_id = ?",
                (effect_run_id,),
            ).fetchone()
        if row is None:
            return None
        freshness_value = row["freshness_mode"]
        return TemporalAnswerAudit(
            effect_run_id=int(row["effect_run_id"]),
            execution_attempt=int(row["execution_attempt"]),
            chat_id=str(row["chat_id"]),
            trigger_event_id=str(row["trigger_event_id"]),
            source_kind=str(row["source_kind"]),  # type: ignore[arg-type]
            final_context_id=(
                str(row["final_context_id"]) if row["final_context_id"] is not None else None
            ),
            final_captured_at_utc=_optional_datetime(row["final_captured_at_utc"]),
            answer_timezone=(
                str(row["answer_timezone"]) if row["answer_timezone"] is not None else None
            ),
            utc_offset=str(row["utc_offset"]) if row["utc_offset"] is not None else None,
            freshness_mode=(
                FreshnessMode(str(freshness_value)) if freshness_value is not None else None
            ),
            web_requested=bool(row["web_requested"]),
            web_audit_ids=tuple(json.loads(str(row["web_audit_ids_json"]))),
            latest_web_retrieved_at=_optional_datetime(row["latest_web_retrieved_at"]),
            status=str(row["status"]),  # type: ignore[arg-type]
            degradation_reason=(
                str(row["degradation_reason"]) if row["degradation_reason"] is not None else None
            ),
        )

    @staticmethod
    def _validate_effect_scope(
        connection: sqlite3.Connection,
        *,
        effect_run_id: int,
        execution_attempt: int,
        chat_id: str,
        trigger_event_id: str,
        source_kind: SourceKind,
    ) -> None:
        row = connection.execute(
            """
            SELECT execution_attempt, chat_id, trigger_event_id, source_kind, status
            FROM effect_runs WHERE id = ?
            """,
            (effect_run_id,),
        ).fetchone()
        if row is None or (
            int(row["execution_attempt"]),
            str(row["chat_id"]),
            str(row["trigger_event_id"]),
            str(row["source_kind"]),
            str(row["status"]),
        ) != (execution_attempt, chat_id, trigger_event_id, source_kind, "processing"):
            raise ValueError("temporal audit effect scope mismatch")

    @staticmethod
    def _validate_active_attempt(
        connection: sqlite3.Connection,
        *,
        effect_run_id: int,
        execution_attempt: int,
    ) -> None:
        row = connection.execute(
            "SELECT execution_attempt, status FROM effect_runs WHERE id = ?",
            (effect_run_id,),
        ).fetchone()
        if row is None or (
            int(row["execution_attempt"]),
            str(row["status"]),
        ) != (execution_attempt, "processing"):
            raise ValueError("temporal sample attempt mismatch")

    @staticmethod
    def _validate_web_audits(
        connection: sqlite3.Connection,
        *,
        effect_run_id: int,
        audit_ids: tuple[int, ...],
    ) -> None:
        if not audit_ids:
            return
        placeholders = ",".join("?" for _ in audit_ids)
        rows = connection.execute(
            f"""
            SELECT id FROM tool_call_audit
            WHERE owner_kind = 'effect' AND owner_id = ?
              AND budget_kind = 'web' AND id IN ({placeholders})
            """,
            (effect_run_id, *audit_ids),
        ).fetchall()
        if {int(row["id"]) for row in rows} != set(audit_ids):
            raise ValueError("Web audit ownership mismatch")


def _stored_final_values(row: sqlite3.Row) -> tuple[object, ...]:
    return (
        int(row["execution_attempt"]),
        str(row["chat_id"]),
        str(row["trigger_event_id"]),
        str(row["source_kind"]),
        str(row["final_context_id"]) if row["final_context_id"] is not None else None,
        (str(row["final_captured_at_utc"]) if row["final_captured_at_utc"] is not None else None),
        str(row["answer_timezone"]) if row["answer_timezone"] is not None else None,
        str(row["utc_offset"]) if row["utc_offset"] is not None else None,
        str(row["freshness_mode"]) if row["freshness_mode"] is not None else None,
        int(row["web_requested"]),
        str(row["web_audit_ids_json"]),
        (
            str(row["latest_web_retrieved_at"])
            if row["latest_web_retrieved_at"] is not None
            else None
        ),
        str(row["status"]),
        (str(row["degradation_reason"]) if row["degradation_reason"] is not None else None),
    )


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("stored temporal audit datetime is naive")
    return parsed


def _safe_code(value: str) -> bool:
    return (
        bool(value)
        and len(value) <= 64
        and all(
            character.islower() or character.isdigit() or character == "_" for character in value
        )
    )
