from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from group_llm_agent.database import SQLiteDatabase
from group_llm_agent.events import MemoryCategory, PersonaSnapshot

_HALF_LIFE_DAYS = {
    MemoryCategory.FACT: 180.0,
    MemoryCategory.SHARED_EXPERIENCE: 180.0,
    MemoryCategory.OBSERVATION: 60.0,
    MemoryCategory.IMPRESSION: 30.0,
    MemoryCategory.PREFERENCE: 30.0,
}
_SUBJECTIVE_CATEGORIES = {MemoryCategory.IMPRESSION, MemoryCategory.PREFERENCE}
_DEFAULT_CONFIDENCE_THRESHOLD = 0.35


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class MemberMemoryItem:
    memory_id: str
    chat_id: str
    member_user_id: str
    category: MemoryCategory
    statement: str
    stored_confidence: float
    effective_confidence: float
    first_observed_at: datetime
    last_supported_at: datetime
    updated_at: datetime
    recognition_policy_version: str
    persona_version: str | None
    persona_digest: str | None
    revision: int
    source_message_ids: tuple[int, ...]


class MemoryRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def add(
        self,
        *,
        memory_id: str,
        chat_id: str,
        member_user_id: str,
        category: MemoryCategory,
        statement: str,
        confidence: float,
        source_message_ids: tuple[int, ...],
        recognition_policy_version: str,
        persona: PersonaSnapshot | None,
        observed_at: datetime | None = None,
        revision: int = 1,
    ) -> None:
        _validate_new_memory(
            memory_id=memory_id,
            statement=statement,
            confidence=confidence,
            source_message_ids=source_message_ids,
            category=category,
            persona=persona,
            revision=revision,
        )
        timestamp = observed_at or _utc_now()
        persona_version, persona_digest = _subjective_persona_fields(category, persona)
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO member_memory_items (
                    memory_id, chat_id, member_user_id, category, statement,
                    stored_confidence, first_observed_at, last_supported_at,
                    updated_at, recognition_policy_version, persona_id,
                    persona_version, persona_digest, revision
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    chat_id,
                    member_user_id,
                    category.value,
                    statement,
                    confidence,
                    timestamp.isoformat(),
                    timestamp.isoformat(),
                    timestamp.isoformat(),
                    recognition_policy_version,
                    persona.persona_id if persona_version is not None and persona else None,
                    persona_version,
                    persona_digest,
                    revision,
                ),
            )
            _add_sources(
                connection,
                memory_id=memory_id,
                chat_id=chat_id,
                source_message_ids=source_message_ids,
            )

    def list_active(
        self,
        *,
        chat_id: str,
        member_user_id: str,
        persona: PersonaSnapshot,
        recognition_policy_version: str,
        at: datetime | None = None,
        minimum_confidence: float = _DEFAULT_CONFIDENCE_THRESHOLD,
        limit: int = 8,
    ) -> tuple[MemberMemoryItem, ...]:
        if not 0 <= minimum_confidence <= 1:
            raise ValueError("minimum_confidence must be in [0, 1]")
        if not 1 <= limit <= 8:
            raise ValueError("limit must be in [1, 8]")
        current = at or _utc_now()
        connection = self.database.connect()
        try:
            policy = connection.execute(
                """
                SELECT memory_status, persona_id, persona_version, persona_digest
                FROM group_policies WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
            if (
                policy is None
                or policy["memory_status"] != "enabled"
                or policy["persona_id"] != persona.persona_id
                or policy["persona_version"] != persona.persona_version
                or policy["persona_digest"] != persona.persona_digest
            ):
                return ()
            rows = connection.execute(
                """
                SELECT memory_id, chat_id, member_user_id, category, statement,
                       stored_confidence, first_observed_at, last_supported_at,
                       updated_at, recognition_policy_version, persona_version,
                       persona_digest, revision
                FROM member_memory_items
                WHERE chat_id = ?
                  AND member_user_id = ?
                  AND status = 'active'
                  AND recognition_policy_version = ?
                ORDER BY updated_at DESC, memory_id
                LIMIT 100
                """,
                (chat_id, member_user_id, recognition_policy_version),
            ).fetchall()
            result: list[MemberMemoryItem] = []
            for row in rows:
                category = MemoryCategory(str(row["category"]))
                if category in _SUBJECTIVE_CATEGORIES and (
                    row["persona_version"] != persona.persona_version
                    or row["persona_digest"] != persona.persona_digest
                ):
                    continue
                last_supported_at = datetime.fromisoformat(str(row["last_supported_at"]))
                confidence = _effective_confidence(
                    stored=float(row["stored_confidence"]),
                    category=category,
                    last_supported_at=last_supported_at,
                    at=current,
                )
                if confidence < minimum_confidence:
                    continue
                source_rows = connection.execute(
                    """
                    SELECT source_message_id
                    FROM member_memory_sources
                    WHERE chat_id = ? AND memory_id = ?
                    ORDER BY source_message_id
                    """,
                    (chat_id, row["memory_id"]),
                ).fetchall()
                result.append(
                    MemberMemoryItem(
                        memory_id=str(row["memory_id"]),
                        chat_id=str(row["chat_id"]),
                        member_user_id=str(row["member_user_id"]),
                        category=category,
                        statement=str(row["statement"]),
                        stored_confidence=float(row["stored_confidence"]),
                        effective_confidence=confidence,
                        first_observed_at=datetime.fromisoformat(str(row["first_observed_at"])),
                        last_supported_at=last_supported_at,
                        updated_at=datetime.fromisoformat(str(row["updated_at"])),
                        recognition_policy_version=str(row["recognition_policy_version"]),
                        persona_version=(
                            str(row["persona_version"])
                            if row["persona_version"] is not None
                            else None
                        ),
                        persona_digest=(
                            str(row["persona_digest"])
                            if row["persona_digest"] is not None
                            else None
                        ),
                        revision=int(row["revision"]),
                        source_message_ids=tuple(
                            int(source["source_message_id"]) for source in source_rows
                        ),
                    )
                )
        finally:
            connection.close()
        result.sort(
            key=lambda item: (
                -item.effective_confidence,
                -item.updated_at.timestamp(),
                item.memory_id,
            )
        )
        return tuple(result[:limit])

    def adjust_confidence(
        self,
        *,
        memory_id: str,
        chat_id: str,
        member_user_id: str,
        expected_revision: int,
        new_confidence: float,
        source_message_ids: tuple[int, ...],
        supported_at: datetime | None = None,
    ) -> int:
        if not 0 <= new_confidence <= 1 or not source_message_ids:
            raise ValueError("Invalid confidence update")
        timestamp = supported_at or _utc_now()
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE member_memory_items
                SET stored_confidence = ?, last_supported_at = ?, updated_at = ?,
                    revision = revision + 1
                WHERE memory_id = ? AND chat_id = ? AND member_user_id = ?
                  AND status = 'active' AND revision = ?
                """,
                (
                    new_confidence,
                    timestamp.isoformat(),
                    timestamp.isoformat(),
                    memory_id,
                    chat_id,
                    member_user_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("Memory revision conflict")
            _add_sources(
                connection,
                memory_id=memory_id,
                chat_id=chat_id,
                source_message_ids=source_message_ids,
            )
            return expected_revision + 1

    def revise(
        self,
        *,
        old_memory_id: str,
        new_memory_id: str,
        chat_id: str,
        member_user_id: str,
        expected_revision: int,
        statement: str,
        confidence: float,
        source_message_ids: tuple[int, ...],
        recognition_policy_version: str,
        persona: PersonaSnapshot | None,
        observed_at: datetime | None = None,
    ) -> int:
        if not statement.strip() or len(statement) > 500 or not 0 <= confidence <= 1:
            raise ValueError("Invalid revised memory")
        timestamp = observed_at or _utc_now()
        with self.database.transaction() as connection:
            old = connection.execute(
                """
                SELECT category, first_observed_at, revision
                FROM member_memory_items
                WHERE memory_id = ? AND chat_id = ? AND member_user_id = ?
                  AND status = 'active' AND revision = ?
                """,
                (old_memory_id, chat_id, member_user_id, expected_revision),
            ).fetchone()
            if old is None:
                raise ValueError("Memory revision conflict")
            category = MemoryCategory(str(old["category"]))
            _validate_new_memory(
                memory_id=new_memory_id,
                statement=statement,
                confidence=confidence,
                source_message_ids=source_message_ids,
                category=category,
                persona=persona,
                revision=expected_revision + 1,
            )
            connection.execute(
                """
                UPDATE member_memory_items
                SET status = 'superseded', updated_at = ?, revision = revision + 1
                WHERE memory_id = ? AND chat_id = ? AND revision = ?
                """,
                (timestamp.isoformat(), old_memory_id, chat_id, expected_revision),
            )
            persona_version, persona_digest = _subjective_persona_fields(category, persona)
            connection.execute(
                """
                INSERT INTO member_memory_items (
                    memory_id, chat_id, member_user_id, category, statement,
                    stored_confidence, first_observed_at, last_supported_at,
                    updated_at, recognition_policy_version, persona_id,
                    persona_version, persona_digest, revision
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_memory_id,
                    chat_id,
                    member_user_id,
                    category.value,
                    statement,
                    confidence,
                    str(old["first_observed_at"]),
                    timestamp.isoformat(),
                    timestamp.isoformat(),
                    recognition_policy_version,
                    persona.persona_id if persona_version is not None and persona else None,
                    persona_version,
                    persona_digest,
                    expected_revision + 1,
                ),
            )
            _add_sources(
                connection,
                memory_id=new_memory_id,
                chat_id=chat_id,
                source_message_ids=source_message_ids,
            )
            return expected_revision + 1

    def revoke(
        self,
        *,
        memory_id: str,
        chat_id: str,
        member_user_id: str,
        expected_revision: int,
        at: datetime | None = None,
    ) -> int:
        timestamp = at or _utc_now()
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE member_memory_items
                SET status = 'revoked', updated_at = ?, revision = revision + 1
                WHERE memory_id = ? AND chat_id = ? AND member_user_id = ?
                  AND status = 'active' AND revision = ?
                """,
                (
                    timestamp.isoformat(),
                    memory_id,
                    chat_id,
                    member_user_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("Memory revision conflict")
            return expected_revision + 1

    def reset_member(
        self,
        *,
        chat_id: str,
        member_user_id: str,
        reset_by_user_id: str,
        at: datetime | None = None,
    ) -> int:
        timestamp = at or _utc_now()
        value = timestamp.isoformat()
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE member_memory_items
                SET status = 'revoked', updated_at = ?, revision = revision + 1
                WHERE chat_id = ? AND member_user_id = ? AND status = 'active'
                """,
                (value, chat_id, member_user_id),
            )
            connection.execute(
                """
                UPDATE group_messages
                SET text = NULL, text_purged_at = ?
                WHERE chat_id = ? AND sender_user_id = ? AND text IS NOT NULL
                """,
                (value, chat_id, member_user_id),
            )
            connection.execute(
                """
                UPDATE recognition_jobs
                SET status = 'superseded', lease_token = NULL,
                    leased_until = NULL, updated_at = ?
                WHERE chat_id = ? AND subject_user_id = ?
                  AND status IN ('pending', 'leased', 'retry')
                """,
                (value, chat_id, member_user_id),
            )
            connection.execute(
                """
                UPDATE group_policies
                SET reset_generation = reset_generation + 1, updated_at = ?
                WHERE chat_id = ?
                """,
                (value, chat_id),
            )
            row = connection.execute(
                "SELECT reset_generation FROM group_policies WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Unknown group policy")
            generation = int(row["reset_generation"])
            connection.execute(
                """
                INSERT INTO memory_reset_barriers (
                    chat_id, member_user_id, ignore_sources_before, generation,
                    reset_by_user_id, reset_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, member_user_id) DO UPDATE SET
                    ignore_sources_before = excluded.ignore_sources_before,
                    generation = excluded.generation,
                    reset_by_user_id = excluded.reset_by_user_id,
                    reset_at = excluded.reset_at
                """,
                (
                    chat_id,
                    member_user_id,
                    value,
                    generation,
                    reset_by_user_id,
                    value,
                ),
            )
            return generation

    def reset_group(
        self,
        *,
        chat_id: str,
        reset_by_user_id: str,
        at: datetime | None = None,
    ) -> int:
        timestamp = at or _utc_now()
        value = timestamp.isoformat()
        with self.database.transaction() as connection:
            members = [
                str(row["sender_user_id"])
                for row in connection.execute(
                    """
                    SELECT DISTINCT sender_user_id
                    FROM group_messages
                    WHERE chat_id = ? AND direction = 'inbound'
                    """,
                    (chat_id,),
                ).fetchall()
            ]
            connection.execute(
                """
                UPDATE member_memory_items
                SET status = 'revoked', updated_at = ?, revision = revision + 1
                WHERE chat_id = ? AND status = 'active'
                """,
                (value, chat_id),
            )
            connection.execute(
                """
                UPDATE group_messages
                SET text = NULL, text_purged_at = ?
                WHERE chat_id = ? AND text IS NOT NULL
                """,
                (value, chat_id),
            )
            connection.execute(
                """
                UPDATE recognition_jobs
                SET status = 'superseded', lease_token = NULL,
                    leased_until = NULL, updated_at = ?
                WHERE chat_id = ? AND status IN ('pending', 'leased', 'retry')
                """,
                (value, chat_id),
            )
            cursor = connection.execute(
                """
                UPDATE group_policies
                SET reset_generation = reset_generation + 1, updated_at = ?
                WHERE chat_id = ?
                """,
                (value, chat_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Unknown group policy")
            generation = int(
                connection.execute(
                    "SELECT reset_generation FROM group_policies WHERE chat_id = ?",
                    (chat_id,),
                ).fetchone()["reset_generation"]
            )
            connection.executemany(
                """
                INSERT INTO memory_reset_barriers (
                    chat_id, member_user_id, ignore_sources_before, generation,
                    reset_by_user_id, reset_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, member_user_id) DO UPDATE SET
                    ignore_sources_before = excluded.ignore_sources_before,
                    generation = excluded.generation,
                    reset_by_user_id = excluded.reset_by_user_id,
                    reset_at = excluded.reset_at
                """,
                [
                    (
                        chat_id,
                        member_user_id,
                        value,
                        generation,
                        reset_by_user_id,
                        value,
                    )
                    for member_user_id in members
                ],
            )
            return generation


def _validate_new_memory(
    *,
    memory_id: str,
    statement: str,
    confidence: float,
    source_message_ids: tuple[int, ...],
    category: MemoryCategory,
    persona: PersonaSnapshot | None,
    revision: int,
) -> None:
    if (
        not memory_id
        or len(memory_id) > 128
        or not statement.strip()
        or len(statement) > 500
        or not 0 <= confidence <= 1
        or not source_message_ids
        or len(source_message_ids) > 12
        or len(set(source_message_ids)) != len(source_message_ids)
        or revision < 1
    ):
        raise ValueError("Invalid memory item")
    if category in _SUBJECTIVE_CATEGORIES and persona is None:
        raise ValueError("Subjective memory requires a persona snapshot")


def _subjective_persona_fields(
    category: MemoryCategory,
    persona: PersonaSnapshot | None,
) -> tuple[str | None, str | None]:
    if category not in _SUBJECTIVE_CATEGORIES:
        return None, None
    assert persona is not None
    return persona.persona_version, persona.persona_digest


def _add_sources(
    connection: sqlite3.Connection,
    *,
    memory_id: str,
    chat_id: str,
    source_message_ids: tuple[int, ...],
) -> None:
    connection.executemany(
        """
        INSERT OR IGNORE INTO member_memory_sources (
            memory_id, chat_id, source_message_id
        )
        VALUES (?, ?, ?)
        """,
        [(memory_id, chat_id, source_id) for source_id in source_message_ids],
    )


def _effective_confidence(
    *,
    stored: float,
    category: MemoryCategory,
    last_supported_at: datetime,
    at: datetime,
) -> float:
    age_seconds = max(0.0, (at - last_supported_at).total_seconds())
    age_days = age_seconds / 86_400
    return stored * math.pow(0.5, age_days / _HALF_LIFE_DAYS[category])
