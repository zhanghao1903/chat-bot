from __future__ import annotations

import http.client
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from group_llm_agent.events import TelegramTextMessage


class TelegramApiError(RuntimeError):
    """A redacted Bot API failure safe to include in logs."""

    def __init__(self, method: str, category: str, status_code: int | None = None) -> None:
        self.method = method
        self.category = category
        self.status_code = status_code
        suffix = f" http_status={status_code}" if status_code is not None else ""
        super().__init__(f"telegram_method={method} category={category}{suffix}")


@dataclass(frozen=True)
class SentMessage:
    message_id: str


class TelegramMemberStatus(StrEnum):
    CREATOR = "creator"
    ADMINISTRATOR = "administrator"
    MEMBER = "member"
    RESTRICTED = "restricted"
    LEFT = "left"
    KICKED = "kicked"


@dataclass(frozen=True)
class ChatMemberStatus:
    user_id: str
    status: TelegramMemberStatus

    @property
    def is_administrator(self) -> bool:
        return self.status in {
            TelegramMemberStatus.CREATOR,
            TelegramMemberStatus.ADMINISTRATOR,
        }


class TelegramBotApiClient:
    def __init__(self, token: str, timeout_seconds: int = 30) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.timeout_seconds = timeout_seconds

    def request(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout_seconds: int | None = None,
    ) -> Any:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            url = f"{self.base_url}/{method}"
            request = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(
                request,
                timeout=timeout_seconds or self.timeout_seconds,
            ) as response:
                raw_body = response.read()
        except urllib.error.HTTPError as exc:
            raise TelegramApiError(method, "http_error", exc.code) from None
        except urllib.error.URLError:
            raise TelegramApiError(method, "transport_error") from None
        except (http.client.InvalidURL, ValueError):
            raise TelegramApiError(method, "invalid_url") from None
        except TimeoutError:
            raise TelegramApiError(method, "timeout") from None
        except (http.client.HTTPException, OSError):
            raise TelegramApiError(method, "transport_error") from None
        try:
            body = raw_body.decode("utf-8")
            parsed = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise TelegramApiError(method, "invalid_json") from exc
        if not isinstance(parsed, dict):
            raise TelegramApiError(method, "invalid_response")
        if not parsed.get("ok"):
            error_code = parsed.get("error_code")
            status_code = error_code if isinstance(error_code, int) else None
            raise TelegramApiError(method, "api_error", status_code)
        return parsed.get("result")

    def get_me(self) -> dict[str, Any]:
        result = self.request("getMe")
        if not isinstance(result, dict):
            raise TelegramApiError("getMe", "invalid_result")
        return result

    def get_updates(self, *, offset: int | None, timeout_seconds: int) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "timeout": timeout_seconds,
            "allowed_updates": ["message"],
        }
        if offset is not None:
            params["offset"] = offset
        result = self.request(
            "getUpdates",
            params,
            timeout_seconds=timeout_seconds + 5,
        )
        if not isinstance(result, list):
            raise TelegramApiError("getUpdates", "invalid_result")
        return [item for item in result if isinstance(item, dict)]

    def send_message(
        self, *, chat_id: str, text: str, reply_to_message_id: str | None = None
    ) -> SentMessage:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_to_message_id is not None:
            payload["reply_parameters"] = {"message_id": int(reply_to_message_id)}
        result = self.request("sendMessage", payload)
        if not isinstance(result, dict):
            raise TelegramApiError("sendMessage", "invalid_result")
        message_id = result.get("message_id")
        if isinstance(message_id, bool) or not isinstance(message_id, (int, str)):
            raise TelegramApiError("sendMessage", "invalid_result")
        return SentMessage(message_id=str(message_id))

    def get_chat_member(self, *, chat_id: str, user_id: str) -> ChatMemberStatus:
        result = self.request(
            "getChatMember",
            {"chat_id": chat_id, "user_id": int(user_id)},
        )
        if not isinstance(result, dict):
            raise TelegramApiError("getChatMember", "invalid_result")
        user = result.get("user")
        returned_user_id = user.get("id") if isinstance(user, dict) else None
        if (
            isinstance(returned_user_id, bool)
            or not isinstance(returned_user_id, (int, str))
            or str(returned_user_id) != user_id
        ):
            raise TelegramApiError("getChatMember", "invalid_result")
        status_value = result.get("status")
        if not isinstance(status_value, str):
            raise TelegramApiError("getChatMember", "invalid_result") from None
        try:
            status = TelegramMemberStatus(status_value)
        except ValueError:
            raise TelegramApiError("getChatMember", "invalid_result") from None
        return ChatMemberStatus(user_id=user_id, status=status)


class TelegramAdapter:
    def __init__(
        self,
        *,
        bot_username: str | None = None,
    ) -> None:
        self.bot_username = bot_username

    def normalize_update(
        self, update: dict[str, Any], raw_event_ref: str | None = None
    ) -> list[TelegramTextMessage]:
        message = update.get("message")
        if not isinstance(message, dict):
            return []
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        if not isinstance(chat, dict) or not isinstance(sender, dict):
            return []
        if str(chat.get("type") or "") not in {"group", "supergroup"}:
            return []
        if sender.get("is_bot") is True:
            return []
        text = message.get("text")
        if not isinstance(text, str) or not text.strip():
            return []

        group_id_value = chat.get("id")
        message_id_value = message.get("message_id")
        sender_id_value = sender.get("id")
        if group_id_value is None or message_id_value is None or sender_id_value is None:
            return []
        try:
            timestamp = datetime.fromtimestamp(int(message.get("date", 0)), tz=UTC)
        except (TypeError, ValueError, OSError, OverflowError):
            return []

        group_id = str(group_id_value)
        message_id = str(message_id_value)
        sender_id = str(sender_id_value)
        display_name = _display_name(sender)
        is_bot_command, bot_command_target = _bot_command(text, message)
        if bot_command_target is not None and not self._is_local_command_target(bot_command_target):
            return []
        mentioned_bot = self._mentioned_bot(text, is_bot_command=is_bot_command)
        replied_to_message_id, replied_to_user_id = _reply_metadata(message)
        mentioned_user_ids = _mentioned_user_ids(message)

        return [
            TelegramTextMessage(
                event_id=str(update.get("update_id", f"telegram:{group_id}:{message_id}")),
                group_id=group_id,
                message_id=message_id,
                sender_id=sender_id,
                sender_display_name=display_name,
                text=text,
                mentioned_bot=mentioned_bot,
                replied_to_message_id=replied_to_message_id,
                replied_to_user_id=replied_to_user_id,
                mentioned_user_ids=mentioned_user_ids,
                is_bot_command=is_bot_command,
                bot_command_target=bot_command_target,
                timestamp=timestamp,
                raw_event_ref=raw_event_ref,
            )
        ]

    def _mentioned_bot(self, text: str, *, is_bot_command: bool) -> bool:
        if self.bot_username and re.search(
            rf"@{re.escape(self.bot_username)}(?![A-Za-z0-9_])",
            text,
            re.IGNORECASE,
        ):
            return True
        return is_bot_command

    def _is_local_command_target(self, target: str) -> bool:
        return self.bot_username is not None and target.casefold() == self.bot_username.casefold()


def _display_name(sender: dict[str, Any]) -> str:
    parts = [
        str(sender.get("first_name") or "").strip(),
        str(sender.get("last_name") or "").strip(),
    ]
    name = " ".join(part for part in parts if part).strip()
    return name or str(sender.get("username") or sender.get("id") or "unknown")


def _reply_metadata(message: dict[str, Any]) -> tuple[str | None, str | None]:
    reply = message.get("reply_to_message")
    if not isinstance(reply, dict):
        return None, None
    reply_message_id = reply.get("message_id")
    reply_sender = reply.get("from")
    reply_sender_id = reply_sender.get("id") if isinstance(reply_sender, dict) else None
    return (
        str(reply_message_id) if reply_message_id is not None else None,
        str(reply_sender_id) if reply_sender_id is not None else None,
    )


def _mentioned_user_ids(message: dict[str, Any]) -> tuple[str, ...]:
    entities = message.get("entities")
    if not isinstance(entities, list):
        return ()
    result: list[str] = []
    for entity in entities:
        if not isinstance(entity, dict) or entity.get("type") != "text_mention":
            continue
        user = entity.get("user")
        user_id = user.get("id") if isinstance(user, dict) else None
        if user_id is not None and str(user_id) not in result:
            result.append(str(user_id))
    return tuple(result)


def _bot_command(text: str, message: dict[str, Any]) -> tuple[bool, str | None]:
    entities = message.get("entities")
    if not isinstance(entities, list):
        return False, None
    for entity in entities:
        if (
            not isinstance(entity, dict)
            or entity.get("type") != "bot_command"
            or entity.get("offset") != 0
        ):
            continue
        length = entity.get("length")
        if isinstance(length, bool) or not isinstance(length, int) or not 1 <= length <= len(text):
            return False, None
        token = text[:length]
        if not token.startswith("/"):
            return False, None
        _, separator, target = token.partition("@")
        return True, target if separator else None
    return False, None
