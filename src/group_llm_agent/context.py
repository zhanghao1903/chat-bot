from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from group_llm_agent.events import PersonaSnapshot, TelegramTextMessage, TriggerPath
from group_llm_agent.memory import MemberMemoryItem, MemoryRepository
from group_llm_agent.messages import MessageRepository, StoredGroupMessage
from group_llm_agent.persona import CharacterBundle, CompiledCharacterView


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
        at: datetime | None = None,
    ) -> TriggerContext:
        return TriggerContext(
            persona=bundle.snapshot,
            character=bundle.views.trigger,
            current_message=message,
            recent_scene=self.messages.recent(chat_id=message.group_id, limit=20),
            member_memory=self._member_context(
                message=message,
                persona=bundle.snapshot,
                at=at,
            ),
            hard_gate_reason=hard_gate_reason,
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
        at: datetime | None = None,
    ) -> EffectContext:
        if not 1 <= model_calls_remaining <= 3:
            raise ValueError("model_calls_remaining must be in [1, 3]")
        if not 0 <= tool_calls_remaining <= 2:
            raise ValueError("tool_calls_remaining must be in [0, 2]")
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
