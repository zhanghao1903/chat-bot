from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from group_llm_agent.database import SQLiteDatabase
from group_llm_agent.events import MemoryCategory, PersonaSnapshot
from group_llm_agent.model import (
    RecognitionOperation,
    RecognitionProposal,
)

_SUBJECTIVE_CATEGORIES = {MemoryCategory.IMPRESSION, MemoryCategory.PREFERENCE}


@dataclass(frozen=True)
class RecognitionJob:
    id: int
    chat_id: str
    source_message_id: int
    subject_user_id: str
    attempt_count: int
    lease_token: str
    recognition_policy_version: str
    persona: PersonaSnapshot
    reset_generation: int


@dataclass(frozen=True)
class RecognitionSource:
    database_id: int
    telegram_message_id: str
    sender_user_id: str
    text: str
    sent_at: datetime


@dataclass(frozen=True)
class RecognitionMemory:
    memory_id: str
    category: MemoryCategory
    statement: str
    confidence: float
    revision: int


@dataclass(frozen=True)
class RecognitionEnvelope:
    job: RecognitionJob
    sources: tuple[RecognitionSource, ...]
    memories: tuple[RecognitionMemory, ...]


class RecognitionConflict(RuntimeError):
    pass


class RecognitionStale(RuntimeError):
    pass


class RecognitionJobRepository:
    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        maximum_attempts: int = 3,
    ) -> None:
        if not 1 <= maximum_attempts <= 3:
            raise ValueError("maximum_attempts must be in [1, 3]")
        self.database = database
        self.maximum_attempts = maximum_attempts

    def lease_one(
        self,
        *,
        persona: PersonaSnapshot,
        now: datetime,
        lease_duration: timedelta,
    ) -> RecognitionJob | None:
        timestamp = now.isoformat()
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE recognition_jobs
                SET status = 'retry', lease_token = NULL, leased_until = NULL,
                    next_attempt_at = ?, updated_at = ?
                WHERE status = 'leased' AND leased_until <= ?
                """,
                (timestamp, timestamp, timestamp),
            )
            connection.execute(
                """
                UPDATE recognition_jobs
                SET status = 'superseded', lease_token = NULL,
                    leased_until = NULL, updated_at = ?
                WHERE status IN ('pending', 'retry')
                  AND (
                    persona_id != ? OR persona_version != ? OR persona_digest != ?
                  )
                """,
                (
                    timestamp,
                    persona.persona_id,
                    persona.persona_version,
                    persona.persona_digest,
                ),
            )
            row = connection.execute(
                """
                SELECT j.id
                FROM recognition_jobs AS j
                JOIN group_policies AS p ON p.chat_id = j.chat_id
                WHERE j.status IN ('pending', 'retry')
                  AND (j.next_attempt_at IS NULL OR j.next_attempt_at <= ?)
                  AND j.persona_id = ?
                  AND j.persona_version = ?
                  AND j.persona_digest = ?
                  AND p.memory_status = 'enabled'
                  AND p.reset_generation = j.reset_generation
                  AND p.persona_id = j.persona_id
                  AND p.persona_version = j.persona_version
                  AND p.persona_digest = j.persona_digest
                ORDER BY j.id
                LIMIT 1
                """,
                (
                    timestamp,
                    persona.persona_id,
                    persona.persona_version,
                    persona.persona_digest,
                ),
            ).fetchone()
            if row is None:
                self._supersede_disabled_or_reset(connection, now=timestamp)
                return None
            job_id = int(row["id"])
            lease_token = uuid.uuid4().hex
            leased_until = (now + lease_duration).isoformat()
            cursor = connection.execute(
                """
                UPDATE recognition_jobs
                SET status = 'leased', attempt_count = attempt_count + 1,
                    lease_token = ?, leased_until = ?, next_attempt_at = NULL,
                    error_code = NULL, updated_at = ?
                WHERE id = ? AND status IN ('pending', 'retry')
                """,
                (lease_token, leased_until, timestamp, job_id),
            )
            if cursor.rowcount != 1:
                return None
            claimed = connection.execute(
                """
                SELECT id, chat_id, source_message_id, subject_user_id,
                       attempt_count, lease_token, recognition_policy_version,
                       persona_id, persona_version, persona_digest,
                       reset_generation
                FROM recognition_jobs WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
            assert claimed is not None
            return _job_from_row(claimed)

    def load_envelope(self, job: RecognitionJob) -> RecognitionEnvelope:
        connection = self.database.connect()
        try:
            self._assert_current(connection, job)
            barrier = connection.execute(
                """
                SELECT ignore_sources_before
                FROM memory_reset_barriers
                WHERE chat_id = ? AND member_user_id = ?
                """,
                (job.chat_id, job.subject_user_id),
            ).fetchone()
            after = str(barrier["ignore_sources_before"]) if barrier is not None else ""
            source_row = connection.execute(
                """
                SELECT id, telegram_message_id, sender_user_id, text, sent_at
                FROM group_messages
                WHERE id = ? AND chat_id = ? AND text IS NOT NULL AND sent_at >= ?
                """,
                (job.source_message_id, job.chat_id, after),
            ).fetchone()
            if source_row is None:
                raise RecognitionStale("source_unavailable")
            recent_rows = connection.execute(
                """
                SELECT id, telegram_message_id, sender_user_id, text, sent_at
                FROM group_messages
                WHERE chat_id = ? AND id != ? AND text IS NOT NULL AND sent_at >= ?
                ORDER BY sent_at DESC, id DESC
                LIMIT 19
                """,
                (job.chat_id, job.source_message_id, after),
            ).fetchall()
            sources = _bounded_sources(
                _source_from_row(source_row),
                tuple(_source_from_row(row) for row in recent_rows),
            )
            memory_rows = connection.execute(
                """
                SELECT memory_id, category, statement, stored_confidence, revision,
                       persona_version, persona_digest
                FROM member_memory_items
                WHERE chat_id = ? AND member_user_id = ? AND status = 'active'
                  AND recognition_policy_version = ?
                ORDER BY updated_at DESC, memory_id
                LIMIT 32
                """,
                (
                    job.chat_id,
                    job.subject_user_id,
                    job.recognition_policy_version,
                ),
            ).fetchall()
        finally:
            connection.close()
        memories: list[RecognitionMemory] = []
        for row in memory_rows:
            category = MemoryCategory(str(row["category"]))
            if category in _SUBJECTIVE_CATEGORIES and (
                row["persona_version"] != job.persona.persona_version
                or row["persona_digest"] != job.persona.persona_digest
            ):
                continue
            memories.append(
                RecognitionMemory(
                    memory_id=str(row["memory_id"]),
                    category=category,
                    statement=str(row["statement"]),
                    confidence=float(row["stored_confidence"]),
                    revision=int(row["revision"]),
                )
            )
        return RecognitionEnvelope(job=job, sources=sources, memories=tuple(memories))

    def apply(
        self,
        *,
        envelope: RecognitionEnvelope,
        proposals: Sequence[RecognitionProposal],
        now: datetime,
    ) -> int:
        job = envelope.job
        timestamp = now.isoformat()
        memory_by_id = {item.memory_id: item for item in envelope.memories}
        source_by_platform_id = {
            item.telegram_message_id: item.database_id for item in envelope.sources
        }
        with self.database.transaction() as connection:
            self._assert_current(connection, job)
            applied = 0
            for index, proposal in enumerate(proposals):
                source_ids = tuple(
                    source_by_platform_id[source_id] for source_id in proposal.source_message_ids
                )
                target = (
                    memory_by_id.get(proposal.supersedes_memory_id)
                    if proposal.supersedes_memory_id is not None
                    else None
                )
                memory_id = self._apply_one(
                    connection,
                    job=job,
                    proposal=proposal,
                    target=target,
                    source_ids=source_ids,
                    index=index,
                    now=timestamp,
                )
                connection.execute(
                    """
                    INSERT INTO recognition_change_audit (
                        chat_id, member_user_id, memory_id, operation,
                        source_message_ids, recognition_job_id, policy_version,
                        persona_version, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.chat_id,
                        job.subject_user_id,
                        memory_id,
                        proposal.operation.value,
                        json.dumps(source_ids, separators=(",", ":")),
                        job.id,
                        job.recognition_policy_version,
                        (
                            job.persona.persona_version
                            if proposal.category in _SUBJECTIVE_CATEGORIES
                            else None
                        ),
                        timestamp,
                    ),
                )
                applied += 1
            cursor = connection.execute(
                """
                UPDATE recognition_jobs
                SET status = 'completed', lease_token = NULL, leased_until = NULL,
                    next_attempt_at = NULL, error_code = NULL, updated_at = ?
                WHERE id = ? AND status = 'leased' AND lease_token = ?
                """,
                (timestamp, job.id, job.lease_token),
            )
            if cursor.rowcount != 1:
                raise RecognitionStale("lease_lost")
            return applied

    def retry(self, job: RecognitionJob, *, error_code: str, now: datetime) -> None:
        terminal = job.attempt_count >= self.maximum_attempts
        next_attempt_at = None
        if not terminal:
            delay_seconds = min(60, 2**job.attempt_count)
            next_attempt_at = (now + timedelta(seconds=delay_seconds)).isoformat()
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE recognition_jobs
                SET status = ?, lease_token = NULL, leased_until = NULL,
                    next_attempt_at = ?, error_code = ?, updated_at = ?
                WHERE id = ? AND status = 'leased' AND lease_token = ?
                """,
                (
                    "dead" if terminal else "retry",
                    next_attempt_at,
                    error_code[:64],
                    now.isoformat(),
                    job.id,
                    job.lease_token,
                ),
            )

    def supersede(self, job: RecognitionJob, *, reason: str, now: datetime) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE recognition_jobs
                SET status = 'superseded', lease_token = NULL, leased_until = NULL,
                    next_attempt_at = NULL, error_code = ?, updated_at = ?
                WHERE id = ? AND status = 'leased' AND lease_token = ?
                """,
                (reason[:64], now.isoformat(), job.id, job.lease_token),
            )

    def dead(self, job: RecognitionJob, *, reason: str, now: datetime) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE recognition_jobs
                SET status = 'dead', lease_token = NULL, leased_until = NULL,
                    next_attempt_at = NULL, error_code = ?, updated_at = ?
                WHERE id = ? AND status = 'leased' AND lease_token = ?
                """,
                (reason[:64], now.isoformat(), job.id, job.lease_token),
            )

    def _assert_current(
        self,
        connection: sqlite3.Connection,
        job: RecognitionJob,
    ) -> None:
        row = connection.execute(
            """
            SELECT j.status, j.lease_token, j.reset_generation,
                   p.memory_status, p.reset_generation AS policy_generation,
                   p.persona_id, p.persona_version, p.persona_digest
            FROM recognition_jobs AS j
            JOIN group_policies AS p ON p.chat_id = j.chat_id
            WHERE j.id = ?
            """,
            (job.id,),
        ).fetchone()
        if (
            row is None
            or row["status"] != "leased"
            or row["lease_token"] != job.lease_token
            or row["memory_status"] != "enabled"
            or int(row["reset_generation"]) != job.reset_generation
            or int(row["policy_generation"]) != job.reset_generation
            or row["persona_id"] != job.persona.persona_id
            or row["persona_version"] != job.persona.persona_version
            or row["persona_digest"] != job.persona.persona_digest
        ):
            raise RecognitionStale("job_or_policy_changed")

    def _apply_one(
        self,
        connection: sqlite3.Connection,
        *,
        job: RecognitionJob,
        proposal: RecognitionProposal,
        target: RecognitionMemory | None,
        source_ids: tuple[int, ...],
        index: int,
        now: str,
    ) -> str:
        if proposal.operation is RecognitionOperation.ADD:
            memory_id = _new_memory_id(job.id, index, proposal)
            persona_id, persona_version, persona_digest = _persona_columns(
                proposal.category,
                job.persona,
            )
            connection.execute(
                """
                INSERT INTO member_memory_items (
                    memory_id, chat_id, member_user_id, category, statement,
                    stored_confidence, first_observed_at, last_supported_at,
                    updated_at, recognition_policy_version, persona_id,
                    persona_version, persona_digest, revision
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    memory_id,
                    job.chat_id,
                    job.subject_user_id,
                    proposal.category.value,
                    proposal.statement,
                    proposal.confidence,
                    now,
                    now,
                    now,
                    job.recognition_policy_version,
                    persona_id,
                    persona_version,
                    persona_digest,
                ),
            )
            _insert_sources(connection, memory_id, job.chat_id, source_ids)
            return memory_id

        if target is None:
            raise RecognitionConflict("target_changed")
        if proposal.operation in {RecognitionOperation.STRENGTHEN, RecognitionOperation.WEAKEN}:
            cursor = connection.execute(
                """
                UPDATE member_memory_items
                SET stored_confidence = ?, last_supported_at = ?, updated_at = ?,
                    revision = revision + 1
                WHERE memory_id = ? AND chat_id = ? AND member_user_id = ?
                  AND status = 'active' AND revision = ?
                """,
                (
                    proposal.confidence,
                    now,
                    now,
                    target.memory_id,
                    job.chat_id,
                    job.subject_user_id,
                    target.revision,
                ),
            )
            if cursor.rowcount != 1:
                raise RecognitionConflict("revision_conflict")
            _insert_sources(connection, target.memory_id, job.chat_id, source_ids)
            return target.memory_id
        if proposal.operation is RecognitionOperation.REVOKE:
            cursor = connection.execute(
                """
                UPDATE member_memory_items
                SET status = 'revoked', updated_at = ?, revision = revision + 1
                WHERE memory_id = ? AND chat_id = ? AND member_user_id = ?
                  AND status = 'active' AND revision = ?
                """,
                (
                    now,
                    target.memory_id,
                    job.chat_id,
                    job.subject_user_id,
                    target.revision,
                ),
            )
            if cursor.rowcount != 1:
                raise RecognitionConflict("revision_conflict")
            return target.memory_id

        memory_id = _new_memory_id(job.id, index, proposal)
        cursor = connection.execute(
            """
            UPDATE member_memory_items
            SET status = 'superseded', updated_at = ?, revision = revision + 1
            WHERE memory_id = ? AND chat_id = ? AND member_user_id = ?
              AND status = 'active' AND revision = ?
            """,
            (
                now,
                target.memory_id,
                job.chat_id,
                job.subject_user_id,
                target.revision,
            ),
        )
        if cursor.rowcount != 1:
            raise RecognitionConflict("revision_conflict")
        persona_id, persona_version, persona_digest = _persona_columns(
            proposal.category,
            job.persona,
        )
        connection.execute(
            """
            INSERT INTO member_memory_items (
                memory_id, chat_id, member_user_id, category, statement,
                stored_confidence, first_observed_at, last_supported_at,
                updated_at, recognition_policy_version, persona_id,
                persona_version, persona_digest, revision
            )
            SELECT ?, chat_id, member_user_id, ?, ?, ?, first_observed_at,
                   ?, ?, ?, ?, ?, ?, revision
            FROM member_memory_items
            WHERE memory_id = ? AND chat_id = ?
            """,
            (
                memory_id,
                proposal.category.value,
                proposal.statement,
                proposal.confidence,
                now,
                now,
                job.recognition_policy_version,
                persona_id,
                persona_version,
                persona_digest,
                target.memory_id,
                job.chat_id,
            ),
        )
        _insert_sources(connection, memory_id, job.chat_id, source_ids)
        return memory_id

    @staticmethod
    def _supersede_disabled_or_reset(
        connection: sqlite3.Connection,
        *,
        now: str,
    ) -> None:
        connection.execute(
            """
            UPDATE recognition_jobs
            SET status = 'superseded', lease_token = NULL,
                leased_until = NULL, updated_at = ?
            WHERE status IN ('pending', 'retry')
              AND EXISTS (
                SELECT 1 FROM group_policies AS p
                WHERE p.chat_id = recognition_jobs.chat_id
                  AND (
                    p.memory_status != 'enabled'
                    OR p.reset_generation != recognition_jobs.reset_generation
                    OR p.persona_id != recognition_jobs.persona_id
                    OR p.persona_version != recognition_jobs.persona_version
                    OR p.persona_digest != recognition_jobs.persona_digest
                  )
              )
            """,
            (now,),
        )


def _job_from_row(row: sqlite3.Row) -> RecognitionJob:
    return RecognitionJob(
        id=int(row["id"]),
        chat_id=str(row["chat_id"]),
        source_message_id=int(row["source_message_id"]),
        subject_user_id=str(row["subject_user_id"]),
        attempt_count=int(row["attempt_count"]),
        lease_token=str(row["lease_token"]),
        recognition_policy_version=str(row["recognition_policy_version"]),
        persona=PersonaSnapshot(
            persona_id=str(row["persona_id"]),
            persona_version=str(row["persona_version"]),
            persona_digest=str(row["persona_digest"]),
        ),
        reset_generation=int(row["reset_generation"]),
    )


def _source_from_row(row: sqlite3.Row) -> RecognitionSource:
    return RecognitionSource(
        database_id=int(row["id"]),
        telegram_message_id=str(row["telegram_message_id"]),
        sender_user_id=str(row["sender_user_id"]),
        text=str(row["text"]),
        sent_at=datetime.fromisoformat(str(row["sent_at"])),
    )


def _bounded_sources(
    required: RecognitionSource,
    recent: tuple[RecognitionSource, ...],
) -> tuple[RecognitionSource, ...]:
    selected = [required]
    character_count = len(required.text)
    for source in recent:
        if character_count + len(source.text) > 24_000:
            continue
        selected.append(source)
        character_count += len(source.text)
    selected.sort(key=lambda source: (source.sent_at, source.database_id))
    return tuple(selected)


def _new_memory_id(
    job_id: int,
    index: int,
    proposal: RecognitionProposal,
) -> str:
    digest = hashlib.sha256(
        (
            f"{job_id}:{index}:{proposal.operation.value}:{proposal.category.value}:"
            f"{proposal.statement}"
        ).encode()
    ).hexdigest()[:20]
    return f"recognition-{job_id}-{index}-{digest}"


def _persona_columns(
    category: MemoryCategory,
    persona: PersonaSnapshot,
) -> tuple[str | None, str | None, str | None]:
    if category not in _SUBJECTIVE_CATEGORIES:
        return None, None, None
    return persona.persona_id, persona.persona_version, persona.persona_digest


def _insert_sources(
    connection: sqlite3.Connection,
    memory_id: str,
    chat_id: str,
    source_ids: tuple[int, ...],
) -> None:
    connection.executemany(
        """
        INSERT OR IGNORE INTO member_memory_sources (
            memory_id, chat_id, source_message_id
        )
        VALUES (?, ?, ?)
        """,
        [(memory_id, chat_id, source_id) for source_id in source_ids],
    )
