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
            text_sha256 TEXT NOT NULL,
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
    (
        2,
        "conversation_triggers_v0_2",
        """
        ALTER TABLE effect_runs
            ADD COLUMN trigger_category TEXT NOT NULL DEFAULT 'ordinary_contextual'
                CHECK (
                    trigger_category IN (
                        'direct_platform', 'direct_persona_name',
                        'conversation_continuity', 'ordinary_contextual'
                    )
                );

        UPDATE effect_runs
        SET trigger_category = 'direct_platform'
        WHERE trigger_path = 'direct';

        CREATE TABLE IF NOT EXISTS trigger_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE,
            chat_id TEXT NOT NULL,
            trigger_event_id TEXT NOT NULL,
            trigger_message_id TEXT NOT NULL,
            trigger_category TEXT NOT NULL
                CHECK (
                    trigger_category IN (
                        'direct_platform', 'direct_persona_name',
                        'conversation_continuity', 'ordinary_contextual',
                        'control', 'ignored'
                    )
                ),
            persona_name_hit INTEGER NOT NULL DEFAULT 0
                CHECK (persona_name_hit IN (0, 1)),
            continuity_anchor_message_id TEXT,
            decision_kind TEXT NOT NULL
                CHECK (
                    decision_kind IN (
                        'effect_requested', 'silence', 'ignored', 'control'
                    )
                ),
            reason_code TEXT NOT NULL,
            model_status TEXT NOT NULL
                CHECK (model_status IN ('not_called', 'completed', 'failed')),
            persona_id TEXT NOT NULL,
            persona_version TEXT NOT NULL,
            persona_digest TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(chat_id, trigger_event_id)
        );

        CREATE INDEX IF NOT EXISTS idx_trigger_evaluations_chat_event
            ON trigger_evaluations(chat_id, trigger_event_id);
        """,
    ),
    (
        3,
        "visual_expression_v0_3",
        """
        ALTER TABLE group_messages
            ADD COLUMN media_kind TEXT
                CHECK (media_kind IN ('photo', 'static_document', 'static_sticker'));
        ALTER TABLE group_messages ADD COLUMN media_unique_id TEXT;
        ALTER TABLE group_messages ADD COLUMN media_catalog_id TEXT;

        ALTER TABLE effect_runs RENAME TO effect_runs_v2;
        CREATE TABLE effect_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE,
            chat_id TEXT NOT NULL,
            trigger_event_id TEXT NOT NULL,
            trigger_message_id TEXT NOT NULL,
            trigger_path TEXT NOT NULL CHECK (trigger_path IN ('direct', 'contextual')),
            trigger_category TEXT NOT NULL DEFAULT 'ordinary_contextual'
                CHECK (
                    trigger_category IN (
                        'direct_platform', 'direct_persona_name',
                        'conversation_continuity', 'ordinary_contextual'
                    )
                ),
            persona_id TEXT NOT NULL,
            persona_version TEXT NOT NULL,
            persona_digest TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK (
                    status IN (
                        'processing', 'reply', 'sticker', 'silence',
                        'failure_reply', 'failed'
                    )
                ),
            model_call_count INTEGER NOT NULL DEFAULT 0,
            tool_call_count INTEGER NOT NULL DEFAULT 0,
            reason_code TEXT,
            error_code TEXT,
            deadline_at TEXT NOT NULL,
            vision_status TEXT NOT NULL DEFAULT 'not_called'
                CHECK (vision_status IN ('not_called', 'completed', 'failed')),
            vision_model TEXT,
            catalog_version TEXT,
            catalog_digest TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO effect_runs (
            id, request_id, chat_id, trigger_event_id, trigger_message_id,
            trigger_path, trigger_category, persona_id, persona_version,
            persona_digest, status, model_call_count, tool_call_count,
            reason_code, error_code, deadline_at, created_at, updated_at
        )
        SELECT
            id, request_id, chat_id, trigger_event_id, trigger_message_id,
            trigger_path, trigger_category, persona_id, persona_version,
            persona_digest, status, model_call_count, tool_call_count,
            reason_code, error_code, deadline_at, created_at, updated_at
        FROM effect_runs_v2;
        DROP TABLE effect_runs_v2;
        CREATE INDEX idx_effect_runs_chat_event
            ON effect_runs(chat_id, trigger_event_id);

        ALTER TABLE external_effects RENAME TO external_effects_v2;
        CREATE TABLE external_effects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            trigger_event_id TEXT NOT NULL,
            trigger_message_id TEXT NOT NULL,
            effect_kind TEXT NOT NULL
                CHECK (effect_kind IN ('reply', 'sticker', 'failure_reply', 'control_ack')),
            requested_effect_kind TEXT NOT NULL
                CHECK (
                    requested_effect_kind IN (
                        'reply', 'sticker', 'failure_reply', 'control_ack'
                    )
                ),
            delivered_effect_kind TEXT
                CHECK (
                    delivered_effect_kind IS NULL OR delivered_effect_kind IN (
                        'reply', 'sticker', 'failure_reply', 'control_ack'
                    )
                ),
            asset_semantic_id TEXT,
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
        INSERT INTO external_effects (
            id, chat_id, trigger_event_id, trigger_message_id, effect_kind,
            requested_effect_kind, delivered_effect_kind, status,
            persona_version, persona_digest, platform_message_id, error_code,
            created_at, updated_at
        )
        SELECT
            id, chat_id, trigger_event_id, trigger_message_id, effect_kind,
            effect_kind,
            CASE WHEN status = 'sent' THEN effect_kind ELSE NULL END,
            status, persona_version, persona_digest, platform_message_id,
            error_code, created_at, updated_at
        FROM external_effects_v2;
        DROP TABLE external_effects_v2;

        ALTER TABLE tool_call_audit
            ADD COLUMN budget_ordinal INTEGER NOT NULL DEFAULT 0
                CHECK (budget_ordinal >= 0);
        ALTER TABLE tool_call_audit ADD COLUMN extension_reason_code TEXT;
        ALTER TABLE tool_call_audit
            ADD COLUMN result_novel INTEGER NOT NULL DEFAULT 0
                CHECK (result_novel IN (0, 1));

        CREATE TABLE media_effect_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            trigger_event_id TEXT NOT NULL,
            media_kind TEXT NOT NULL
                CHECK (media_kind IN ('photo', 'static_document', 'static_sticker')),
            result_status TEXT NOT NULL,
            byte_bucket TEXT,
            pixel_bucket TEXT,
            model_id TEXT,
            latency_ms INTEGER NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
            error_code TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX idx_media_effect_audit_event
            ON media_effect_audit(chat_id, trigger_event_id);

        CREATE TABLE persona_mood_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_user_id TEXT NOT NULL,
            trigger_event_id TEXT NOT NULL,
            persona_version TEXT NOT NULL,
            persona_digest TEXT NOT NULL,
            catalog_version TEXT,
            catalog_digest TEXT,
            mood_code TEXT NOT NULL,
            bot_scope_count INTEGER NOT NULL DEFAULT 1 CHECK (bot_scope_count >= 1),
            created_at TEXT NOT NULL,
            UNIQUE(bot_user_id, trigger_event_id)
        );
        CREATE INDEX idx_persona_mood_recent
            ON persona_mood_observations(bot_user_id, created_at DESC);

        CREATE TABLE avatar_change_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_user_id TEXT NOT NULL,
            avatar_catalog_version TEXT NOT NULL,
            avatar_catalog_digest TEXT NOT NULL,
            previous_avatar_id TEXT,
            requested_avatar_id TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            cooldown_status TEXT NOT NULL,
            requested_by TEXT NOT NULL,
            platform_status TEXT NOT NULL,
            error_code TEXT,
            rollback_status TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX idx_avatar_change_recent
            ON avatar_change_audit(bot_user_id, created_at DESC);
        """,
    ),
    (
        4,
        "avatar_global_provenance",
        """
        ALTER TABLE persona_mood_observations ADD COLUMN chat_id TEXT;
        ALTER TABLE persona_mood_observations ADD COLUMN member_user_id TEXT;
        ALTER TABLE avatar_change_audit ADD COLUMN requested_image_sha256 TEXT;
        CREATE INDEX idx_persona_mood_provenance
            ON persona_mood_observations(
                bot_user_id, mood_code, chat_id, member_user_id, created_at DESC
            );
        """,
    ),
    (
        5,
        "scheduled_food_automation_v0_4",
        """
        ALTER TABLE effect_runs RENAME TO effect_runs_v4;
        DROP INDEX IF EXISTS idx_effect_runs_chat_event;
        CREATE TABLE effect_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE,
            chat_id TEXT NOT NULL,
            trigger_event_id TEXT NOT NULL,
            trigger_message_id TEXT,
            trigger_path TEXT NOT NULL
                CHECK (trigger_path IN ('direct', 'contextual', 'scheduled')),
            trigger_category TEXT NOT NULL DEFAULT 'ordinary_contextual'
                CHECK (
                    trigger_category IN (
                        'direct_platform', 'direct_persona_name',
                        'conversation_continuity', 'ordinary_contextual',
                        'scheduled_automation'
                    )
                ),
            source_kind TEXT NOT NULL DEFAULT 'inbound'
                CHECK (source_kind IN ('inbound', 'scheduled')),
            scheduled_occurrence_id TEXT,
            persona_id TEXT NOT NULL,
            persona_version TEXT NOT NULL,
            persona_digest TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK (
                    status IN (
                        'processing', 'reply', 'sticker', 'silence',
                        'failure_reply', 'failed'
                    )
                ),
            model_call_count INTEGER NOT NULL DEFAULT 0,
            tool_call_count INTEGER NOT NULL DEFAULT 0,
            reason_code TEXT,
            error_code TEXT,
            deadline_at TEXT NOT NULL,
            vision_status TEXT NOT NULL DEFAULT 'not_called'
                CHECK (vision_status IN ('not_called', 'completed', 'failed')),
            vision_model TEXT,
            catalog_version TEXT,
            catalog_digest TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (
                (source_kind = 'inbound' AND trigger_message_id IS NOT NULL
                    AND scheduled_occurrence_id IS NULL)
                OR
                (source_kind = 'scheduled' AND trigger_message_id IS NULL
                    AND scheduled_occurrence_id IS NOT NULL)
            )
        );
        INSERT INTO effect_runs (
            id, request_id, chat_id, trigger_event_id, trigger_message_id,
            trigger_path, trigger_category, source_kind, scheduled_occurrence_id,
            persona_id, persona_version, persona_digest, status,
            model_call_count, tool_call_count, reason_code, error_code,
            deadline_at, vision_status, vision_model, catalog_version,
            catalog_digest, created_at, updated_at
        )
        SELECT
            id, request_id, chat_id, trigger_event_id, trigger_message_id,
            trigger_path, trigger_category, 'inbound', NULL,
            persona_id, persona_version, persona_digest, status,
            model_call_count, tool_call_count, reason_code, error_code,
            deadline_at, vision_status, vision_model, catalog_version,
            catalog_digest, created_at, updated_at
        FROM effect_runs_v4;
        DROP TABLE effect_runs_v4;
        CREATE INDEX idx_effect_runs_chat_event
            ON effect_runs(chat_id, trigger_event_id);

        ALTER TABLE external_effects RENAME TO external_effects_v4;
        CREATE TABLE external_effects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            trigger_event_id TEXT NOT NULL,
            trigger_message_id TEXT,
            effect_kind TEXT NOT NULL
                CHECK (effect_kind IN ('reply', 'sticker', 'failure_reply', 'control_ack')),
            requested_effect_kind TEXT NOT NULL
                CHECK (
                    requested_effect_kind IN (
                        'reply', 'sticker', 'failure_reply', 'control_ack'
                    )
                ),
            delivered_effect_kind TEXT
                CHECK (
                    delivered_effect_kind IS NULL OR delivered_effect_kind IN (
                        'reply', 'sticker', 'failure_reply', 'control_ack'
                    )
                ),
            asset_semantic_id TEXT,
            status TEXT NOT NULL
                CHECK (status IN ('sending', 'sent', 'failed', 'uncertain')),
            persona_version TEXT,
            persona_digest TEXT,
            platform_message_id TEXT,
            error_code TEXT,
            source_kind TEXT NOT NULL DEFAULT 'inbound'
                CHECK (source_kind IN ('inbound', 'scheduled')),
            scheduled_occurrence_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(chat_id, trigger_event_id),
            CHECK (
                (source_kind = 'inbound' AND trigger_message_id IS NOT NULL
                    AND scheduled_occurrence_id IS NULL)
                OR
                (source_kind = 'scheduled' AND trigger_message_id IS NULL
                    AND scheduled_occurrence_id IS NOT NULL)
            )
        );
        INSERT INTO external_effects (
            id, chat_id, trigger_event_id, trigger_message_id, effect_kind,
            requested_effect_kind, delivered_effect_kind, asset_semantic_id,
            status, persona_version, persona_digest, platform_message_id,
            error_code, source_kind, scheduled_occurrence_id, created_at, updated_at
        )
        SELECT
            id, chat_id, trigger_event_id, trigger_message_id, effect_kind,
            requested_effect_kind, delivered_effect_kind, asset_semantic_id,
            status, persona_version, persona_digest, platform_message_id,
            error_code, 'inbound', NULL, created_at, updated_at
        FROM external_effects_v4;
        DROP TABLE external_effects_v4;

        ALTER TABLE tool_call_audit ADD COLUMN budget_kind TEXT NOT NULL DEFAULT 'context'
            CHECK (budget_kind IN ('context', 'web'));
        ALTER TABLE tool_call_audit ADD COLUMN provider_request_id TEXT;
        ALTER TABLE tool_call_audit ADD COLUMN provider_credits REAL;
        ALTER TABLE tool_call_audit ADD COLUMN source_domains_json TEXT;
        ALTER TABLE tool_call_audit ADD COLUMN retrieved_at TEXT;
        ALTER TABLE tool_call_audit ADD COLUMN provider_error_code TEXT;

        CREATE TABLE automation_group_configs (
            chat_id TEXT NOT NULL,
            automation_type TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
            paused INTEGER NOT NULL DEFAULT 0 CHECK (paused IN (0, 1)),
            timezone TEXT NOT NULL,
            lunch_time TEXT NOT NULL,
            dinner_time TEXT NOT NULL,
            location_text TEXT,
            config_version INTEGER NOT NULL DEFAULT 1 CHECK (config_version >= 1),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (chat_id, automation_type)
        );

        CREATE TABLE automation_subscriptions (
            chat_id TEXT NOT NULL,
            automation_type TEXT NOT NULL,
            member_user_id TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
            cuisine_tags_json TEXT NOT NULL DEFAULT '[]',
            budget_band TEXT,
            dietary_tags_json TEXT NOT NULL DEFAULT '[]',
            avoid_items_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (chat_id, automation_type, member_user_id),
            FOREIGN KEY (chat_id, automation_type)
                REFERENCES automation_group_configs(chat_id, automation_type)
                ON DELETE CASCADE
        );
        CREATE INDEX idx_automation_subscriptions_active
            ON automation_subscriptions(chat_id, automation_type, active);

        CREATE TABLE automation_occurrences (
            occurrence_id TEXT PRIMARY KEY,
            occurrence_key TEXT NOT NULL UNIQUE,
            chat_id TEXT NOT NULL,
            automation_type TEXT NOT NULL,
            local_date TEXT NOT NULL,
            slot TEXT NOT NULL CHECK (slot IN ('lunch', 'dinner')),
            scheduled_for TEXT NOT NULL,
            grace_deadline TEXT NOT NULL,
            config_version INTEGER NOT NULL CHECK (config_version >= 1),
            persona_id TEXT NOT NULL,
            persona_version TEXT NOT NULL,
            persona_digest TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'due'
                CHECK (
                    status IN (
                        'due', 'leased', 'prepared', 'sending', 'sent',
                        'skipped_no_subscribers', 'skipped_disabled',
                        'skipped_late', 'tool_degraded', 'definite_failure',
                        'uncertain'
                    )
                ),
            lease_owner TEXT,
            lease_expires_at TEXT,
            effect_request_id TEXT,
            prepared_primary_key TEXT,
            prepared_payload_json TEXT,
            prepared_text TEXT,
            external_effect_id INTEGER,
            reason_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(chat_id, automation_type, local_date, slot),
            FOREIGN KEY (chat_id, automation_type)
                REFERENCES automation_group_configs(chat_id, automation_type)
        );
        CREATE INDEX idx_automation_occurrences_due
            ON automation_occurrences(status, scheduled_for, lease_expires_at);
        CREATE INDEX idx_automation_occurrences_chat_history
            ON automation_occurrences(chat_id, automation_type, status, scheduled_for DESC);

        CREATE TABLE automation_action_audit (
            action_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            automation_type TEXT NOT NULL,
            actor_user_id TEXT NOT NULL,
            actor_role TEXT NOT NULL,
            action_kind TEXT NOT NULL,
            result_kind TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            config_version INTEGER,
            created_at TEXT NOT NULL,
            purge_after TEXT NOT NULL
        );
        CREATE INDEX idx_automation_action_audit_purge
            ON automation_action_audit(purge_after);
        """,
    ),
    (
        6,
        "composite_effect_bundles_v0_3_1",
        """
        CREATE TABLE effect_bundles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bundle_id TEXT NOT NULL UNIQUE,
            bot_user_id TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            trigger_event_id TEXT NOT NULL,
            trigger_message_id TEXT NOT NULL,
            persona_version TEXT NOT NULL,
            persona_digest TEXT NOT NULL,
            catalog_version TEXT,
            catalog_digest TEXT,
            requested_form TEXT NOT NULL
                CHECK (requested_form IN ('text', 'sticker', 'text_sticker', 'failure_text')),
            reason_code TEXT NOT NULL,
            sticker_eligible INTEGER NOT NULL CHECK (sticker_eligible IN (0, 1)),
            eligibility_reason TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK (
                    status IN (
                        'prepared', 'delivering', 'completed', 'degraded',
                        'failed', 'uncertain', 'interrupted'
                    )
                ),
            error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            UNIQUE(chat_id, trigger_event_id)
        );
        CREATE INDEX idx_effect_bundles_metrics
            ON effect_bundles(
                bot_user_id, persona_version, persona_digest,
                catalog_version, catalog_digest, completed_at DESC, id DESC
            );

        CREATE TABLE effect_bundle_components (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bundle_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal IN (1, 2)),
            component_kind TEXT NOT NULL CHECK (component_kind IN ('text', 'sticker')),
            requested_effect_kind TEXT NOT NULL
                CHECK (requested_effect_kind IN ('reply', 'failure_reply', 'sticker')),
            asset_semantic_id TEXT,
            text_character_count INTEGER
                CHECK (text_character_count IS NULL OR text_character_count >= 0),
            status TEXT NOT NULL
                CHECK (status IN ('planned', 'sending', 'sent', 'failed', 'uncertain', 'skipped')),
            platform_message_id TEXT,
            error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(bundle_id, ordinal),
            FOREIGN KEY (bundle_id) REFERENCES effect_bundles(bundle_id)
        );
        CREATE INDEX idx_effect_bundle_components_status
            ON effect_bundle_components(status, bundle_id, ordinal);

        ALTER TABLE avatar_change_audit ADD COLUMN operation_id TEXT;
        ALTER TABLE avatar_change_audit ADD COLUMN api_method TEXT;
        ALTER TABLE avatar_change_audit ADD COLUMN authorization_reference TEXT;
        CREATE UNIQUE INDEX idx_avatar_change_operation
            ON avatar_change_audit(operation_id)
            WHERE operation_id IS NOT NULL;
        """,
    ),
    (
        7,
        "temporal_awareness_v1",
        """
        CREATE TABLE temporal_context_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            effect_run_id INTEGER NOT NULL,
            model_call_ordinal INTEGER NOT NULL CHECK (model_call_ordinal BETWEEN 1 AND 12),
            context_version TEXT,
            context_id TEXT,
            captured_at_utc TEXT,
            answer_timezone TEXT,
            utc_offset TEXT,
            timezone_selection TEXT
                CHECK (
                    timezone_selection IS NULL OR timezone_selection IN (
                        'group_default', 'writer_explicit_override'
                    )
                ),
            source_class TEXT CHECK (source_class IS NULL OR source_class = 'system_clock'),
            status TEXT NOT NULL CHECK (status IN ('valid', 'failed')),
            error_code TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(effect_run_id, model_call_ordinal),
            FOREIGN KEY (effect_run_id) REFERENCES effect_runs(id)
        );
        CREATE INDEX idx_temporal_context_samples_effect
            ON temporal_context_samples(effect_run_id, model_call_ordinal);

        CREATE TABLE temporal_answer_audit (
            effect_run_id INTEGER PRIMARY KEY,
            chat_id TEXT NOT NULL,
            trigger_event_id TEXT NOT NULL,
            source_kind TEXT NOT NULL CHECK (source_kind IN ('inbound', 'scheduled')),
            final_context_id TEXT,
            final_captured_at_utc TEXT,
            answer_timezone TEXT,
            utc_offset TEXT,
            freshness_mode TEXT
                CHECK (
                    freshness_mode IS NULL OR freshness_mode IN (
                        'stable', 'clock', 'current_verified', 'current_unverified'
                    )
                ),
            web_requested INTEGER NOT NULL DEFAULT 0 CHECK (web_requested IN (0, 1)),
            web_audit_ids_json TEXT NOT NULL DEFAULT '[]',
            latest_web_retrieved_at TEXT,
            status TEXT NOT NULL
                CHECK (status IN ('completed', 'degraded', 'failed', 'silence')),
            degradation_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (effect_run_id) REFERENCES effect_runs(id)
        );
        CREATE INDEX idx_temporal_answer_audit_scope
            ON temporal_answer_audit(chat_id, trigger_event_id);
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
