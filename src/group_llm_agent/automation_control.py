from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from group_llm_agent.automation import (
    AutomationRepository,
    GroupAutomationConfig,
    SubscriptionPreferences,
)
from group_llm_agent.automation_runtime import next_scheduled
from group_llm_agent.events import ExternalEffectKind, PersonaSnapshot, TelegramTextMessage
from group_llm_agent.platforms.telegram import ChatMemberStatus, SentMessage, TelegramApiError
from group_llm_agent.runs import RunRepository

_ENABLE = "/food_enable"
_DISABLE = "/food_disable"
_PAUSE = "/food_pause"
_RESUME = "/food_resume"
_CONFIG = "/food_config"
_SUBSCRIBE = "/food_subscribe"
_PREFERENCES = "/food_preferences"
_UNSUBSCRIBE = "/food_unsubscribe"
_STATUS = "/food_status"
FOOD_CONTROL_COMMANDS = frozenset(
    {_ENABLE, _DISABLE, _PAUSE, _RESUME, _CONFIG, _SUBSCRIBE, _PREFERENCES, _UNSUBSCRIBE, _STATUS}
)
_ADMIN_COMMANDS = frozenset({_ENABLE, _DISABLE, _PAUSE, _RESUME, _CONFIG})
_UNCERTAIN_TELEGRAM_ERRORS = frozenset(
    {"timeout", "transport_error", "invalid_json", "invalid_response", "invalid_result"}
)


class TelegramAutomationControlPort(Protocol):
    def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        reply_to_message_id: str | None = None,
    ) -> SentMessage: ...

    def get_chat_member(self, *, chat_id: str, user_id: str) -> ChatMemberStatus: ...


@dataclass(frozen=True)
class AutomationControlOutcome:
    consumed: bool
    status: str
    platform_message_id: str | None = None


class AutomationControlService:
    def __init__(
        self,
        *,
        allowed_chat_id: str,
        bot_user_id: str,
        bot_username: str | None,
        telegram: TelegramAutomationControlPort,
        repository: AutomationRepository,
        runs: RunRepository,
        capability_available: bool,
    ) -> None:
        self.allowed_chat_id = allowed_chat_id
        self.bot_user_id = bot_user_id
        self.bot_username = bot_username
        self.telegram = telegram
        self.repository = repository
        self.runs = runs
        self.capability_available = capability_available

    def handle(
        self,
        message: TelegramTextMessage,
        *,
        persona: PersonaSnapshot,
        now: datetime | None = None,
    ) -> AutomationControlOutcome:
        command, argument = _parse_command(message.text, bot_username=self.bot_username)
        if command not in FOOD_CONTROL_COMMANDS:
            return AutomationControlOutcome(consumed=False, status="not_automation_control")
        if message.group_id != self.allowed_chat_id or message.sender_id == self.bot_user_id:
            return AutomationControlOutcome(consumed=True, status="ignored_scope")
        if not self.capability_available:
            self._audit(message, command=command, actor_role="unknown", result="unavailable")
            return AutomationControlOutcome(consumed=True, status="capability_unavailable")

        actor_role = "member"
        if command in _ADMIN_COMMANDS:
            if not self._is_admin(message, command=command):
                return AutomationControlOutcome(consumed=True, status="not_authorized")
            actor_role = "administrator"

        effect_id = self.runs.claim_external_effect(
            message=message,
            effect_kind=ExternalEffectKind.CONTROL_ACK,
            persona=persona,
        )
        if effect_id is None:
            return AutomationControlOutcome(consumed=True, status="duplicate")
        try:
            status, response = self._apply(
                message,
                command=command,
                argument=argument,
                actor_role=actor_role,
                now=now or datetime.now(UTC),
            )
        except ValueError:
            status, response = "invalid_command", "配置格式不正确，未做任何修改。"
        return self._ack(
            message,
            effect_id=effect_id,
            command=command,
            actor_role=actor_role,
            status=status,
            response=response,
        )

    def _apply(
        self,
        message: TelegramTextMessage,
        *,
        command: str,
        argument: str | None,
        actor_role: str,
        now: datetime,
    ) -> tuple[str, str]:
        if command == _ENABLE:
            if argument is not None:
                raise ValueError("food_enable takes no arguments")
            config = self.repository.enable_group(chat_id=message.group_id)
            return (
                "enabled",
                f"工作日美食推荐已启用；时区 {config.timezone}，午餐 {config.lunch_time}，晚餐 {config.dinner_time}。",
            )
        if command == _DISABLE:
            if argument != "CONFIRM":
                return "confirmation_required", "关闭会清除当前订阅；请发送 /food_disable CONFIRM。"
            changed = self.repository.disable_group(chat_id=message.group_id)
            return (
                "disabled" if changed else "already_disabled",
                "工作日美食推荐已关闭，当前订阅已清除。",
            )
        if command == _PAUSE:
            changed = self.repository.set_paused(chat_id=message.group_id, paused=True)
            return (
                "paused" if changed else "not_enabled",
                "工作日美食推荐已暂停；普通聊天不受影响。",
            )
        if command == _RESUME:
            changed = self.repository.set_paused(chat_id=message.group_id, paused=False)
            return ("resumed" if changed else "not_enabled", "工作日美食推荐已恢复。")
        if command == _CONFIG:
            values = _key_values(argument, allowed={"timezone", "lunch", "dinner", "location"})
            current = self.repository.get_config(chat_id=message.group_id)
            if current is None or not current.enabled:
                return "not_enabled", "请先由群管理员启用工作日美食推荐。"
            config = self.repository.update_config(
                chat_id=message.group_id,
                timezone=values.get("timezone", current.timezone),
                lunch_time=values.get("lunch", current.lunch_time),
                dinner_time=values.get("dinner", current.dinner_time),
                location_text=values.get("location", current.location_text),
            )
            return (
                "configured",
                f"配置已更新：{config.timezone}，午餐 {config.lunch_time}，晚餐 {config.dinner_time}。",
            )
        if command == _SUBSCRIBE:
            if argument is not None:
                raise ValueError("food_subscribe takes no arguments")
            created = self.repository.subscribe(
                chat_id=message.group_id,
                member_user_id=message.sender_id,
            )
            active_config = self.repository.get_config(chat_id=message.group_id)
            if active_config is None or not active_config.enabled:
                raise ValueError("subscription requires active group config")
            return (
                "subscribed" if created else "already_subscribed",
                _subscription_summary(
                    chat_id=message.group_id,
                    config=active_config,
                    now=now,
                ),
            )
        if command == _PREFERENCES:
            preferences = _preferences(argument)
            changed = self.repository.set_preferences(
                chat_id=message.group_id,
                member_user_id=message.sender_id,
                preferences=preferences,
            )
            return (
                "preferences_updated" if changed else "not_subscribed",
                "你的有限美食偏好已更新。" if changed else "请先订阅。",
            )
        if command == _UNSUBSCRIBE:
            if argument is not None:
                raise ValueError("food_unsubscribe takes no arguments")
            changed = self.repository.unsubscribe(
                chat_id=message.group_id,
                member_user_id=message.sender_id,
            )
            return (
                "unsubscribed" if changed else "not_subscribed",
                "你已退订，相关活动偏好已清除。",
            )
        if argument is not None:
            raise ValueError("food_status takes no arguments")
        return "status", self._status(message=message, now=now)

    def _status(self, *, message: TelegramTextMessage, now: datetime) -> str:
        config = self.repository.get_config(chat_id=message.group_id)
        if config is None:
            return "本群尚未启用工作日美食推荐。"
        count = self.repository.aggregate_preferences(chat_id=message.group_id).subscriber_count
        own = self.repository.is_subscribed(
            chat_id=message.group_id,
            member_user_id=message.sender_id,
        )
        next_at = next_scheduled(config, after=now)
        next_text = _local_schedule_text(next_at, timezone=config.timezone)
        state = "关闭" if not config.enabled else "暂停" if config.paused else "运行"
        return (
            f"当前群（{message.group_id}）状态：{state}；时区 {config.timezone}；"
            f"午餐 {config.lunch_time}，晚餐 {config.dinner_time}；订阅数：{count}；"
            f"你：{'已订阅' if own else '未订阅'}；下一次：{next_text}；"
            "每个餐次全群合并发送最多一条，不会逐个 @；退订请发送 "
            f"/food_unsubscribe；配置版本：{config.config_version}。"
        )

    def _is_admin(self, message: TelegramTextMessage, *, command: str) -> bool:
        try:
            member = self.telegram.get_chat_member(
                chat_id=message.group_id,
                user_id=message.sender_id,
            )
        except TelegramApiError as error:
            self._audit(
                message,
                command=command,
                actor_role="unknown",
                result="authorization_unavailable",
                reason=error.category,
            )
            return False
        if not member.is_administrator:
            self._audit(message, command=command, actor_role="member", result="permission_denied")
            return False
        return True

    def _ack(
        self,
        message: TelegramTextMessage,
        *,
        effect_id: int,
        command: str,
        actor_role: str,
        status: str,
        response: str,
    ) -> AutomationControlOutcome:
        self._audit(message, command=command, actor_role=actor_role, result=status)
        try:
            sent = self.telegram.send_message(
                chat_id=message.group_id,
                text=response,
                reply_to_message_id=message.message_id,
            )
        except TelegramApiError as error:
            if error.category in _UNCERTAIN_TELEGRAM_ERRORS:
                self.runs.mark_external_uncertain(effect_id, error_code=error.category)
            else:
                self.runs.mark_external_failed(effect_id, error_code=error.category)
            return AutomationControlOutcome(consumed=True, status=f"{status}_ack_failed")
        self.runs.mark_external_sent(effect_id, platform_message_id=sent.message_id)
        return AutomationControlOutcome(
            consumed=True, status=status, platform_message_id=sent.message_id
        )

    def _audit(
        self,
        message: TelegramTextMessage,
        *,
        command: str,
        actor_role: str,
        result: str,
        reason: str = "control_action",
    ) -> None:
        config = self.repository.get_config(chat_id=message.group_id)
        self.repository.record_action(
            chat_id=message.group_id,
            actor_user_id=message.sender_id,
            actor_role=actor_role,
            action_kind=command.lstrip("/"),
            result_kind=result,
            reason_code=reason,
            config_version=config.config_version if config is not None else None,
        )


def _subscription_summary(*, chat_id: str, config: GroupAutomationConfig, now: datetime) -> str:
    next_text = _local_schedule_text(
        next_scheduled(config, after=now),
        timezone=config.timezone,
    )
    state = "（当前暂停）" if config.paused else ""
    return (
        f"你已订阅当前群（{chat_id}）的工作日美食推荐{state}；时区 {config.timezone}；"
        f"午餐 {config.lunch_time}，晚餐 {config.dinner_time}；下一次：{next_text}；"
        "每个餐次全群合并发送最多一条，不会逐个 @；退订请发送 /food_unsubscribe。"
    )


def _local_schedule_text(value: datetime | None, *, timezone: str) -> str:
    if value is None:
        return "暂无"
    local = value.astimezone(ZoneInfo(timezone))
    return f"{local:%Y-%m-%d %H:%M} ({timezone})"


def _parse_command(text: str, *, bot_username: str | None) -> tuple[str, str | None]:
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return "", None
    command_token, separator, target = parts[0].partition("@")
    if separator and (
        bot_username is None
        or not target
        or target.casefold() != bot_username.lstrip("@").casefold()
    ):
        return "", None
    return command_token.lower(), parts[1].strip() if len(parts) == 2 else None


def _key_values(argument: str | None, *, allowed: set[str]) -> dict[str, str]:
    if argument is None:
        raise ValueError("arguments are required")
    result: dict[str, str] = {}
    for token in argument.split():
        key, separator, value = token.partition("=")
        if not separator or key not in allowed or not value or key in result:
            raise ValueError("invalid key-value arguments")
        result[key] = value
    if not result:
        raise ValueError("arguments are required")
    return result


def _preferences(argument: str | None) -> SubscriptionPreferences:
    values = _key_values(argument, allowed={"cuisine", "budget", "dietary", "avoid"})

    def items(key: str) -> tuple[str, ...]:
        value = values.get(key)
        return tuple(part for part in value.split(",") if part) if value else ()

    return SubscriptionPreferences(
        cuisine_tags=items("cuisine"),
        budget_band=values.get("budget"),
        dietary_tags=items("dietary"),
        avoid_items=items("avoid"),
    )
