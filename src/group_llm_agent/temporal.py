from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TEMPORAL_CONTEXT_VERSION = "lezhi-temporal-v1"
DEFAULT_GROUP_TIMEZONE = "Asia/Shanghai"
SELECT_ANSWER_TIMEZONE = "select_answer_timezone"
_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

Clock = Callable[[], datetime]


class TemporalContextError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"temporal_context_error code={code}")


class TimezoneSelection(StrEnum):
    GROUP_DEFAULT = "group_default"
    WRITER_EXPLICIT_OVERRIDE = "writer_explicit_override"


class FreshnessMode(StrEnum):
    STABLE = "stable"
    CLOCK = "clock"
    CURRENT_VERIFIED = "current_verified"
    CURRENT_UNVERIFIED = "current_unverified"


@dataclass(frozen=True)
class TemporalContext:
    version: str
    context_id: str
    captured_at_utc: datetime
    current_utc: datetime
    current_local: datetime
    answer_timezone: str
    utc_offset: str
    local_date: str
    local_weekday_number: int
    local_weekday_name: str
    source_class: str
    group_timezone: str
    timezone_selection: TimezoneSelection

    def as_prompt_data(self) -> dict[str, object]:
        return {
            "version": self.version,
            "context_id": self.context_id,
            "captured_at_utc": _rfc3339(self.captured_at_utc),
            "current_utc": _rfc3339(self.current_utc),
            "current_local": _rfc3339(self.current_local),
            "answer_timezone": self.answer_timezone,
            "utc_offset": self.utc_offset,
            "local_date": self.local_date,
            "local_weekday": {
                "iso_number": self.local_weekday_number,
                "name": self.local_weekday_name,
            },
            "source_class": self.source_class,
            "group_timezone": self.group_timezone,
            "timezone_selection": self.timezone_selection.value,
        }

    def occurrence_data(self, value: datetime) -> dict[str, str]:
        instant = _aware_utc(value, code="invalid_message_timestamp")
        try:
            local = instant.astimezone(ZoneInfo(self.answer_timezone))
        except (OverflowError, ValueError, ZoneInfoNotFoundError):
            raise TemporalContextError("message_timestamp_conversion_failed") from None
        return {
            "occurred_at_utc": _rfc3339(instant),
            "occurred_at_target_local": _rfc3339(local),
            "occurred_timezone": self.answer_timezone,
            "telegram_precision": "second",
        }


class GroupTimezoneReader(Protocol):
    def get_config(self, *, chat_id: str) -> object | None: ...


class GroupTimezoneProvider(Protocol):
    def timezone_for(self, *, chat_id: str) -> str: ...


class TemporalWebEvidence(Protocol):
    result_id: str
    normalized_url: str
    retrieved_at: datetime
    search_audit_id: int
    fetch_audit_id: int | None


@dataclass(frozen=True)
class FinalizedTemporalText:
    text: str
    source_urls: tuple[str, ...]
    source_audit_ids: tuple[int, ...]
    latest_retrieved_at: datetime | None


class StaticGroupTimezoneProvider:
    """Deterministic fallback for tests and callers without automation composition."""

    def __init__(self, timezone: str = DEFAULT_GROUP_TIMEZONE) -> None:
        self.timezone = validate_iana_timezone(timezone)

    def timezone_for(self, *, chat_id: str) -> str:
        if not chat_id:
            raise TemporalContextError("invalid_chat_scope")
        return self.timezone


class AutomationGroupTimezoneProvider:
    """Read the existing automation config without creating a second timezone source."""

    def __init__(
        self,
        reader: GroupTimezoneReader,
        *,
        default_timezone: str = DEFAULT_GROUP_TIMEZONE,
    ) -> None:
        self.reader = reader
        self.default_timezone = validate_iana_timezone(default_timezone)

    def timezone_for(self, *, chat_id: str) -> str:
        if not chat_id:
            raise TemporalContextError("invalid_chat_scope")
        config = self.reader.get_config(chat_id=chat_id)
        if config is None:
            return self.default_timezone
        value = getattr(config, "timezone", None)
        if not isinstance(value, str):
            raise TemporalContextError("invalid_group_timezone")
        try:
            return validate_iana_timezone(value)
        except TemporalContextError:
            raise TemporalContextError("invalid_group_timezone") from None


class TemporalContextFactory:
    def __init__(self, *, clock: Clock | None = None) -> None:
        self.clock = clock or system_clock

    def sample(
        self,
        *,
        group_timezone: str,
        answer_timezone: str | None = None,
        selection: TimezoneSelection = TimezoneSelection.GROUP_DEFAULT,
    ) -> TemporalContext:
        group_zone = validate_iana_timezone(group_timezone)
        target_zone = validate_iana_timezone(answer_timezone or group_zone)
        try:
            sampled = self.clock()
        except Exception:  # noqa: BLE001 - clock failures become a safe typed boundary
            raise TemporalContextError("clock_unavailable") from None
        current_utc = _aware_utc(sampled, code="invalid_clock")
        try:
            zone = ZoneInfo(target_zone)
            current_local = current_utc.astimezone(zone)
            round_trip = current_local.astimezone(UTC)
        except (OverflowError, ValueError, ZoneInfoNotFoundError):
            raise TemporalContextError("timezone_conversion_failed") from None
        if round_trip != current_utc:
            raise TemporalContextError("inconsistent_timezone_conversion")
        offset = current_local.utcoffset()
        if offset is None:
            raise TemporalContextError("missing_utc_offset")
        offset_text = _offset_text(offset)
        local_date = current_local.date().isoformat()
        weekday_number = current_local.isoweekday()
        weekday_name = _WEEKDAYS[weekday_number - 1]
        captured = current_utc
        identity = _context_id(
            captured_at_utc=captured,
            answer_timezone=target_zone,
            utc_offset=offset_text,
            selection=selection,
        )
        context = TemporalContext(
            version=TEMPORAL_CONTEXT_VERSION,
            context_id=identity,
            captured_at_utc=captured,
            current_utc=current_utc,
            current_local=current_local,
            answer_timezone=target_zone,
            utc_offset=offset_text,
            local_date=local_date,
            local_weekday_number=weekday_number,
            local_weekday_name=weekday_name,
            source_class="system_clock",
            group_timezone=group_zone,
            timezone_selection=selection,
        )
        _validate_context(context)
        return context


class TemporalSession:
    def __init__(
        self,
        *,
        group_timezone: str,
        factory: TemporalContextFactory,
        scope_id: str = "unscoped",
    ) -> None:
        self.group_timezone = validate_iana_timezone(group_timezone)
        if not isinstance(scope_id, str) or not scope_id or len(scope_id) > 128:
            raise TemporalContextError("invalid_temporal_scope")
        self.factory = factory
        self.scope_id = scope_id
        self._answer_timezone = self.group_timezone
        self._selection = TimezoneSelection.GROUP_DEFAULT
        self._selection_used = False
        self._model_call_ordinal = 0

    @property
    def answer_timezone(self) -> str:
        return self._answer_timezone

    @property
    def selection_available(self) -> bool:
        return not self._selection_used

    @property
    def model_call_ordinal(self) -> int:
        return self._model_call_ordinal

    def select_answer_timezone(self, timezone: str) -> None:
        if self._selection_used:
            raise TemporalContextError("timezone_selection_already_used")
        selected = validate_iana_timezone(timezone)
        self._answer_timezone = selected
        self._selection = TimezoneSelection.WRITER_EXPLICIT_OVERRIDE
        self._selection_used = True

    def sample_for_model_call(self) -> TemporalContext:
        self._model_call_ordinal += 1
        context = self.factory.sample(
            group_timezone=self.group_timezone,
            answer_timezone=self._answer_timezone,
            selection=self._selection,
        )
        return replace(
            context,
            context_id=_bound_context_id(
                base_context_id=context.context_id,
                scope_id=self.scope_id,
                model_call_ordinal=self._model_call_ordinal,
            ),
        )


def system_clock() -> datetime:
    return datetime.now(UTC)


def validate_iana_timezone(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 64
        or value.startswith(("+", "-"))
        or any(ord(character) < 33 for character in value)
    ):
        raise TemporalContextError("invalid_iana_timezone")
    try:
        zone = ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise TemporalContextError("invalid_iana_timezone") from None
    if not getattr(zone, "key", None):
        raise TemporalContextError("invalid_iana_timezone")
    return value


def finalize_temporal_text(
    *,
    text: str,
    context: TemporalContext,
    freshness_mode: FreshnessMode,
    evidence: tuple[TemporalWebEvidence, ...] = (),
    maximum_length: int = 4_096,
) -> FinalizedTemporalText:
    if not text.strip() or len(text) > maximum_length:
        raise TemporalContextError("invalid_temporal_answer_text")
    if freshness_mode in {FreshnessMode.STABLE, FreshnessMode.CLOCK}:
        if evidence:
            raise TemporalContextError("freshness_sources_invalid")
        return FinalizedTemporalText(
            text=text, source_urls=(), source_audit_ids=(), latest_retrieved_at=None
        )
    if freshness_mode is FreshnessMode.CURRENT_UNVERIFIED:
        rendered = f"当前状态尚未可靠核实。\n{text}"
        if len(rendered) > maximum_length:
            raise TemporalContextError("temporal_answer_too_long")
        return FinalizedTemporalText(
            text=rendered,
            source_urls=(),
            source_audit_ids=(),
            latest_retrieved_at=None,
        )
    if not 1 <= len(evidence) <= 3:
        raise TemporalContextError("freshness_sources_invalid")
    result_ids = tuple(item.result_id for item in evidence)
    urls = tuple(item.normalized_url for item in evidence)
    if len(set(result_ids)) != len(result_ids) or len(set(urls)) != len(urls):
        raise TemporalContextError("freshness_sources_invalid")
    retrievals = tuple(
        _aware_utc(item.retrieved_at, code="invalid_web_retrieval_time") for item in evidence
    )
    latest = max(retrievals)
    try:
        local = latest.astimezone(ZoneInfo(context.answer_timezone))
    except (OverflowError, ValueError, ZoneInfoNotFoundError):
        raise TemporalContextError("web_retrieval_time_conversion_failed") from None
    footer = (
        f"截至 {local.strftime('%Y-%m-%d %H:%M')}（{context.answer_timezone}）\n"
        + "来源："
        + " · ".join(urls)
    )
    rendered = f"{text}\n{footer}"
    if len(rendered) > maximum_length:
        raise TemporalContextError("temporal_answer_too_long")
    audit_ids = sorted(
        {
            audit_id
            for item in evidence
            for audit_id in (item.search_audit_id, item.fetch_audit_id)
            if audit_id is not None
        }
    )
    return FinalizedTemporalText(
        text=rendered,
        source_urls=urls,
        source_audit_ids=tuple(audit_ids),
        latest_retrieved_at=latest,
    )


def _aware_utc(value: datetime, *, code: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise TemporalContextError(code)
    try:
        return value.astimezone(UTC)
    except (OverflowError, ValueError):
        raise TemporalContextError(code) from None


def _offset_text(value: timedelta) -> str:
    total_seconds = int(value.total_seconds())
    if total_seconds % 60 or abs(total_seconds) > 24 * 60 * 60:
        raise TemporalContextError("invalid_utc_offset")
    sign = "+" if total_seconds >= 0 else "-"
    minutes = abs(total_seconds) // 60
    hours, remainder = divmod(minutes, 60)
    return f"{sign}{hours:02d}:{remainder:02d}"


def _rfc3339(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TemporalContextError("naive_datetime")
    return value.isoformat(timespec="seconds")


def _context_id(
    *,
    captured_at_utc: datetime,
    answer_timezone: str,
    utc_offset: str,
    selection: TimezoneSelection,
) -> str:
    canonical = json.dumps(
        {
            "version": TEMPORAL_CONTEXT_VERSION,
            "captured_at_utc": _rfc3339(captured_at_utc),
            "answer_timezone": answer_timezone,
            "utc_offset": utc_offset,
            "timezone_selection": selection.value,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "time:v1:" + hashlib.sha256(canonical.encode()).hexdigest()


def _bound_context_id(
    *,
    base_context_id: str,
    scope_id: str,
    model_call_ordinal: int,
) -> str:
    canonical = json.dumps(
        {
            "base_context_id": base_context_id,
            "scope_id": scope_id,
            "model_call_ordinal": model_call_ordinal,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "time:v1:" + hashlib.sha256(canonical.encode()).hexdigest()


def _validate_context(context: TemporalContext) -> None:
    if context.version != TEMPORAL_CONTEXT_VERSION:
        raise TemporalContextError("invalid_context_version")
    if context.current_utc != context.captured_at_utc:
        raise TemporalContextError("inconsistent_capture_time")
    if context.current_local.astimezone(UTC) != context.current_utc:
        raise TemporalContextError("inconsistent_timezone_conversion")
    if context.utc_offset != _offset_text(context.current_local.utcoffset() or timedelta()):
        raise TemporalContextError("inconsistent_utc_offset")
    if context.local_date != context.current_local.date().isoformat():
        raise TemporalContextError("inconsistent_local_date")
    if context.local_weekday_number != context.current_local.isoweekday():
        raise TemporalContextError("inconsistent_weekday")
    if context.local_weekday_name != _WEEKDAYS[context.local_weekday_number - 1]:
        raise TemporalContextError("inconsistent_weekday")
