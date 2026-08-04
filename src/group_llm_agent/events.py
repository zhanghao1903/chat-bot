from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class PlatformTriggerKind(StrEnum):
    IGNORE = "ignore"
    CONTROL = "control"
    DIRECT = "direct"
    CONTINUITY_CANDIDATE = "continuity_candidate"
    CONTEXTUAL_CANDIDATE = "contextual_candidate"


class PersonaTriggerKind(StrEnum):
    ENGAGE = "engage"
    SILENCE = "silence"


class TriggerPath(StrEnum):
    DIRECT = "direct"
    CONTEXTUAL = "contextual"
    SCHEDULED = "scheduled"


class TriggerCategory(StrEnum):
    DIRECT_PLATFORM = "direct_platform"
    DIRECT_PERSONA_NAME = "direct_persona_name"
    CONVERSATION_CONTINUITY = "conversation_continuity"
    ORDINARY_CONTEXTUAL = "ordinary_contextual"
    SCHEDULED_AUTOMATION = "scheduled_automation"
    CONTROL = "control"
    IGNORED = "ignored"


class ContinuityDecisionKind(StrEnum):
    CONTINUE = "continue"
    CLOSE = "close"
    NOT_ADDRESSED = "not_addressed"
    AMBIGUOUS = "ambiguous"


class TriggerEvaluationDecisionKind(StrEnum):
    EFFECT_REQUESTED = "effect_requested"
    SILENCE = "silence"
    IGNORED = "ignored"
    CONTROL = "control"


class FinalEffectKind(StrEnum):
    REPLY = "reply"
    STICKER = "sticker"
    SILENCE = "silence"
    FAILURE_REPLY = "failure_reply"


class ExternalEffectKind(StrEnum):
    REPLY = "reply"
    STICKER = "sticker"
    FAILURE_REPLY = "failure_reply"
    CONTROL_ACK = "control_ack"


class MediaKind(StrEnum):
    PHOTO = "photo"
    STATIC_DOCUMENT = "static_document"
    STATIC_STICKER = "static_sticker"


class VisionStatus(StrEnum):
    NOT_CALLED = "not_called"
    COMPLETED = "completed"
    FAILED = "failed"


class MemoryCategory(StrEnum):
    FACT = "fact"
    OBSERVATION = "observation"
    IMPRESSION = "impression"
    SHARED_EXPERIENCE = "shared_experience"
    PREFERENCE = "preference"


class TriggerModelStatus(StrEnum):
    NOT_CALLED = "not_called"
    COMPLETED = "completed"
    FAILED = "failed"


class EffectRunStatus(StrEnum):
    PROCESSING = "processing"
    REPLY = "reply"
    STICKER = "sticker"
    SILENCE = "silence"
    FAILURE_REPLY = "failure_reply"
    FAILED = "failed"


class ExternalEffectStatus(StrEnum):
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


class ControlAuthorizationStatus(StrEnum):
    AUTHORIZED = "authorized"
    DENIED = "denied"
    UNAVAILABLE = "unavailable"


class ModelErrorCode(StrEnum):
    TIMEOUT = "timeout"
    AUTHENTICATION = "authentication"
    RATE_LIMITED = "rate_limited"
    INVALID_RESPONSE = "invalid_response"
    PROVIDER_ERROR = "provider_error"
    BUDGET_EXHAUSTED = "budget_exhausted"


class EffectSourceKind(StrEnum):
    INBOUND = "inbound"
    SCHEDULED = "scheduled"


@dataclass(frozen=True)
class InboundMedia:
    kind: MediaKind
    file_id: str
    file_unique_id: str
    mime_type: str | None = None
    file_size: int | None = None
    width: int | None = None
    height: int | None = None
    sticker_set_name: str | None = None
    is_animated: bool = False
    is_video: bool = False


@dataclass(frozen=True)
class TelegramMessage:
    event_id: str
    group_id: str
    message_id: str
    sender_id: str
    sender_display_name: str
    text: str
    timestamp: datetime
    mentioned_bot: bool = False
    replied_to_message_id: str | None = None
    replied_to_user_id: str | None = None
    mentioned_user_ids: tuple[str, ...] = ()
    is_bot_command: bool = False
    bot_command_target: str | None = None
    raw_event_ref: str | None = None
    media: InboundMedia | None = None


# Compatibility alias for callers written before media messages were supported.
TelegramTextMessage = TelegramMessage


@dataclass(frozen=True)
class PersonaSnapshot:
    persona_id: str
    persona_version: str
    persona_digest: str


@dataclass(frozen=True)
class ScheduledOccurrenceSource:
    occurrence_id: str
    occurrence_key: str
    chat_id: str
    automation_type: str
    local_date: str
    meal_slot: str
    scheduled_for: datetime
    timezone: str
    config_version: int
    subscriber_count: int
    preference_summary: tuple[str, ...] = ()
    location_text: str | None = None
    recent_primary_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.occurrence_id or not self.occurrence_key:
            raise ValueError("scheduled occurrence identity must not be empty")
        if not self.chat_id or not self.automation_type:
            raise ValueError("scheduled occurrence scope must not be empty")
        if self.scheduled_for.tzinfo is None:
            raise ValueError("scheduled_for must be timezone-aware")
        if self.config_version < 1:
            raise ValueError("config_version must be positive")
        if self.subscriber_count < 1:
            raise ValueError("subscriber_count must be positive")


@dataclass(frozen=True)
class PlatformTriggerDecision:
    kind: PlatformTriggerKind
    reason_code: str
    persona_name_hit: bool = False
    continuity_anchor_message_id: str | None = None


@dataclass(frozen=True)
class PersonaTriggerDecision:
    kind: PersonaTriggerKind
    reason_code: str
    persona: PersonaSnapshot
    model_status: TriggerModelStatus = TriggerModelStatus.COMPLETED


@dataclass(frozen=True)
class ConversationContinuityDecision:
    kind: ContinuityDecisionKind
    reason_code: str
    persona: PersonaSnapshot


@dataclass(frozen=True)
class EffectRequest:
    request_id: str
    trigger_path: TriggerPath
    trigger_category: TriggerCategory
    trigger_reason: str
    message: TelegramTextMessage | None
    persona: PersonaSnapshot
    deadline_at: datetime
    scheduled: ScheduledOccurrenceSource | None = None

    def __post_init__(self) -> None:
        if (self.message is None) == (self.scheduled is None):
            raise ValueError("effect request requires exactly one source")
        if self.deadline_at.tzinfo is None:
            raise ValueError("deadline_at must be timezone-aware")
        if self.message is None:
            if self.trigger_path is not TriggerPath.SCHEDULED:
                raise ValueError("scheduled source requires scheduled trigger path")
            if self.trigger_category is not TriggerCategory.SCHEDULED_AUTOMATION:
                raise ValueError("scheduled source requires scheduled trigger category")
        elif self.trigger_path is TriggerPath.SCHEDULED:
            raise ValueError("inbound source cannot use scheduled trigger path")

    @property
    def source_kind(self) -> EffectSourceKind:
        if self.scheduled is not None:
            return EffectSourceKind.SCHEDULED
        return EffectSourceKind.INBOUND

    @property
    def chat_id(self) -> str:
        if self.scheduled is not None:
            return self.scheduled.chat_id
        assert self.message is not None
        return self.message.group_id

    @property
    def trigger_event_id(self) -> str:
        if self.scheduled is not None:
            return self.scheduled.occurrence_id
        assert self.message is not None
        return self.message.event_id

    @property
    def trigger_message_id(self) -> str | None:
        if self.message is None:
            return None
        return self.message.message_id


@dataclass(frozen=True)
class FinalEffect:
    kind: FinalEffectKind
    reason_code: str
    persona: PersonaSnapshot
    text: str | None = None
    sticker_id: str | None = None
    catalog_version: str | None = None
    catalog_digest: str | None = None
    fallback_text: str | None = None
    mood_signal: str | None = None
    used_memory_ids: tuple[str, ...] = ()
    used_tool_call_ids: tuple[int, ...] = ()
    primary_key: str | None = None
    source_urls: tuple[str, ...] = ()
