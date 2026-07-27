from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _lastrowid(cursor: sqlite3.Cursor) -> int:
    value = cursor.lastrowid
    if value is None:
        raise sqlite3.DatabaseError("Insert did not produce a row id")
    return value


@dataclass(frozen=True)
class DeliveryRecord:
    id: int
    chat_id: str
    message_id: str
    action_kind: str
    status: str
    error_code: str | None


class SQLiteDeliveryLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row

    def initialize(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS delivery_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                action_kind TEXT NOT NULL,
                status TEXT NOT NULL,
                error_code TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(chat_id, message_id, action_kind)
            )
            """
        )
        self.connection.commit()

    def claim(
        self,
        *,
        chat_id: str,
        message_id: str,
        action_kind: str,
    ) -> int | None:
        now = _utc_now()
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO delivery_ledger (
                chat_id, message_id, action_kind, status, created_at, updated_at
            )
            VALUES (?, ?, ?, 'sending', ?, ?)
            """,
            (chat_id, message_id, action_kind, now, now),
        )
        self.connection.commit()
        if cursor.rowcount == 0:
            return None
        return _lastrowid(cursor)

    def mark_sent(self, delivery_id: int) -> None:
        self._set_status(delivery_id, status="sent", error_code=None)

    def mark_failed(self, delivery_id: int, *, error_code: str) -> None:
        self._set_status(delivery_id, status="failed", error_code=error_code)

    def get(
        self,
        *,
        chat_id: str,
        message_id: str,
        action_kind: str,
    ) -> DeliveryRecord | None:
        row = self.connection.execute(
            """
            SELECT id, chat_id, message_id, action_kind, status, error_code
            FROM delivery_ledger
            WHERE chat_id = ? AND message_id = ? AND action_kind = ?
            """,
            (chat_id, message_id, action_kind),
        ).fetchone()
        if row is None:
            return None
        return DeliveryRecord(
            id=int(row["id"]),
            chat_id=str(row["chat_id"]),
            message_id=str(row["message_id"]),
            action_kind=str(row["action_kind"]),
            status=str(row["status"]),
            error_code=str(row["error_code"]) if row["error_code"] is not None else None,
        )

    def _set_status(
        self,
        delivery_id: int,
        *,
        status: str,
        error_code: str | None,
    ) -> None:
        cursor = self.connection.execute(
            """
            UPDATE delivery_ledger
            SET status = ?, error_code = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, error_code, _utc_now(), delivery_id),
        )
        self.connection.commit()
        if cursor.rowcount != 1:
            raise ValueError(f"Unknown delivery id: {delivery_id}")

    def close(self) -> None:
        self.connection.close()
