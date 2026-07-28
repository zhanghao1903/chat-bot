from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from group_llm_agent.events import (
    ControlAuthorizationStatus,
    ExternalEffectKind,
    PersonaSnapshot,
    TelegramTextMessage,
)
from group_llm_agent.memory import MemoryRepository
from group_llm_agent.messages import MessageRepository
from group_llm_agent.platforms.telegram import (
    ChatMemberStatus,
    SentMessage,
    TelegramApiError,
)
from group_llm_agent.runs import RunRepository

MEMORY_DISCLOSURE = (
    "本群已启用有限的成员认识功能：机器人只使用本公开群中可见的消息，"
    "可能形成仅限本群、会影响后续互动且可修订的成员认识；近期原文最多保留 7 天，"
    "配置的模型服务会处理这些上下文。任何成员可使用 /memory_forget_me 清除自己的"
    "认识与留存原文；管理员可使用 /memory_disable 或群重置命令。"
)
_ENABLE_COMMAND = "/memory_enable"
_DISABLE_COMMAND = "/memory_disable"
_FORGET_ME_COMMAND = "/memory_forget_me"
_FORGET_MEMBER_COMMAND = "/memory_forget_member"
_FORGET_GROUP_COMMAND = "/memory_forget_group"
_ADMIN_COMMANDS = {
    _ENABLE_COMMAND,
    _DISABLE_COMMAND,
    _FORGET_MEMBER_COMMAND,
    _FORGET_GROUP_COMMAND,
}


class TelegramControlPort(Protocol):
    def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        reply_to_message_id: str | None = None,
    ) -> SentMessage: ...

    def get_chat_member(self, *, chat_id: str, user_id: str) -> ChatMemberStatus: ...


@dataclass(frozen=True)
class ControlOutcome:
    consumed: bool
    status: str
    platform_message_id: str | None = None
    reset_generation: int | None = None


class MemoryControlService:
    def __init__(
        self,
        *,
        allowed_chat_id: str,
        bot_user_id: str,
        telegram: TelegramControlPort,
        messages: MessageRepository,
        memory: MemoryRepository,
        runs: RunRepository,
    ) -> None:
        self.allowed_chat_id = allowed_chat_id
        self.bot_user_id = bot_user_id
        self.telegram = telegram
        self.messages = messages
        self.memory = memory
        self.runs = runs

    def handle(
        self,
        message: TelegramTextMessage,
        *,
        persona: PersonaSnapshot,
        now: datetime | None = None,
    ) -> ControlOutcome:
        command, argument = _parse_command(message.text)
        if command not in {
            _ENABLE_COMMAND,
            _DISABLE_COMMAND,
            _FORGET_ME_COMMAND,
            _FORGET_MEMBER_COMMAND,
            _FORGET_GROUP_COMMAND,
        }:
            return ControlOutcome(consumed=False, status="not_control")
        if message.group_id != self.allowed_chat_id or message.sender_id == self.bot_user_id:
            return ControlOutcome(consumed=True, status="ignored_scope")
        if command in _ADMIN_COMMANDS and not self._authorize_admin(message, command=command):
            return ControlOutcome(consumed=True, status="not_authorized")

        if command == _ENABLE_COMMAND:
            return self._enable(message, persona=persona)
        if command == _DISABLE_COMMAND:
            return self._disable(message, persona=persona)
        if command == _FORGET_ME_COMMAND:
            return self._forget_member(
                message,
                target_user_id=message.sender_id,
                command=command,
                persona=persona,
                now=now,
            )
        if command == _FORGET_MEMBER_COMMAND:
            target = message.replied_to_user_id
            if target is None or target == self.bot_user_id:
                self._audit(
                    message,
                    command=command,
                    target_user_id=target,
                    authorization=ControlAuthorizationStatus.AUTHORIZED,
                    outcome="invalid_target",
                )
                return ControlOutcome(consumed=True, status="invalid_target")
            return self._forget_member(
                message,
                target_user_id=target,
                command=command,
                persona=persona,
                now=now,
            )
        if argument != "CONFIRM":
            self._audit(
                message,
                command=command,
                target_user_id=None,
                authorization=ControlAuthorizationStatus.AUTHORIZED,
                outcome="confirmation_required",
            )
            return ControlOutcome(consumed=True, status="confirmation_required")
        return self._forget_group(message, persona=persona, now=now)

    def _authorize_admin(
        self,
        message: TelegramTextMessage,
        *,
        command: str,
    ) -> bool:
        try:
            status = self.telegram.get_chat_member(
                chat_id=self.allowed_chat_id,
                user_id=message.sender_id,
            )
        except TelegramApiError as error:
            self._audit(
                message,
                command=command,
                target_user_id=None,
                authorization=ControlAuthorizationStatus.UNAVAILABLE,
                outcome="authorization_unavailable",
                error_code=error.category,
            )
            return False
        if not status.is_administrator:
            self._audit(
                message,
                command=command,
                target_user_id=None,
                authorization=ControlAuthorizationStatus.DENIED,
                outcome="permission_denied",
            )
            return False
        return True

    def _enable(
        self,
        message: TelegramTextMessage,
        *,
        persona: PersonaSnapshot,
    ) -> ControlOutcome:
        policy = self.messages.policies.ensure(chat_id=message.group_id)
        if policy.memory_enabled:
            self._audit_authorized(message, command=_ENABLE_COMMAND, outcome="already_enabled")
            return ControlOutcome(consumed=True, status="already_enabled")
        effect_id = self._claim(message, persona=persona)
        if effect_id is None:
            return ControlOutcome(consumed=True, status="duplicate")
        try:
            sent = self.telegram.send_message(
                chat_id=message.group_id,
                text=MEMORY_DISCLOSURE,
                reply_to_message_id=message.message_id,
            )
        except TelegramApiError as error:
            self._mark_send_failure(effect_id, error)
            self._audit_authorized(
                message,
                command=_ENABLE_COMMAND,
                outcome="notice_failed",
                error_code=error.category,
            )
            return ControlOutcome(consumed=True, status="notice_failed")
        self.messages.policies.set_memory_status(
            chat_id=message.group_id,
            status="enabled",
            persona=persona,
            notice_message_id=sent.message_id,
            enabled_by_user_id=message.sender_id,
        )
        self.runs.mark_external_sent(effect_id, platform_message_id=sent.message_id)
        self._audit_authorized(message, command=_ENABLE_COMMAND, outcome="enabled")
        return ControlOutcome(
            consumed=True,
            status="enabled",
            platform_message_id=sent.message_id,
        )

    def _disable(
        self,
        message: TelegramTextMessage,
        *,
        persona: PersonaSnapshot,
    ) -> ControlOutcome:
        policy = self.messages.policies.ensure(chat_id=message.group_id)
        if not policy.memory_enabled:
            self._audit_authorized(message, command=_DISABLE_COMMAND, outcome="already_disabled")
            return ControlOutcome(consumed=True, status="already_disabled")
        effect_id = self._claim(message, persona=persona)
        if effect_id is None:
            return ControlOutcome(consumed=True, status="duplicate")
        self.messages.policies.set_memory_status(
            chat_id=message.group_id,
            status="disabled",
            persona=persona,
        )
        return self._acknowledge(
            message,
            effect_id=effect_id,
            command=_DISABLE_COMMAND,
            text="成员认识已停用；不会再持久化新消息或创建认识任务。",
            success_status="disabled",
        )

    def _forget_member(
        self,
        message: TelegramTextMessage,
        *,
        target_user_id: str,
        command: str,
        persona: PersonaSnapshot,
        now: datetime | None,
    ) -> ControlOutcome:
        effect_id = self._claim(message, persona=persona)
        if effect_id is None:
            return ControlOutcome(consumed=True, status="duplicate")
        generation = self.memory.reset_member(
            chat_id=message.group_id,
            member_user_id=target_user_id,
            reset_by_user_id=message.sender_id,
            at=now,
        )
        return self._acknowledge(
            message,
            effect_id=effect_id,
            command=command,
            target_user_id=target_user_id,
            text="已清除目标成员在本群的认识与留存原文。",
            success_status="member_forgotten",
            reset_generation=generation,
        )

    def _forget_group(
        self,
        message: TelegramTextMessage,
        *,
        persona: PersonaSnapshot,
        now: datetime | None,
    ) -> ControlOutcome:
        effect_id = self._claim(message, persona=persona)
        if effect_id is None:
            return ControlOutcome(consumed=True, status="duplicate")
        generation = self.memory.reset_group(
            chat_id=message.group_id,
            reset_by_user_id=message.sender_id,
            at=now,
        )
        return self._acknowledge(
            message,
            effect_id=effect_id,
            command=_FORGET_GROUP_COMMAND,
            text="已清除本群全部成员认识与留存原文。",
            success_status="group_forgotten",
            reset_generation=generation,
        )

    def _acknowledge(
        self,
        message: TelegramTextMessage,
        *,
        effect_id: int,
        command: str,
        text: str,
        success_status: str,
        target_user_id: str | None = None,
        reset_generation: int | None = None,
    ) -> ControlOutcome:
        try:
            sent = self.telegram.send_message(
                chat_id=message.group_id,
                text=text,
                reply_to_message_id=message.message_id,
            )
        except TelegramApiError as error:
            self._mark_send_failure(effect_id, error)
            self._audit_authorized(
                message,
                command=command,
                target_user_id=target_user_id,
                outcome=f"{success_status}_ack_failed",
                error_code=error.category,
            )
            return ControlOutcome(
                consumed=True,
                status=f"{success_status}_ack_failed",
                reset_generation=reset_generation,
            )
        self.runs.mark_external_sent(effect_id, platform_message_id=sent.message_id)
        self._audit_authorized(
            message,
            command=command,
            target_user_id=target_user_id,
            outcome=success_status,
        )
        return ControlOutcome(
            consumed=True,
            status=success_status,
            platform_message_id=sent.message_id,
            reset_generation=reset_generation,
        )

    def _claim(
        self,
        message: TelegramTextMessage,
        *,
        persona: PersonaSnapshot,
    ) -> int | None:
        return self.runs.claim_external_effect(
            message=message,
            effect_kind=ExternalEffectKind.CONTROL_ACK,
            persona=persona,
        )

    def _mark_send_failure(self, effect_id: int, error: TelegramApiError) -> None:
        if error.category in {
            "timeout",
            "transport_error",
            "invalid_json",
            "invalid_response",
            "invalid_result",
        }:
            self.runs.mark_external_uncertain(effect_id, error_code=error.category)
        else:
            self.runs.mark_external_failed(effect_id, error_code=error.category)

    def _audit_authorized(
        self,
        message: TelegramTextMessage,
        *,
        command: str,
        outcome: str,
        target_user_id: str | None = None,
        error_code: str | None = None,
    ) -> None:
        self._audit(
            message,
            command=command,
            target_user_id=target_user_id,
            authorization=ControlAuthorizationStatus.AUTHORIZED,
            outcome=outcome,
            error_code=error_code,
        )

    def _audit(
        self,
        message: TelegramTextMessage,
        *,
        command: str,
        target_user_id: str | None,
        authorization: ControlAuthorizationStatus,
        outcome: str,
        error_code: str | None = None,
    ) -> None:
        self.runs.record_control_action(
            chat_id=message.group_id,
            command=command,
            requesting_user_id=message.sender_id,
            target_user_id=target_user_id,
            authorization_status=authorization,
            outcome=outcome,
            error_code=error_code,
        )


def _parse_command(text: str) -> tuple[str, str | None]:
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return "", None
    command = parts[0].split("@", 1)[0].lower()
    argument = parts[1].strip() if len(parts) == 2 else None
    return command, argument
