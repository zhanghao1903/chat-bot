from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_BUSY_TIMEOUT_MILLISECONDS = 5_000

_MIGRATIONS: tuple[tuple[int, str, str], ...] = (
    (
        1,
        "persona_runtime",
        """
        CREATE TABLE IF NOT EXISTS group_policies (
            chat_id TEXT PRIMARY KEY,
            memory_status TEXT NOT NULL DEFAULT 'disabled'
                CHECK (memory_status IN ('disabled', 'pending', 'enabled')),
            notice_message_id TEXT,
            enabled_by_user_id TEXT,
            enabled_at TEXT,
            persona_mode TEXT NOT NULL DEFAULT 'fixed'
                CHECK (persona_mode IN ('fixed', 'persona_direct', 'persona_full')),
            persona_id TEXT,
            persona_version TEXT,
            persona_digest TEXT,
            raw_retention_days INTEGER NOT NULL DEFAULT 7
                CHECK (raw_retention_days BETWEEN 1 AND 7),
            reset_generation INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS group_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            telegram_message_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            sender_user_id TEXT NOT NULL,
            sender_display_name TEXT NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
            text TEXT,
            sent_at TEXT NOT NULL,
            ingested_at TEXT NOT NULL,
            text_expires_at TEXT,
            text_purged_at TEXT,
            replied_to_message_id TEXT,
            replied_to_user_id TEXT,
            UNIQUE(chat_id, telegram_message_id),
            UNIQUE(chat_id, event_id),
            UNIQUE(id, chat_id)
        );

        CREATE INDEX IF NOT EXISTS idx_group_messages_recent
            ON group_messages(chat_id, sent_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_group_messages_member
            ON group_messages(chat_id, sender_user_id, sent_at DESC);

        CREATE TABLE IF NOT EXISTS recognition_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            source_message_id INTEGER NOT NULL,
            subject_user_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'leased', 'retry', 'completed', 'dead', 'superseded')),
            attempt_count INTEGER NOT NULL DEFAULT 0,
            lease_token TEXT,
            leased_until TEXT,
            next_attempt_at TEXT,
            recognition_policy_version TEXT NOT NULL,
            persona_id TEXT NOT NULL,
            persona_version TEXT NOT NULL,
            persona_digest TEXT NOT NULL,
            reset_generation INTEGER NOT NULL,
            error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source_message_id, subject_user_id),
            FOREIGN KEY (source_message_id, chat_id) REFERENCES group_messages(id, chat_id)
        );

        CREATE INDEX IF NOT EXISTS idx_recognition_jobs_due
            ON recognition_jobs(chat_id, status, next_attempt_at, id);

        CREATE TABLE IF NOT EXISTS member_memory_items (
            memory_id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL,
            member_user_id TEXT NOT NULL,
            category TEXT NOT NULL
                CHECK (
                    category IN (
                        'fact', 'observation', 'impression',
                        'shared_experience', 'preference'
                    )
                ),
            statement TEXT NOT NULL,
            stored_confidence REAL NOT NULL
                CHECK (stored_confidence >= 0.0 AND stored_confidence <= 1.0),
            first_observed_at TEXT NOT NULL,
            last_supported_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'superseded', 'revoked')),
            recognition_policy_version TEXT NOT NULL,
            persona_id TEXT,
            persona_version TEXT,
            persona_digest TEXT,
            revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
            UNIQUE(memory_id, chat_id)
        );

        CREATE INDEX IF NOT EXISTS idx_member_memory_active
            ON member_memory_items(chat_id, member_user_id, status, category, updated_at DESC);

        CREATE TABLE IF NOT EXISTS member_memory_sources (
            memory_id TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            source_message_id INTEGER NOT NULL,
            PRIMARY KEY (memory_id, source_message_id),
            FOREIGN KEY (memory_id, chat_id)
                REFERENCES member_memory_items(memory_id, chat_id) ON DELETE CASCADE,
            FOREIGN KEY (source_message_id, chat_id)
                REFERENCES group_messages(id, chat_id)
        );

        CREATE TABLE IF NOT EXISTS memory_reset_barriers (
            chat_id TEXT NOT NULL,
            member_user_id TEXT NOT NULL,
            ignore_sources_before TEXT NOT NULL,
            generation INTEGER NOT NULL,
            reset_by_user_id TEXT NOT NULL,
            reset_at TEXT NOT NULL,
            PRIMARY KEY (chat_id, member_user_id)
        );

        CREATE TABLE IF NOT EXISTS trigger_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE,
            chat_id TEXT NOT NULL,
            trigger_event_id TEXT NOT NULL,
            trigger_message_id TEXT NOT NULL,
            candidate_kind TEXT NOT NULL,
            persona_id TEXT NOT NULL,
            persona_version TEXT NOT NULL,
            persona_digest TEXT NOT NULL,
            result_kind TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            model_status TEXT NOT NULL
                CHECK (model_status IN ('not_called', 'completed', 'failed')),
            deadline_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_trigger_runs_chat_event
            ON trigger_runs(chat_id, trigger_event_id);

        CREATE TABLE IF NOT EXISTS effect_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE,
            chat_id TEXT NOT NULL,
            trigger_event_id TEXT NOT NULL,
            trigger_message_id TEXT NOT NULL,
            trigger_path TEXT NOT NULL CHECK (trigger_path IN ('direct', 'contextual')),
            persona_id TEXT NOT NULL,
            persona_version TEXT NOT NULL,
            persona_digest TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK (status IN ('processing', 'reply', 'silence', 'failure_reply', 'failed')),
            model_call_count INTEGER NOT NULL DEFAULT 0,
            tool_call_count INTEGER NOT NULL DEFAULT 0,
            reason_code TEXT,
            error_code TEXT,
            deadline_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS external_effects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            trigger_event_id TEXT NOT NULL,
            trigger_message_id TEXT NOT NULL,
            effect_kind TEXT NOT NULL
                CHECK (effect_kind IN ('reply', 'failure_reply', 'control_ack')),
            status TEXT NOT NULL
                CHECK (status IN ('sending', 'sent', 'failed', 'uncertain')),
            persona_version TEXT,
            persona_digest TEXT,
            platform_message_id TEXT,
            error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(chat_id, trigger_event_id)
        );

        CREATE TABLE IF NOT EXISTS tool_call_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_kind TEXT NOT NULL CHECK (owner_kind IN ('effect', 'recognition')),
            owner_id INTEGER NOT NULL,
            chat_id TEXT NOT NULL,
            capability TEXT NOT NULL,
            purpose_code TEXT NOT NULL,
            source_scope TEXT NOT NULL,
            status TEXT NOT NULL,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            result_count INTEGER NOT NULL DEFAULT 0,
            result_char_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_tool_call_audit_owner
            ON tool_call_audit(chat_id, owner_kind, owner_id);

        CREATE TABLE IF NOT EXISTS recognition_change_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            member_user_id TEXT NOT NULL,
            memory_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            source_message_ids TEXT NOT NULL,
            recognition_job_id INTEGER NOT NULL,
            policy_version TEXT NOT NULL,
            persona_version TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (recognition_job_id) REFERENCES recognition_jobs(id)
        );

        CREATE TABLE IF NOT EXISTS control_action_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            command TEXT NOT NULL,
            requesting_user_id TEXT NOT NULL,
            target_user_id TEXT,
            authorization_status TEXT NOT NULL
                CHECK (authorization_status IN ('authorized', 'denied', 'unavailable')),
            outcome TEXT NOT NULL,
            error_code TEXT,
            created_at TEXT NOT NULL
        );
        """,
    ),
)


class SQLiteDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MILLISECONDS}")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        connection = self.connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
                """
            )
            connection.commit()
            applied = {
                int(row["version"])
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for version, name, script in _MIGRATIONS:
                if version in applied:
                    continue
                safe_name = name.replace("'", "''")
                migration_script = (
                    "BEGIN IMMEDIATE;\n"
                    f"{script}\n"
                    "INSERT INTO schema_migrations (version, name, applied_at) "
                    f"VALUES ({version}, '{safe_name}', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));\n"
                    "COMMIT;"
                )
                try:
                    connection.executescript(migration_script)
                except Exception:
                    if connection.in_transaction:
                        connection.rollback()
                    raise
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
