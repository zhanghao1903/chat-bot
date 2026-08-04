from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from group_llm_agent.database import SQLiteDatabase
from group_llm_agent.events import PersonaSnapshot

_AUTOMATION_TYPE = "weekday_food_recommendation"


class AutomationDeliveryRepository:
    """Own the atomic boundary between a prepared occurrence and its external claim."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def claim_prepared(
        self,
        *,
        occurrence_id: str,
        persona: PersonaSnapshot,
        now: datetime,
    ) -> int | None:
        if now.tzinfo is None:
            raise ValueError("datetime must be timezone-aware")
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT occurrence.chat_id, occurrence.config_version,
                       occurrence.grace_deadline, occurrence.persona_id,
                       occurrence.persona_version, occurrence.persona_digest,
                       config.enabled, config.paused,
                       config.config_version AS active_config_version,
                       policy.persona_id AS active_persona_id,
                       policy.persona_version AS active_persona_version,
                       policy.persona_digest AS active_persona_digest,
                       (SELECT COUNT(*) FROM automation_subscriptions AS subscription
                        WHERE subscription.chat_id = occurrence.chat_id
                          AND subscription.automation_type = occurrence.automation_type
                          AND subscription.active = 1) AS subscriber_count
                FROM automation_occurrences AS occurrence
                JOIN automation_group_configs AS config
                  ON config.chat_id = occurrence.chat_id
                 AND config.automation_type = occurrence.automation_type
                JOIN group_policies AS policy
                  ON policy.chat_id = occurrence.chat_id
                WHERE occurrence.occurrence_id = ?
                  AND occurrence.status = 'prepared'
                  AND occurrence.prepared_text IS NOT NULL
                  AND occurrence.prepared_primary_key IS NOT NULL
                """,
                (occurrence_id,),
            ).fetchone()
            if row is None:
                return None
            if (
                not bool(row["enabled"])
                or bool(row["paused"])
                or int(row["subscriber_count"]) < 1
                or int(row["config_version"]) != int(row["active_config_version"])
                or datetime.fromisoformat(str(row["grace_deadline"])) < now
                or str(row["persona_id"]) != persona.persona_id
                or str(row["persona_version"]) != persona.persona_version
                or str(row["persona_digest"]) != persona.persona_digest
                or str(row["active_persona_id"]) != persona.persona_id
                or str(row["active_persona_version"]) != persona.persona_version
                or str(row["active_persona_digest"]) != persona.persona_digest
            ):
                raise ValueError("scheduled_preclaim_state_changed")
            timestamp = now.isoformat()
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO external_effects (
                    chat_id, trigger_event_id, trigger_message_id, effect_kind,
                    requested_effect_kind, status, persona_version, persona_digest,
                    source_kind, scheduled_occurrence_id, created_at, updated_at
                ) VALUES (?, ?, NULL, 'reply', 'reply', 'sending', ?, ?,
                          'scheduled', ?, ?, ?)
                """,
                (
                    str(row["chat_id"]),
                    occurrence_id,
                    persona.persona_version,
                    persona.persona_digest,
                    occurrence_id,
                    timestamp,
                    timestamp,
                ),
            )
            if cursor.rowcount != 1:
                return None
            effect_id = cursor.lastrowid
            if effect_id is None:
                raise sqlite3.DatabaseError("scheduled external claim produced no row")
            updated = connection.execute(
                """
                UPDATE automation_occurrences
                SET status = 'sending', reason_code = 'external_effect_claimed',
                    updated_at = ?
                WHERE occurrence_id = ? AND status = 'prepared'
                """,
                (timestamp, occurrence_id),
            )
            if updated.rowcount != 1:
                raise sqlite3.DatabaseError("scheduled claim lost prepared state")
            return int(effect_id)

    def recover_sending_as_uncertain(self) -> int:
        """Reconcile the durable external effect before closing restart-time ambiguity."""

        now = datetime.now(UTC).isoformat()
        with self.database.transaction() as connection:
            rows = connection.execute(
                """
                SELECT occurrence.occurrence_id, effect.id AS effect_id,
                       effect.status AS effect_status
                FROM automation_occurrences AS occurrence
                LEFT JOIN external_effects AS effect
                  ON effect.scheduled_occurrence_id = occurrence.occurrence_id
                 AND effect.source_kind = 'scheduled'
                WHERE occurrence.automation_type = ? AND occurrence.status = 'sending'
                """,
                (_AUTOMATION_TYPE,),
            ).fetchall()
            if not rows:
                return 0
            reconciled = 0
            for row in rows:
                occurrence_id = str(row["occurrence_id"])
                effect_status = row["effect_status"]
                if effect_status == "sent":
                    status = "sent"
                    reason = "delivery_ack_reconciled"
                elif effect_status == "failed":
                    status = "definite_failure"
                    reason = "delivery_failure_reconciled"
                else:
                    status = "uncertain"
                    reason = "restart_after_claim"
                    if effect_status == "sending":
                        connection.execute(
                            """
                            UPDATE external_effects
                            SET status = 'uncertain', error_code = ?, updated_at = ?
                            WHERE id = ? AND status = 'sending'
                            """,
                            (reason, now, int(row["effect_id"])),
                        )
                cursor = connection.execute(
                    """
                    UPDATE automation_occurrences
                    SET status = ?, reason_code = ?, updated_at = ?
                    WHERE occurrence_id = ? AND status = 'sending'
                    """,
                    (status, reason, now, occurrence_id),
                )
                reconciled += cursor.rowcount
            return reconciled
