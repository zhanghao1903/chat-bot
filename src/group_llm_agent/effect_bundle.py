from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from group_llm_agent.database import SQLiteDatabase
from group_llm_agent.events import FinalEffect, FinalEffectKind, TelegramMessage


class BundleStatus(StrEnum):
    PREPARED = "prepared"
    DELIVERING = "delivering"
    COMPLETED = "completed"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    INTERRUPTED = "interrupted"


class ComponentStatus(StrEnum):
    PLANNED = "planned"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class BundleComponent:
    id: int
    bundle_id: str
    ordinal: int
    component_kind: str
    requested_effect_kind: str
    asset_semantic_id: str | None
    text_character_count: int | None
    status: ComponentStatus
    platform_message_id: str | None
    error_code: str | None


@dataclass(frozen=True)
class EffectBundleRecord:
    bundle_id: str
    bot_user_id: str
    chat_id: str
    trigger_event_id: str
    trigger_message_id: str
    effect_run_id: int | None
    execution_attempt: int | None
    persona_version: str
    persona_digest: str
    catalog_version: str | None
    catalog_digest: str | None
    requested_form: str
    reason_code: str
    sticker_eligible: bool
    eligibility_reason: str
    status: BundleStatus
    error_code: str | None
    components: tuple[BundleComponent, ...]


class EffectBundleRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def prepare(
        self,
        *,
        event: TelegramMessage,
        final: FinalEffect,
        bot_user_id: str,
        now: datetime | None = None,
    ) -> EffectBundleRecord | None:
        if final.kind is FinalEffectKind.SILENCE:
            raise ValueError("silence has no visible effect bundle")
        current = _aware(now or datetime.now(UTC))
        requested_form, components = _component_plan(final)
        bundle_id = f"bundle-{uuid4().hex}"
        timestamp = current.isoformat()
        eligibility_reason = final.sticker_eligibility_reason or "not_eligible"
        with self.database.transaction() as connection:
            if not _active_attempt_owns_final(
                connection,
                event=event,
                final=final,
            ):
                return None
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO effect_bundles (
                    bundle_id, bot_user_id, chat_id, trigger_event_id,
                    trigger_message_id, effect_run_id, execution_attempt,
                    persona_version, persona_digest,
                    catalog_version, catalog_digest, requested_form, reason_code,
                    sticker_eligible, eligibility_reason, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'prepared', ?, ?)
                """,
                (
                    bundle_id,
                    bot_user_id,
                    event.group_id,
                    event.event_id,
                    event.message_id,
                    final.effect_run_id,
                    final.execution_attempt,
                    final.persona.persona_version,
                    final.persona.persona_digest,
                    final.catalog_version,
                    final.catalog_digest,
                    requested_form,
                    final.reason_code,
                    int(final.sticker_eligible),
                    eligibility_reason,
                    timestamp,
                    timestamp,
                ),
            )
            if cursor.rowcount != 1:
                return None
            for ordinal, kind, requested_kind, semantic_id, character_count in components:
                connection.execute(
                    """
                    INSERT INTO effect_bundle_components (
                        bundle_id, ordinal, component_kind, requested_effect_kind,
                        asset_semantic_id, text_character_count, status,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'planned', ?, ?)
                    """,
                    (
                        bundle_id,
                        ordinal,
                        kind,
                        requested_kind,
                        semantic_id,
                        character_count,
                        timestamp,
                        timestamp,
                    ),
                )
        return self.get(chat_id=event.group_id, trigger_event_id=event.event_id)

    def get(self, *, chat_id: str, trigger_event_id: str) -> EffectBundleRecord | None:
        connection = self.database.connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM effect_bundles
                WHERE chat_id = ? AND trigger_event_id = ?
                """,
                (chat_id, trigger_event_id),
            ).fetchone()
            if row is None:
                return None
            components = connection.execute(
                """
                SELECT * FROM effect_bundle_components
                WHERE bundle_id = ? ORDER BY ordinal
                """,
                (str(row["bundle_id"]),),
            ).fetchall()
        finally:
            connection.close()
        return _bundle_record(row, components)

    def claim_component(self, *, bundle_id: str, ordinal: int) -> int | None:
        now = datetime.now(UTC).isoformat()
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE effect_bundle_components
                SET status = 'sending', updated_at = ?
                WHERE bundle_id = ? AND ordinal = ? AND status = 'planned'
                """,
                (now, bundle_id, ordinal),
            )
            if cursor.rowcount != 1:
                return None
            connection.execute(
                """
                UPDATE effect_bundles
                SET status = 'delivering', updated_at = ?
                WHERE bundle_id = ? AND status IN ('prepared', 'delivering')
                """,
                (now, bundle_id),
            )
            row = connection.execute(
                """
                SELECT id FROM effect_bundle_components
                WHERE bundle_id = ? AND ordinal = ?
                """,
                (bundle_id, ordinal),
            ).fetchone()
            if row is None:
                raise sqlite3.DatabaseError("claimed component disappeared")
            return int(row["id"])

    def mark_sent(self, component_id: int, *, platform_message_id: str) -> bool:
        return self._terminal_component(
            component_id,
            status=ComponentStatus.SENT,
            platform_message_id=platform_message_id,
            error_code=None,
        )

    def mark_failed(self, component_id: int, *, error_code: str) -> bool:
        return self._terminal_component(
            component_id,
            status=ComponentStatus.FAILED,
            platform_message_id=None,
            error_code=error_code,
        )

    def mark_uncertain(self, component_id: int, *, error_code: str) -> bool:
        return self._terminal_component(
            component_id,
            status=ComponentStatus.UNCERTAIN,
            platform_message_id=None,
            error_code=error_code,
        )

    def skip_planned(self, *, bundle_id: str, error_code: str) -> int:
        now = datetime.now(UTC).isoformat()
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE effect_bundle_components
                SET status = 'skipped', error_code = ?, updated_at = ?
                WHERE bundle_id = ? AND status = 'planned'
                """,
                (error_code, now, bundle_id),
            )
            return cursor.rowcount

    def finalize(self, *, bundle_id: str, error_code: str | None = None) -> BundleStatus:
        with self.database.transaction() as connection:
            return self._finalize_in_transaction(
                connection,
                bundle_id=bundle_id,
                error_code=error_code,
            )

    def reconcile_incomplete(
        self,
        *,
        chat_id: str | None = None,
        trigger_event_id: str | None = None,
    ) -> int:
        if (chat_id is None) != (trigger_event_id is None):
            raise ValueError("chat_id and trigger_event_id must be provided together")
        with self.database.transaction() as connection:
            parameters: tuple[object, ...] = ()
            predicate = "status IN ('prepared', 'delivering')"
            if chat_id is not None and trigger_event_id is not None:
                predicate += " AND chat_id = ? AND trigger_event_id = ?"
                parameters = (chat_id, trigger_event_id)
            rows = connection.execute(
                f"SELECT bundle_id FROM effect_bundles WHERE {predicate}",
                parameters,
            ).fetchall()
            now = datetime.now(UTC).isoformat()
            for row in rows:
                bundle_id = str(row["bundle_id"])
                connection.execute(
                    """
                    UPDATE effect_bundle_components
                    SET status = 'uncertain', error_code = 'restart_after_send_claim',
                        updated_at = ?
                    WHERE bundle_id = ? AND status = 'sending'
                    """,
                    (now, bundle_id),
                )
                connection.execute(
                    """
                    UPDATE effect_bundle_components
                    SET status = 'skipped', error_code = 'restart_before_component_send',
                        updated_at = ?
                    WHERE bundle_id = ? AND status = 'planned'
                    """,
                    (now, bundle_id),
                )
                self._finalize_in_transaction(
                    connection,
                    bundle_id=bundle_id,
                    error_code="restart_reconciled",
                )
            return len(rows)

    def _terminal_component(
        self,
        component_id: int,
        *,
        status: ComponentStatus,
        platform_message_id: str | None,
        error_code: str | None,
    ) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE effect_bundle_components
                SET status = ?, platform_message_id = ?, error_code = ?, updated_at = ?
                WHERE id = ? AND status = 'sending'
                """,
                (
                    status.value,
                    platform_message_id,
                    error_code,
                    datetime.now(UTC).isoformat(),
                    component_id,
                ),
            )
            return cursor.rowcount == 1

    def _finalize_in_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        bundle_id: str,
        error_code: str | None,
    ) -> BundleStatus:
        rows = connection.execute(
            """
            SELECT status FROM effect_bundle_components
            WHERE bundle_id = ? ORDER BY ordinal
            """,
            (bundle_id,),
        ).fetchall()
        if not rows:
            raise sqlite3.DatabaseError("bundle has no components")
        statuses = tuple(ComponentStatus(str(row["status"])) for row in rows)
        if any(status in {ComponentStatus.PLANNED, ComponentStatus.SENDING} for status in statuses):
            derived = BundleStatus.DELIVERING
            completed_at = None
        elif ComponentStatus.UNCERTAIN in statuses:
            derived = BundleStatus.UNCERTAIN
            completed_at = datetime.now(UTC).isoformat()
        elif all(status is ComponentStatus.SENT for status in statuses):
            derived = BundleStatus.COMPLETED
            completed_at = datetime.now(UTC).isoformat()
        elif ComponentStatus.SENT in statuses:
            derived = BundleStatus.DEGRADED
            completed_at = datetime.now(UTC).isoformat()
        elif ComponentStatus.FAILED in statuses:
            derived = BundleStatus.FAILED
            completed_at = datetime.now(UTC).isoformat()
        else:
            derived = BundleStatus.INTERRUPTED
            completed_at = datetime.now(UTC).isoformat()
        connection.execute(
            """
            UPDATE effect_bundles
            SET status = ?, error_code = COALESCE(?, error_code),
                updated_at = ?, completed_at = ?
            WHERE bundle_id = ? AND status IN ('prepared', 'delivering')
            """,
            (
                derived.value,
                error_code,
                datetime.now(UTC).isoformat(),
                completed_at,
                bundle_id,
            ),
        )
        return derived


def _component_plan(
    final: FinalEffect,
) -> tuple[str, tuple[tuple[int, str, str, str | None, int | None], ...]]:
    if final.kind in {FinalEffectKind.REPLY, FinalEffectKind.FAILURE_REPLY}:
        if final.text is None:
            raise ValueError("text effect requires text")
        requested = "reply" if final.kind is FinalEffectKind.REPLY else "failure_reply"
        form = "text" if final.kind is FinalEffectKind.REPLY else "failure_text"
        return form, ((1, "text", requested, None, len(final.text)),)
    if final.kind is FinalEffectKind.STICKER:
        if final.sticker_id is None:
            raise ValueError("sticker effect requires semantic id")
        return "sticker", ((1, "sticker", "sticker", final.sticker_id, None),)
    if final.kind is FinalEffectKind.REPLY_WITH_STICKER:
        if final.text is None or final.sticker_id is None:
            raise ValueError("composite effect requires text and semantic id")
        return (
            "text_sticker",
            (
                (1, "text", "reply", None, len(final.text)),
                (2, "sticker", "sticker", final.sticker_id, None),
            ),
        )
    raise ValueError("unsupported visible effect kind")


def _bundle_record(
    row: sqlite3.Row,
    component_rows: list[sqlite3.Row],
) -> EffectBundleRecord:
    return EffectBundleRecord(
        bundle_id=str(row["bundle_id"]),
        bot_user_id=str(row["bot_user_id"]),
        chat_id=str(row["chat_id"]),
        trigger_event_id=str(row["trigger_event_id"]),
        trigger_message_id=str(row["trigger_message_id"]),
        effect_run_id=(int(row["effect_run_id"]) if row["effect_run_id"] is not None else None),
        execution_attempt=(
            int(row["execution_attempt"]) if row["execution_attempt"] is not None else None
        ),
        persona_version=str(row["persona_version"]),
        persona_digest=str(row["persona_digest"]),
        catalog_version=(
            str(row["catalog_version"]) if row["catalog_version"] is not None else None
        ),
        catalog_digest=(str(row["catalog_digest"]) if row["catalog_digest"] is not None else None),
        requested_form=str(row["requested_form"]),
        reason_code=str(row["reason_code"]),
        sticker_eligible=bool(row["sticker_eligible"]),
        eligibility_reason=str(row["eligibility_reason"]),
        status=BundleStatus(str(row["status"])),
        error_code=str(row["error_code"]) if row["error_code"] is not None else None,
        components=tuple(_component_record(item) for item in component_rows),
    )


def _component_record(row: sqlite3.Row) -> BundleComponent:
    return BundleComponent(
        id=int(row["id"]),
        bundle_id=str(row["bundle_id"]),
        ordinal=int(row["ordinal"]),
        component_kind=str(row["component_kind"]),
        requested_effect_kind=str(row["requested_effect_kind"]),
        asset_semantic_id=(
            str(row["asset_semantic_id"]) if row["asset_semantic_id"] is not None else None
        ),
        text_character_count=(
            int(row["text_character_count"]) if row["text_character_count"] is not None else None
        ),
        status=ComponentStatus(str(row["status"])),
        platform_message_id=(
            str(row["platform_message_id"]) if row["platform_message_id"] is not None else None
        ),
        error_code=str(row["error_code"]) if row["error_code"] is not None else None,
    )


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value


def _active_attempt_owns_final(
    connection: sqlite3.Connection,
    *,
    event: TelegramMessage,
    final: FinalEffect,
) -> bool:
    effect_run_id = final.effect_run_id
    execution_attempt = final.execution_attempt
    if (effect_run_id is None) != (execution_attempt is None):
        return False
    if effect_run_id is None or execution_attempt is None:
        existing = connection.execute(
            """
            SELECT 1 FROM effect_runs
            WHERE chat_id = ? AND trigger_event_id = ?
            """,
            (event.group_id, event.event_id),
        ).fetchone()
        return existing is None
    if effect_run_id <= 0 or execution_attempt <= 0:
        return False
    expected_status = (
        FinalEffectKind.REPLY.value
        if final.kind is FinalEffectKind.REPLY_WITH_STICKER
        else final.kind.value
    )
    row = connection.execute(
        """
        SELECT runs.execution_attempt, runs.status, runs.reason_code,
               audit.execution_attempt AS audit_attempt
        FROM effect_runs AS runs
        LEFT JOIN temporal_answer_audit AS audit ON audit.effect_run_id = runs.id
        WHERE runs.id = ? AND runs.chat_id = ? AND runs.trigger_event_id = ?
        """,
        (effect_run_id, event.group_id, event.event_id),
    ).fetchone()
    return row is not None and (
        int(row["execution_attempt"]),
        str(row["status"]),
        str(row["reason_code"]),
        int(row["audit_attempt"]) if row["audit_attempt"] is not None else None,
    ) == (execution_attempt, expected_status, final.reason_code, execution_attempt)
