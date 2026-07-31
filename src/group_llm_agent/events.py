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


class TriggerCategory(StrEnum):
    DIRECT_PLATFORM = "direct_platform"
    DIRECT_PERSONA_NAME = "direct_persona_name"
    CONVERSATION_CONTINUITY = "conversation_continuity"
    ORDINARY_CONTEXTUAL = "ordinary_contextual"
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
    SILENCE = "silence"
    FAILURE_REPLY = "failure_reply"


class ExternalEffectKind(StrEnum):
    REPLY = "reply"
    FAILURE_REPLY = "failure_reply"
    CONTROL_ACK = "control_ack"


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


@dataclass(frozen=True)
class TelegramTextMessage:
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


@dataclass(frozen=True)
class PersonaSnapshot:
    persona_id: str
    persona_version: str
    persona_digest: str


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
    message: TelegramTextMessage
    persona: PersonaSnapshot
    deadline_at: datetime


@dataclass(frozen=True)
class FinalEffect:
    kind: FinalEffectKind
    reason_code: str
    persona: PersonaSnapshot
    text: str | None = None
    used_memory_ids: tuple[str, ...] = ()
    used_tool_call_ids: tuple[int, ...] = ()
