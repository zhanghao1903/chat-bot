from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from group_llm_agent.events import PersonaSnapshot, TelegramTextMessage, TriggerPath
from group_llm_agent.memory import MemberMemoryItem, MemoryRepository
from group_llm_agent.messages import MessageRepository, StoredGroupMessage
from group_llm_agent.persona import CharacterBundle, CompiledCharacterView
from group_llm_agent.vision import VisionEvidence


@dataclass(frozen=True)
class MemberMemoryContext:
    member_user_id: str
    items: tuple[MemberMemoryItem, ...]


@dataclass(frozen=True)
class TriggerContext:
    persona: PersonaSnapshot
    character: CompiledCharacterView
    current_message: TelegramTextMessage
    recent_scene: tuple[StoredGroupMessage, ...]
    member_memory: tuple[MemberMemoryContext, ...]
    hard_gate_reason: str
    continuity_anchor: StoredGroupMessage | None = None


@dataclass(frozen=True)
class EffectContext:
    persona: PersonaSnapshot
    character: CompiledCharacterView
    current_message: TelegramTextMessage
    recent_scene: tuple[StoredGroupMessage, ...]
    member_memory: tuple[MemberMemoryContext, ...]
    trigger_path: TriggerPath
    model_calls_remaining: int
    tool_calls_remaining: int
    deadline_at: datetime
    vision_evidence: VisionEvidence | None = None
    vision_error_code: str | None = None

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, (self.deadline_at - datetime.now(UTC)).total_seconds())


class ContextAssembler:
    def __init__(
        self,
        *,
        messages: MessageRepository,
        memory: MemoryRepository,
        recognition_policy_version: str,
    ) -> None:
        if not recognition_policy_version:
            raise ValueError("recognition_policy_version must not be empty")
        self.messages = messages
        self.memory = memory
        self.recognition_policy_version = recognition_policy_version

    def trigger_context(
        self,
        *,
        bundle: CharacterBundle,
        message: TelegramTextMessage,
        hard_gate_reason: str,
        continuity_anchor_message_id: str | None = None,
        at: datetime | None = None,
    ) -> TriggerContext:
        recent_scene = self.messages.recent(chat_id=message.group_id, limit=20)
        continuity_anchor = next(
            (
                item
                for item in recent_scene
                if item.telegram_message_id == continuity_anchor_message_id
                and item.direction == "outbound"
            ),
            None,
        )
        return TriggerContext(
            persona=bundle.snapshot,
            character=bundle.views.trigger,
            current_message=message,
            recent_scene=recent_scene,
            member_memory=self._member_context(
                message=message,
                persona=bundle.snapshot,
                at=at,
            ),
            hard_gate_reason=hard_gate_reason,
            continuity_anchor=continuity_anchor,
        )

    def effect_context(
        self,
        *,
        bundle: CharacterBundle,
        message: TelegramTextMessage,
        trigger_path: TriggerPath,
        model_calls_remaining: int,
        tool_calls_remaining: int,
        deadline_at: datetime,
        vision_evidence: VisionEvidence | None = None,
        vision_error_code: str | None = None,
        at: datetime | None = None,
    ) -> EffectContext:
        if not 1 <= model_calls_remaining <= 6:
            raise ValueError("model_calls_remaining must be in [1, 6]")
        if not 0 <= tool_calls_remaining <= 5:
            raise ValueError("tool_calls_remaining must be in [0, 5]")
        if deadline_at.tzinfo is None:
            raise ValueError("deadline_at must be timezone-aware")
        return EffectContext(
            persona=bundle.snapshot,
            character=bundle.views.effector,
            current_message=message,
            recent_scene=self.messages.recent(chat_id=message.group_id, limit=20),
            member_memory=self._member_context(
                message=message,
                persona=bundle.snapshot,
                at=at,
            ),
            trigger_path=trigger_path,
            model_calls_remaining=model_calls_remaining,
            tool_calls_remaining=tool_calls_remaining,
            deadline_at=deadline_at,
            vision_evidence=vision_evidence,
            vision_error_code=vision_error_code,
        )

    def _member_context(
        self,
        *,
        message: TelegramTextMessage,
        persona: PersonaSnapshot,
        at: datetime | None,
    ) -> tuple[MemberMemoryContext, ...]:
        member_ids = _scene_member_ids(message)
        return tuple(
            MemberMemoryContext(
                member_user_id=member_id,
                items=self.memory.list_active(
                    chat_id=message.group_id,
                    member_user_id=member_id,
                    persona=persona,
                    recognition_policy_version=self.recognition_policy_version,
                    at=at,
                    limit=8,
                ),
            )
            for member_id in member_ids
        )


def _scene_member_ids(message: TelegramTextMessage) -> tuple[str, ...]:
    candidates = (
        message.sender_id,
        message.replied_to_user_id,
        *message.mentioned_user_ids[:2],
    )
    result: list[str] = []
    for candidate in candidates:
        if candidate is not None and candidate not in result:
            result.append(candidate)
    return tuple(result)
