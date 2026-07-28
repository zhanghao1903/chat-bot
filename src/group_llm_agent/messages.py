from __future__ import annotations

import hashlib
import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from group_llm_agent.database import SQLiteDatabase
from group_llm_agent.events import PersonaSnapshot, TelegramTextMessage

_RECENT_LIMIT = 20
_SEEN_EVENT_LIMIT = 256


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _lastrowid(cursor: sqlite3.Cursor) -> int:
    value = cursor.lastrowid
    if value is None:
        raise sqlite3.DatabaseError("Insert did not produce a row id")
    return int(value)


@dataclass(frozen=True)
class GroupPolicy:
    chat_id: str
    memory_status: str
    raw_retention_days: int
    reset_generation: int
    persona_id: str | None
    persona_version: str | None
    persona_digest: str | None

    @property
    def memory_enabled(self) -> bool:
        return self.memory_status == "enabled"


@dataclass(frozen=True)
class StoredGroupMessage:
    id: int | None
    chat_id: str
    telegram_message_id: str
    event_id: str
    sender_user_id: str
    sender_display_name: str
    direction: str
    text: str
    sent_at: datetime
    replied_to_message_id: str | None
    replied_to_user_id: str | None


@dataclass(frozen=True)
class MessageIngestResult:
    message_id: int | None
    recognition_job_id: int | None
    duplicate: bool
    persisted: bool


class GroupPolicyRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def ensure(self, *, chat_id: str, raw_retention_days: int = 7) -> GroupPolicy:
        if not 1 <= raw_retention_days <= 7:
            raise ValueError("raw_retention_days must be in [1, 7]")
        now = _utc_now().isoformat()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO group_policies (
                    chat_id, raw_retention_days, created_at, updated_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, raw_retention_days, now, now),
            )
        policy = self.get(chat_id=chat_id)
        assert policy is not None
        return policy

    def get(self, *, chat_id: str) -> GroupPolicy | None:
        connection = self.database.connect()
        try:
            row = connection.execute(
                """
                SELECT chat_id, memory_status, raw_retention_days, reset_generation,
                       persona_id, persona_version, persona_digest
                FROM group_policies
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return GroupPolicy(
            chat_id=str(row["chat_id"]),
            memory_status=str(row["memory_status"]),
            raw_retention_days=int(row["raw_retention_days"]),
            reset_generation=int(row["reset_generation"]),
            persona_id=str(row["persona_id"]) if row["persona_id"] is not None else None,
            persona_version=(
                str(row["persona_version"]) if row["persona_version"] is not None else None
            ),
            persona_digest=(
                str(row["persona_digest"]) if row["persona_digest"] is not None else None
            ),
        )

    def set_memory_status(
        self,
        *,
        chat_id: str,
        status: str,
        persona: PersonaSnapshot,
        notice_message_id: str | None = None,
        enabled_by_user_id: str | None = None,
    ) -> None:
        if status not in {"disabled", "pending", "enabled"}:
            raise ValueError("Unknown memory status")
        self.ensure(chat_id=chat_id)
        now = _utc_now().isoformat()
        enabled_at = now if status == "enabled" else None
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE group_policies
                SET memory_status = ?, notice_message_id = ?,
                    enabled_by_user_id = ?, enabled_at = ?,
                    persona_id = ?, persona_version = ?, persona_digest = ?,
                    updated_at = ?
                WHERE chat_id = ?
                """,
                (
                    status,
                    notice_message_id,
                    enabled_by_user_id,
                    enabled_at,
                    persona.persona_id,
                    persona.persona_version,
                    persona.persona_digest,
                    now,
                    chat_id,
                ),
            )


class MessageRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database
        self.policies = GroupPolicyRepository(database)
        self._transient: dict[str, deque[StoredGroupMessage]] = defaultdict(
            lambda: deque(maxlen=_RECENT_LIMIT)
        )
        self._seen_events: dict[str, deque[str]] = defaultdict(
            lambda: deque(maxlen=_SEEN_EVENT_LIMIT)
        )
        self._seen_event_sets: dict[str, set[str]] = defaultdict(set)

    def ingest_inbound(
        self,
        message: TelegramTextMessage,
        *,
        persona: PersonaSnapshot,
        recognition_policy_version: str,
    ) -> MessageIngestResult:
        policy = self.policies.ensure(chat_id=message.group_id)
        if not policy.memory_enabled:
            duplicate = not self._remember_transient_event(message.group_id, message.event_id)
            if not duplicate:
                self._transient[message.group_id].append(_from_telegram(message))
            return MessageIngestResult(
                message_id=None,
                recognition_job_id=None,
                duplicate=duplicate,
                persisted=False,
            )

        now = _utc_now()
        expires_at = now + timedelta(days=policy.raw_retention_days)
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO group_messages (
                    chat_id, telegram_message_id, event_id, sender_user_id,
                    sender_display_name, direction, text, text_sha256, sent_at,
                    ingested_at, text_expires_at, replied_to_message_id,
                    replied_to_user_id
                )
                VALUES (?, ?, ?, ?, ?, 'inbound', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.group_id,
                    message.message_id,
                    message.event_id,
                    message.sender_id,
                    message.sender_display_name,
                    message.text,
                    _text_digest(message.text),
                    message.timestamp.isoformat(),
                    now.isoformat(),
                    expires_at.isoformat(),
                    message.replied_to_message_id,
                    message.replied_to_user_id,
                ),
            )
            if cursor.rowcount == 0:
                row = connection.execute(
                    """
                    SELECT id FROM group_messages
                    WHERE chat_id = ? AND event_id = ?
                    """,
                    (message.group_id, message.event_id),
                ).fetchone()
                return MessageIngestResult(
                    message_id=int(row["id"]) if row is not None else None,
                    recognition_job_id=None,
                    duplicate=True,
                    persisted=True,
                )

            message_id = _lastrowid(cursor)
            job_cursor = connection.execute(
                """
                INSERT INTO recognition_jobs (
                    chat_id, source_message_id, subject_user_id,
                    recognition_policy_version, persona_id, persona_version,
                    persona_digest, reset_generation, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.group_id,
                    message_id,
                    message.sender_id,
                    recognition_policy_version,
                    persona.persona_id,
                    persona.persona_version,
                    persona.persona_digest,
                    policy.reset_generation,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            return MessageIngestResult(
                message_id=message_id,
                recognition_job_id=_lastrowid(job_cursor),
                duplicate=False,
                persisted=True,
            )

    def record_outbound(
        self,
        *,
        chat_id: str,
        telegram_message_id: str,
        event_id: str,
        bot_user_id: str,
        bot_display_name: str,
        text: str,
        sent_at: datetime,
        replied_to_message_id: str | None,
    ) -> int | None:
        policy = self.policies.ensure(chat_id=chat_id)
        if not policy.memory_enabled:
            if self._remember_transient_event(chat_id, event_id):
                self._transient[chat_id].append(
                    StoredGroupMessage(
                        id=None,
                        chat_id=chat_id,
                        telegram_message_id=telegram_message_id,
                        event_id=event_id,
                        sender_user_id=bot_user_id,
                        sender_display_name=bot_display_name,
                        direction="outbound",
                        text=text,
                        sent_at=sent_at,
                        replied_to_message_id=replied_to_message_id,
                        replied_to_user_id=None,
                    )
                )
            return None

        now = _utc_now()
        expires_at = now + timedelta(days=policy.raw_retention_days)
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO group_messages (
                    chat_id, telegram_message_id, event_id, sender_user_id,
                    sender_display_name, direction, text, text_sha256, sent_at,
                    ingested_at, text_expires_at, replied_to_message_id
                )
                VALUES (?, ?, ?, ?, ?, 'outbound', ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    telegram_message_id,
                    event_id,
                    bot_user_id,
                    bot_display_name,
                    text,
                    _text_digest(text),
                    sent_at.isoformat(),
                    now.isoformat(),
                    expires_at.isoformat(),
                    replied_to_message_id,
                ),
            )
            return _lastrowid(cursor) if cursor.rowcount == 1 else None

    def recent(self, *, chat_id: str, limit: int = _RECENT_LIMIT) -> tuple[StoredGroupMessage, ...]:
        if not 1 <= limit <= _RECENT_LIMIT:
            raise ValueError(f"limit must be in [1, {_RECENT_LIMIT}]")
        policy = self.policies.get(chat_id=chat_id)
        if policy is None or not policy.memory_enabled:
            return tuple(list(self._transient[chat_id])[-limit:])

        connection = self.database.connect()
        try:
            now = _utc_now().isoformat()
            rows = connection.execute(
                """
                SELECT id, chat_id, telegram_message_id, event_id,
                       sender_user_id, sender_display_name, direction, text,
                       sent_at, replied_to_message_id, replied_to_user_id
                FROM group_messages
                WHERE chat_id = ?
                  AND text IS NOT NULL
                  AND (text_expires_at IS NULL OR text_expires_at > ?)
                ORDER BY sent_at DESC, id DESC
                LIMIT ?
                """,
                (chat_id, now, limit),
            ).fetchall()
        finally:
            connection.close()
        return tuple(_stored_from_row(row) for row in reversed(rows))

    def search(
        self,
        *,
        chat_id: str,
        query: str,
        limit: int = 10,
        maximum_characters: int = 4_000,
        now: datetime | None = None,
    ) -> tuple[StoredGroupMessage, ...]:
        if not query.strip() or len(query) > 200:
            raise ValueError("query must be non-empty and at most 200 characters")
        if not 1 <= limit <= 10 or not 1 <= maximum_characters <= 4_000:
            raise ValueError("search bounds exceed the capability contract")
        current = now or _utc_now()
        connection = self.database.connect()
        try:
            rows = connection.execute(
                """
                SELECT id, chat_id, telegram_message_id, event_id,
                       sender_user_id, sender_display_name, direction, text,
                       sent_at, replied_to_message_id, replied_to_user_id
                FROM group_messages
                WHERE chat_id = ?
                  AND text IS NOT NULL
                  AND (text_expires_at IS NULL OR text_expires_at > ?)
                ORDER BY sent_at DESC, id DESC
                LIMIT 200
                """,
                (chat_id, current.isoformat()),
            ).fetchall()
        finally:
            connection.close()

        needle = query.casefold()
        result: list[StoredGroupMessage] = []
        character_count = 0
        for row in rows:
            text = str(row["text"])
            if needle not in text.casefold():
                continue
            if character_count + len(text) > maximum_characters:
                break
            result.append(_stored_from_row(row))
            character_count += len(text)
            if len(result) == limit:
                break
        return tuple(result)

    def purge_expired_text(
        self,
        *,
        now: datetime | None = None,
        batch_size: int = 500,
    ) -> int:
        if not 1 <= batch_size <= 1_000:
            raise ValueError("batch_size must be in [1, 1000]")
        timestamp = (now or _utc_now()).isoformat()
        with self.database.transaction() as connection:
            rows = connection.execute(
                """
                SELECT id FROM group_messages
                WHERE text IS NOT NULL
                  AND text_expires_at IS NOT NULL
                  AND text_expires_at <= ?
                ORDER BY id
                LIMIT ?
                """,
                (timestamp, batch_size),
            ).fetchall()
            ids = [int(row["id"]) for row in rows]
            if not ids:
                return 0
            placeholders = ",".join("?" for _ in ids)
            connection.execute(
                f"""
                UPDATE group_messages
                SET text = NULL, text_purged_at = ?
                WHERE id IN ({placeholders})
                """,
                (timestamp, *ids),
            )
            return len(ids)

    def _remember_transient_event(self, chat_id: str, event_id: str) -> bool:
        seen = self._seen_event_sets[chat_id]
        if event_id in seen:
            return False
        order = self._seen_events[chat_id]
        if len(order) == order.maxlen:
            evicted = order[0]
            seen.discard(evicted)
        order.append(event_id)
        seen.add(event_id)
        return True


def _from_telegram(message: TelegramTextMessage) -> StoredGroupMessage:
    return StoredGroupMessage(
        id=None,
        chat_id=message.group_id,
        telegram_message_id=message.message_id,
        event_id=message.event_id,
        sender_user_id=message.sender_id,
        sender_display_name=message.sender_display_name,
        direction="inbound",
        text=message.text,
        sent_at=message.timestamp,
        replied_to_message_id=message.replied_to_message_id,
        replied_to_user_id=message.replied_to_user_id,
    )


def _stored_from_row(row: sqlite3.Row) -> StoredGroupMessage:
    return StoredGroupMessage(
        id=int(row["id"]),
        chat_id=str(row["chat_id"]),
        telegram_message_id=str(row["telegram_message_id"]),
        event_id=str(row["event_id"]),
        sender_user_id=str(row["sender_user_id"]),
        sender_display_name=str(row["sender_display_name"]),
        direction=str(row["direction"]),
        text=str(row["text"]),
        sent_at=datetime.fromisoformat(str(row["sent_at"])),
        replied_to_message_id=(
            str(row["replied_to_message_id"]) if row["replied_to_message_id"] is not None else None
        ),
        replied_to_user_id=(
            str(row["replied_to_user_id"]) if row["replied_to_user_id"] is not None else None
        ),
    )


def _text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
