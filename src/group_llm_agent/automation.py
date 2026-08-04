from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from group_llm_agent.database import SQLiteDatabase
from group_llm_agent.events import PersonaSnapshot, ScheduledOccurrenceSource

_TYPE_ID = "weekday_food_recommendation"
_DEFAULT_TIMEZONE = "Asia/Shanghai"
_DEFAULT_LUNCH = "11:30"
_DEFAULT_DINNER = "17:30"
_GRACE = timedelta(minutes=30)
_LEASE = timedelta(minutes=2)
_SAFE_TOKEN = re.compile(r"^[^\x00-\x1f\x7f]{1,32}$")
_SENSITIVE_REASON = re.compile(
    r"过敏|病|药|宗教|清真|犹太|收入|贫困|allerg|medical|religio|income",
    re.IGNORECASE,
)
_CUISINES = frozenset(
    {"chinese", "japanese", "korean", "southeast_asian", "western", "noodles", "rice"}
)
_DIETARY_TAGS = frozenset({"vegetarian", "light", "spicy", "not_spicy"})
_BUDGET_BANDS = frozenset({"low", "medium", "high"})


class MealSlot(StrEnum):
    LUNCH = "lunch"
    DINNER = "dinner"


class OccurrenceStatus(StrEnum):
    DUE = "due"
    LEASED = "leased"
    PREPARED = "prepared"
    SENDING = "sending"
    SENT = "sent"
    SKIPPED_NO_SUBSCRIBERS = "skipped_no_subscribers"
    SKIPPED_DISABLED = "skipped_disabled"
    SKIPPED_LATE = "skipped_late"
    TOOL_DEGRADED = "tool_degraded"
    DEFINITE_FAILURE = "definite_failure"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class AutomationDefinition:
    type_id: str = _TYPE_ID
    default_timezone: str = _DEFAULT_TIMEZONE
    default_lunch: str = _DEFAULT_LUNCH
    default_dinner: str = _DEFAULT_DINNER
    grace: timedelta = _GRACE
    web_tool_limit: int = 5
    context_tool_ordinary_limit: int = 3
    context_tool_complex_limit: int = 5


AUTOMATION_REGISTRY = {_TYPE_ID: AutomationDefinition()}


@dataclass(frozen=True)
class GroupAutomationConfig:
    chat_id: str
    automation_type: str
    enabled: bool
    paused: bool
    timezone: str
    lunch_time: str
    dinner_time: str
    location_text: str | None
    config_version: int


@dataclass(frozen=True)
class SubscriptionPreferences:
    cuisine_tags: tuple[str, ...] = ()
    budget_band: str | None = None
    dietary_tags: tuple[str, ...] = ()
    avoid_items: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_preference_values(self)


@dataclass(frozen=True)
class AggregatedPreferences:
    subscriber_count: int
    summary: tuple[str, ...]


@dataclass(frozen=True)
class AutomationOccurrence:
    occurrence_id: str
    occurrence_key: str
    chat_id: str
    automation_type: str
    local_date: str
    slot: MealSlot
    scheduled_for: datetime
    grace_deadline: datetime
    config_version: int
    persona: PersonaSnapshot
    status: OccurrenceStatus
    prepared_primary_key: str | None = None
    prepared_text: str | None = None
    reason_code: str | None = None


def definition_for(type_id: str) -> AutomationDefinition:
    try:
        return AUTOMATION_REGISTRY[type_id]
    except KeyError:
        raise ValueError("unknown automation type") from None


def validate_timezone(value: str) -> str:
    if not value or len(value) > 64 or value.startswith(("+", "-")):
        raise ValueError("invalid timezone")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("invalid timezone") from None
    return value


def validate_meal_time(value: str) -> str:
    try:
        parsed = time.fromisoformat(value)
    except ValueError:
        raise ValueError("invalid meal time") from None
    if parsed.second or parsed.microsecond or len(value) != 5:
        raise ValueError("meal time must use HH:MM")
    return value


def validate_location(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    if not normalized:
        return None
    if len(normalized) > 120 or not _SAFE_TOKEN.fullmatch(normalized) or "://" in normalized:
        raise ValueError("invalid location")
    return normalized


def scheduled_instant(
    *,
    local_date: date,
    slot: MealSlot,
    timezone: str,
    lunch_time: str,
    dinner_time: str,
) -> datetime | None:
    if local_date.weekday() >= 5:
        return None
    zone = ZoneInfo(validate_timezone(timezone))
    wall_time = time.fromisoformat(
        validate_meal_time(lunch_time if slot is MealSlot.LUNCH else dinner_time)
    )
    naive = datetime.combine(local_date, wall_time)
    candidates: list[datetime] = []
    for fold in (0, 1):
        local = naive.replace(tzinfo=zone, fold=fold)
        round_trip = local.astimezone(UTC).astimezone(zone)
        if round_trip.replace(tzinfo=None) == naive:
            candidates.append(local.astimezone(UTC))
    return min(candidates) if candidates else None


def occurrence_identity(
    *, bot_user_id: str, chat_id: str, local_date: date, slot: MealSlot
) -> tuple[str, str]:
    parts = (bot_user_id, chat_id, _TYPE_ID, local_date.isoformat(), slot.value)
    occurrence_key = "|".join(f"{len(part)}:{part}" for part in parts)
    digest = hashlib.sha256(f"v1|{occurrence_key}".encode()).hexdigest()
    return f"automation:v1:{digest}", occurrence_key


class AutomationRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def enable_group(
        self,
        *,
        chat_id: str,
        timezone: str = _DEFAULT_TIMEZONE,
        lunch_time: str = _DEFAULT_LUNCH,
        dinner_time: str = _DEFAULT_DINNER,
        location_text: str | None = None,
    ) -> GroupAutomationConfig:
        definition_for(_TYPE_ID)
        timezone = validate_timezone(timezone)
        lunch_time = validate_meal_time(lunch_time)
        dinner_time = validate_meal_time(dinner_time)
        if lunch_time == dinner_time:
            raise ValueError("meal times must be distinct")
        location_text = validate_location(location_text)
        now = _utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO automation_group_configs (
                    chat_id, automation_type, enabled, paused, timezone,
                    lunch_time, dinner_time, location_text, config_version,
                    created_at, updated_at
                ) VALUES (?, ?, 1, 0, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(chat_id, automation_type) DO UPDATE SET
                    enabled = 1, paused = 0, timezone = excluded.timezone,
                    lunch_time = excluded.lunch_time,
                    dinner_time = excluded.dinner_time,
                    location_text = excluded.location_text,
                    config_version = automation_group_configs.config_version + 1,
                    updated_at = excluded.updated_at
                """,
                (
                    chat_id,
                    _TYPE_ID,
                    timezone,
                    lunch_time,
                    dinner_time,
                    location_text,
                    now,
                    now,
                ),
            )
        config = self.get_config(chat_id=chat_id)
        assert config is not None
        return config

    def get_config(self, *, chat_id: str) -> GroupAutomationConfig | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM automation_group_configs
                WHERE chat_id = ? AND automation_type = ?
                """,
                (chat_id, _TYPE_ID),
            ).fetchone()
        return _config_from_row(row) if row is not None else None

    def list_configs(self) -> tuple[GroupAutomationConfig, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM automation_group_configs
                WHERE automation_type = ? ORDER BY chat_id
                """,
                (_TYPE_ID,),
            ).fetchall()
        return tuple(_config_from_row(row) for row in rows)

    def update_config(
        self,
        *,
        chat_id: str,
        timezone: str,
        lunch_time: str,
        dinner_time: str,
        location_text: str | None,
    ) -> GroupAutomationConfig:
        timezone = validate_timezone(timezone)
        lunch_time = validate_meal_time(lunch_time)
        dinner_time = validate_meal_time(dinner_time)
        if lunch_time == dinner_time:
            raise ValueError("meal times must be distinct")
        location_text = validate_location(location_text)
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE automation_group_configs
                SET timezone = ?, lunch_time = ?, dinner_time = ?, location_text = ?,
                    config_version = config_version + 1, updated_at = ?
                WHERE chat_id = ? AND automation_type = ? AND enabled = 1
                """,
                (
                    timezone,
                    lunch_time,
                    dinner_time,
                    location_text,
                    _utc_now(),
                    chat_id,
                    _TYPE_ID,
                ),
            )
        if cursor.rowcount != 1:
            raise ValueError("automation is not enabled")
        config = self.get_config(chat_id=chat_id)
        assert config is not None
        return config

    def set_paused(self, *, chat_id: str, paused: bool) -> bool:
        return self._set_flag(chat_id=chat_id, column="paused", value=paused)

    def disable_group(self, *, chat_id: str) -> bool:
        now = _utc_now()
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE automation_group_configs
                SET enabled = 0, paused = 0, config_version = config_version + 1,
                    updated_at = ?
                WHERE chat_id = ? AND automation_type = ?
                """,
                (now, chat_id, _TYPE_ID),
            )
            connection.execute(
                """
                DELETE FROM automation_subscriptions
                WHERE chat_id = ? AND automation_type = ?
                """,
                (chat_id, _TYPE_ID),
            )
        return cursor.rowcount == 1

    def subscribe(
        self,
        *,
        chat_id: str,
        member_user_id: str,
        preferences: SubscriptionPreferences | None = None,
    ) -> bool:
        preferences = preferences or SubscriptionPreferences()
        now = _utc_now()
        with self.database.transaction() as connection:
            config = connection.execute(
                """
                SELECT enabled FROM automation_group_configs
                WHERE chat_id = ? AND automation_type = ?
                """,
                (chat_id, _TYPE_ID),
            ).fetchone()
            if config is None or not bool(config["enabled"]):
                raise ValueError("automation is not enabled")
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO automation_subscriptions (
                    chat_id, automation_type, member_user_id, active,
                    cuisine_tags_json, budget_band, dietary_tags_json,
                    avoid_items_json, created_at, updated_at
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    _TYPE_ID,
                    member_user_id,
                    _json_array(preferences.cuisine_tags),
                    preferences.budget_band,
                    _json_array(preferences.dietary_tags),
                    _json_array(preferences.avoid_items),
                    now,
                    now,
                ),
            )
        return cursor.rowcount == 1

    def unsubscribe(self, *, chat_id: str, member_user_id: str) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                DELETE FROM automation_subscriptions
                WHERE chat_id = ? AND automation_type = ? AND member_user_id = ?
                """,
                (chat_id, _TYPE_ID, member_user_id),
            )
        return cursor.rowcount == 1

    def set_preferences(
        self,
        *,
        chat_id: str,
        member_user_id: str,
        preferences: SubscriptionPreferences,
    ) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE automation_subscriptions
                SET cuisine_tags_json = ?, budget_band = ?, dietary_tags_json = ?,
                    avoid_items_json = ?, updated_at = ?
                WHERE chat_id = ? AND automation_type = ? AND member_user_id = ?
                  AND active = 1
                """,
                (
                    _json_array(preferences.cuisine_tags),
                    preferences.budget_band,
                    _json_array(preferences.dietary_tags),
                    _json_array(preferences.avoid_items),
                    _utc_now(),
                    chat_id,
                    _TYPE_ID,
                    member_user_id,
                ),
            )
        return cursor.rowcount == 1

    def is_subscribed(self, *, chat_id: str, member_user_id: str) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM automation_subscriptions
                WHERE chat_id = ? AND automation_type = ? AND member_user_id = ?
                  AND active = 1
                """,
                (chat_id, _TYPE_ID, member_user_id),
            ).fetchone()
        return row is not None

    def aggregate_preferences(self, *, chat_id: str) -> AggregatedPreferences:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT cuisine_tags_json, budget_band, dietary_tags_json, avoid_items_json
                FROM automation_subscriptions
                WHERE chat_id = ? AND automation_type = ? AND active = 1
                ORDER BY member_user_id
                """,
                (chat_id, _TYPE_ID),
            ).fetchall()
        counts: dict[str, int] = {}
        for row in rows:
            values = (
                *_parse_array(row["cuisine_tags_json"]),
                *((row["budget_band"],) if row["budget_band"] else ()),
                *_parse_array(row["dietary_tags_json"]),
                *_parse_array(row["avoid_items_json"]),
            )
            for value in values:
                counts[value] = counts.get(value, 0) + 1
        summary = tuple(
            f"{key}:{count}"
            for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:16]
        )
        return AggregatedPreferences(subscriber_count=len(rows), summary=summary)

    def create_occurrence(
        self,
        *,
        bot_user_id: str,
        config: GroupAutomationConfig,
        local_date: date,
        slot: MealSlot,
        persona: PersonaSnapshot,
    ) -> AutomationOccurrence | None:
        scheduled_for = scheduled_instant(
            local_date=local_date,
            slot=slot,
            timezone=config.timezone,
            lunch_time=config.lunch_time,
            dinner_time=config.dinner_time,
        )
        if scheduled_for is None:
            return None
        occurrence_id, occurrence_key = occurrence_identity(
            bot_user_id=bot_user_id,
            chat_id=config.chat_id,
            local_date=local_date,
            slot=slot,
        )
        now = _utc_now()
        with self.database.transaction() as connection:
            active = connection.execute(
                """
                SELECT config_version
                FROM automation_group_configs
                WHERE chat_id = ? AND automation_type = ?
                """,
                (config.chat_id, config.automation_type),
            ).fetchone()
            # BEGIN IMMEDIATE makes this comparison and the due-row refresh one
            # serialized operation. A scheduler holding an older snapshot must not
            # create, return or lease work for a newer active configuration.
            if active is None or int(active["config_version"]) != config.config_version:
                return None
            connection.execute(
                """
                INSERT OR IGNORE INTO automation_occurrences (
                    occurrence_id, occurrence_key, chat_id, automation_type,
                    local_date, slot, scheduled_for, grace_deadline, config_version,
                    persona_id, persona_version, persona_digest, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    occurrence_id,
                    occurrence_key,
                    config.chat_id,
                    config.automation_type,
                    local_date.isoformat(),
                    slot.value,
                    scheduled_for.isoformat(),
                    (scheduled_for + _GRACE).isoformat(),
                    config.config_version,
                    persona.persona_id,
                    persona.persona_version,
                    persona.persona_digest,
                    now,
                    now,
                ),
            )
            # The stable occurrence key intentionally survives a schedule edit. Until a
            # worker has leased the send right, refresh that row to the active schedule
            # snapshot instead of letting an obsolete unleased row poison the new slot.
            # Claimed states are immutable and therefore excluded by status='due'; the
            # active-version check above prevents stale snapshots from reverting it.
            connection.execute(
                """
                UPDATE automation_occurrences
                SET scheduled_for = ?, grace_deadline = ?, config_version = ?,
                    persona_id = ?, persona_version = ?, persona_digest = ?,
                    reason_code = NULL, updated_at = ?
                WHERE occurrence_id = ? AND status = 'due'
                """,
                (
                    scheduled_for.isoformat(),
                    (scheduled_for + _GRACE).isoformat(),
                    config.config_version,
                    persona.persona_id,
                    persona.persona_version,
                    persona.persona_digest,
                    now,
                    occurrence_id,
                ),
            )
        return self.get_occurrence(occurrence_id=occurrence_id)

    def get_occurrence(self, *, occurrence_id: str) -> AutomationOccurrence | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM automation_occurrences WHERE occurrence_id = ?",
                (occurrence_id,),
            ).fetchone()
        return _occurrence_from_row(row) if row is not None else None

    def lease(
        self, *, occurrence_id: str, worker_id: str, now: datetime
    ) -> AutomationOccurrence | None:
        _require_aware(now)
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE automation_occurrences
                SET status = 'leased', lease_owner = ?, lease_expires_at = ?, updated_at = ?
                WHERE occurrence_id = ?
                  AND (
                    status = 'due'
                    OR (status = 'leased' AND lease_expires_at < ?)
                  )
                """,
                (
                    worker_id,
                    (now + _LEASE).isoformat(),
                    now.isoformat(),
                    occurrence_id,
                    now.isoformat(),
                ),
            )
        if cursor.rowcount != 1:
            return None
        return self.get_occurrence(occurrence_id=occurrence_id)

    def prepare(
        self,
        *,
        occurrence_id: str,
        worker_id: str,
        effect_request_id: str,
        primary_key: str,
        payload: dict[str, object],
        text: str,
    ) -> bool:
        if not primary_key or not text or len(text) > 4_096:
            raise ValueError("invalid prepared recommendation")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode()) > 16_384:
            raise ValueError("prepared payload is too large")
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE automation_occurrences
                SET status = 'prepared', effect_request_id = ?,
                    prepared_primary_key = ?, prepared_payload_json = ?,
                    prepared_text = ?, lease_owner = NULL, lease_expires_at = NULL,
                    updated_at = ?
                WHERE occurrence_id = ? AND status = 'leased' AND lease_owner = ?
                """,
                (
                    effect_request_id,
                    primary_key,
                    encoded,
                    text,
                    _utc_now(),
                    occurrence_id,
                    worker_id,
                ),
            )
        return cursor.rowcount == 1

    def recent_primary_keys(self, *, chat_id: str, limit: int = 5) -> tuple[str, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT prepared_primary_key FROM automation_occurrences
                WHERE chat_id = ? AND automation_type = ? AND status = 'sent'
                  AND prepared_primary_key IS NOT NULL
                ORDER BY scheduled_for DESC LIMIT ?
                """,
                (chat_id, _TYPE_ID, limit),
            ).fetchall()
        return tuple(str(row["prepared_primary_key"]) for row in rows)

    def mark_occurrence(
        self,
        *,
        occurrence_id: str,
        status: OccurrenceStatus,
        reason_code: str,
    ) -> bool:
        if status in {OccurrenceStatus.DUE, OccurrenceStatus.LEASED}:
            raise ValueError("occurrence outcome must be terminal or prepared")
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE automation_occurrences
                SET status = ?, reason_code = ?, lease_owner = NULL,
                    lease_expires_at = NULL, updated_at = ?
                WHERE occurrence_id = ?
                  AND status NOT IN ('sent', 'uncertain', 'definite_failure')
                """,
                (status.value, reason_code, _utc_now(), occurrence_id),
            )
        return cursor.rowcount == 1

    def record_action(
        self,
        *,
        chat_id: str,
        actor_user_id: str,
        actor_role: str,
        action_kind: str,
        result_kind: str,
        reason_code: str,
        config_version: int | None = None,
        at: datetime | None = None,
    ) -> int:
        current = at or datetime.now(UTC)
        _require_aware(current)
        purge_after = current + timedelta(days=30)
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO automation_action_audit (
                    chat_id, automation_type, actor_user_id, actor_role,
                    action_kind, result_kind, reason_code, config_version,
                    created_at, purge_after
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    _TYPE_ID,
                    actor_user_id,
                    actor_role,
                    action_kind,
                    result_kind,
                    reason_code,
                    config_version,
                    current.isoformat(),
                    purge_after.isoformat(),
                ),
            )
        if cursor.lastrowid is None:
            raise sqlite3.DatabaseError("automation audit insert produced no row")
        return int(cursor.lastrowid)

    def scheduled_source(self, *, occurrence: AutomationOccurrence) -> ScheduledOccurrenceSource:
        config = self.get_config(chat_id=occurrence.chat_id)
        if config is None:
            raise ValueError("automation config is unavailable")
        aggregate = self.aggregate_preferences(chat_id=occurrence.chat_id)
        return ScheduledOccurrenceSource(
            occurrence_id=occurrence.occurrence_id,
            occurrence_key=occurrence.occurrence_key,
            chat_id=occurrence.chat_id,
            automation_type=occurrence.automation_type,
            local_date=occurrence.local_date,
            meal_slot=occurrence.slot.value,
            scheduled_for=occurrence.scheduled_for,
            timezone=config.timezone,
            config_version=occurrence.config_version,
            subscriber_count=aggregate.subscriber_count,
            preference_summary=aggregate.summary,
            location_text=config.location_text,
            recent_primary_keys=self.recent_primary_keys(chat_id=occurrence.chat_id),
        )

    def _set_flag(self, *, chat_id: str, column: str, value: bool) -> bool:
        if column != "paused":
            raise ValueError("unsupported automation flag")
        with self.database.transaction() as connection:
            cursor = connection.execute(
                f"""
                UPDATE automation_group_configs
                SET {column} = ?, config_version = config_version + 1, updated_at = ?
                WHERE chat_id = ? AND automation_type = ? AND enabled = 1
                """,
                (int(value), _utc_now(), chat_id, _TYPE_ID),
            )
        return cursor.rowcount == 1


def _config_from_row(row: sqlite3.Row) -> GroupAutomationConfig:
    return GroupAutomationConfig(
        chat_id=str(row["chat_id"]),
        automation_type=str(row["automation_type"]),
        enabled=bool(row["enabled"]),
        paused=bool(row["paused"]),
        timezone=str(row["timezone"]),
        lunch_time=str(row["lunch_time"]),
        dinner_time=str(row["dinner_time"]),
        location_text=str(row["location_text"]) if row["location_text"] is not None else None,
        config_version=int(row["config_version"]),
    )


def _occurrence_from_row(row: sqlite3.Row) -> AutomationOccurrence:
    return AutomationOccurrence(
        occurrence_id=str(row["occurrence_id"]),
        occurrence_key=str(row["occurrence_key"]),
        chat_id=str(row["chat_id"]),
        automation_type=str(row["automation_type"]),
        local_date=str(row["local_date"]),
        slot=MealSlot(str(row["slot"])),
        scheduled_for=datetime.fromisoformat(str(row["scheduled_for"])),
        grace_deadline=datetime.fromisoformat(str(row["grace_deadline"])),
        config_version=int(row["config_version"]),
        persona=PersonaSnapshot(
            persona_id=str(row["persona_id"]),
            persona_version=str(row["persona_version"]),
            persona_digest=str(row["persona_digest"]),
        ),
        status=OccurrenceStatus(str(row["status"])),
        prepared_primary_key=(
            str(row["prepared_primary_key"]) if row["prepared_primary_key"] is not None else None
        ),
        prepared_text=str(row["prepared_text"]) if row["prepared_text"] is not None else None,
        reason_code=str(row["reason_code"]) if row["reason_code"] is not None else None,
    )


def _validate_preference_values(preferences: SubscriptionPreferences) -> None:
    if len(preferences.cuisine_tags) > 5 or not set(preferences.cuisine_tags) <= _CUISINES:
        raise ValueError("invalid cuisine preferences")
    if preferences.budget_band is not None and preferences.budget_band not in _BUDGET_BANDS:
        raise ValueError("invalid budget preference")
    if len(preferences.dietary_tags) > 4 or not set(preferences.dietary_tags) <= _DIETARY_TAGS:
        raise ValueError("invalid dietary preferences")
    if len(preferences.avoid_items) > 5:
        raise ValueError("too many avoid items")
    for item in preferences.avoid_items:
        if not _SAFE_TOKEN.fullmatch(item) or _SENSITIVE_REASON.search(item):
            raise ValueError("invalid avoid item")


def _json_array(values: tuple[str, ...]) -> str:
    return json.dumps(sorted(set(values)), ensure_ascii=False, separators=(",", ":"))


def _parse_array(value: object) -> tuple[str, ...]:
    parsed = json.loads(str(value))
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("invalid stored preference")
    return tuple(parsed)


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
