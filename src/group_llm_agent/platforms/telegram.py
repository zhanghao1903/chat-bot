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

from group_llm_agent.events import InboundMedia, MediaKind, TelegramMessage


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
    asset_file_unique_id: str | None = None


@dataclass(frozen=True)
class TelegramFile:
    file_path: str
    file_size: int | None = None


@dataclass(frozen=True)
class TelegramProfilePhoto:
    file_id: str
    file_unique_id: str
    width: int
    height: int


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
        self._token = token
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

    def send_sticker(
        self,
        *,
        chat_id: str,
        sticker: str,
        reply_to_message_id: str | None = None,
    ) -> SentMessage:
        payload: dict[str, Any] = {"chat_id": chat_id, "sticker": sticker}
        if reply_to_message_id is not None:
            payload["reply_parameters"] = {"message_id": int(reply_to_message_id)}
        result = self.request("sendSticker", payload)
        if not isinstance(result, dict):
            raise TelegramApiError("sendSticker", "invalid_result")
        message_id = result.get("message_id")
        if isinstance(message_id, bool) or not isinstance(message_id, (int, str)):
            raise TelegramApiError("sendSticker", "invalid_result")
        returned = result.get("sticker")
        unique_id = returned.get("file_unique_id") if isinstance(returned, dict) else None
        if not isinstance(unique_id, str):
            raise TelegramApiError("sendSticker", "invalid_result")
        return SentMessage(message_id=str(message_id), asset_file_unique_id=unique_id)

    def get_file(self, *, file_id: str) -> TelegramFile:
        result = self.request("getFile", {"file_id": file_id})
        if not isinstance(result, dict):
            raise TelegramApiError("getFile", "invalid_result")
        file_path = result.get("file_path")
        file_size = result.get("file_size")
        if not isinstance(file_path, str) or not _safe_file_path(file_path):
            raise TelegramApiError("getFile", "invalid_file_path")
        if file_size is not None and (
            isinstance(file_size, bool) or not isinstance(file_size, int) or file_size < 0
        ):
            raise TelegramApiError("getFile", "invalid_result")
        return TelegramFile(file_path=file_path, file_size=file_size)

    def download_file(
        self,
        *,
        file_path: str,
        maximum_bytes: int,
        timeout_seconds: int | None = None,
    ) -> bytes:
        if maximum_bytes <= 0:
            raise ValueError("maximum_bytes must be positive")
        if not _safe_file_path(file_path):
            raise TelegramApiError("downloadFile", "invalid_file_path")
        try:
            request = urllib.request.Request(
                f"https://api.telegram.org/file/bot{self._token}/{file_path}",
                method="GET",
            )
            with urllib.request.urlopen(
                request,
                timeout=timeout_seconds or self.timeout_seconds,
            ) as response:
                raw_body = response.read(maximum_bytes + 1)
        except urllib.error.HTTPError as exc:
            raise TelegramApiError("downloadFile", "http_error", exc.code) from None
        except urllib.error.URLError:
            raise TelegramApiError("downloadFile", "transport_error") from None
        except (http.client.InvalidURL, ValueError):
            raise TelegramApiError("downloadFile", "invalid_url") from None
        except TimeoutError:
            raise TelegramApiError("downloadFile", "timeout") from None
        except (http.client.HTTPException, OSError):
            raise TelegramApiError("downloadFile", "transport_error") from None
        if not isinstance(raw_body, bytes):
            raise TelegramApiError("downloadFile", "invalid_response")
        if len(raw_body) > maximum_bytes:
            raise TelegramApiError("downloadFile", "too_large")
        return raw_body

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

    def get_user_profile_photo(self, *, user_id: str) -> TelegramProfilePhoto | None:
        result = self.request(
            "getUserProfilePhotos",
            {"user_id": int(user_id), "offset": 0, "limit": 1},
        )
        if not isinstance(result, dict):
            raise TelegramApiError("getUserProfilePhotos", "invalid_result")
        photos = result.get("photos")
        if not isinstance(photos, list):
            raise TelegramApiError("getUserProfilePhotos", "invalid_result")
        if not photos:
            return None
        sizes = photos[0]
        if not isinstance(sizes, list):
            raise TelegramApiError("getUserProfilePhotos", "invalid_result")
        candidates = [item for item in sizes if isinstance(item, dict)]
        if not candidates:
            raise TelegramApiError("getUserProfilePhotos", "invalid_result")
        selected = max(
            candidates,
            key=lambda item: (_safe_int(item.get("width")), _safe_int(item.get("height"))),
        )
        file_id = selected.get("file_id")
        unique_id = selected.get("file_unique_id")
        width = _optional_nonnegative_int(selected.get("width"))
        height = _optional_nonnegative_int(selected.get("height"))
        if (
            not isinstance(file_id, str)
            or not isinstance(unique_id, str)
            or width is None
            or height is None
        ):
            raise TelegramApiError("getUserProfilePhotos", "invalid_result")
        return TelegramProfilePhoto(file_id, unique_id, width, height)

    def remove_my_profile_photo(self) -> None:
        if self.request("removeMyProfilePhoto") is not True:
            raise TelegramApiError("removeMyProfilePhoto", "invalid_result")

    def create_new_sticker_set(
        self,
        *,
        owner_user_id: str,
        name: str,
        title: str,
        stickers: list[dict[str, Any]],
    ) -> None:
        result = self.request(
            "createNewStickerSet",
            {
                "user_id": int(owner_user_id),
                "name": name,
                "title": title,
                "stickers": stickers,
                "sticker_type": "regular",
            },
        )
        if result is not True:
            raise TelegramApiError("createNewStickerSet", "invalid_result")

    def add_sticker_to_set(
        self,
        *,
        owner_user_id: str,
        name: str,
        sticker: dict[str, Any],
    ) -> None:
        result = self.request(
            "addStickerToSet",
            {"user_id": int(owner_user_id), "name": name, "sticker": sticker},
        )
        if result is not True:
            raise TelegramApiError("addStickerToSet", "invalid_result")

    def get_sticker_set(self, *, name: str) -> list[tuple[str, str]]:
        result = self.request("getStickerSet", {"name": name})
        stickers = result.get("stickers") if isinstance(result, dict) else None
        if not isinstance(stickers, list):
            raise TelegramApiError("getStickerSet", "invalid_result")
        mapped: list[tuple[str, str]] = []
        for sticker in stickers:
            file_id = sticker.get("file_id") if isinstance(sticker, dict) else None
            unique_id = sticker.get("file_unique_id") if isinstance(sticker, dict) else None
            if not isinstance(file_id, str) or not isinstance(unique_id, str):
                raise TelegramApiError("getStickerSet", "invalid_result")
            mapped.append((file_id, unique_id))
        return mapped


class TelegramAdapter:
    def __init__(
        self,
        *,
        bot_username: str | None = None,
    ) -> None:
        self.bot_username = bot_username

    def normalize_update(
        self, update: dict[str, Any], raw_event_ref: str | None = None
    ) -> list[TelegramMessage]:
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
        text_value = message.get("text")
        caption_value = message.get("caption")
        text = text_value if isinstance(text_value, str) else caption_value
        media = _inbound_media(message)
        if (not isinstance(text, str) or not text.strip()) and media is None:
            return []
        if not isinstance(text, str):
            text = ""

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
            TelegramMessage(
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
                media=media,
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
        entities = message.get("caption_entities")
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


_STATIC_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


def _inbound_media(message: dict[str, Any]) -> InboundMedia | None:
    photos = message.get("photo")
    if isinstance(photos, list):
        candidates = [item for item in photos if isinstance(item, dict)]
        if candidates:
            selected = max(
                candidates,
                key=lambda item: (_safe_int(item.get("width")), _safe_int(item.get("height"))),
            )
            return _media_from_mapping(selected, kind=MediaKind.PHOTO, mime_type="image/jpeg")

    document = message.get("document")
    if isinstance(document, dict):
        mime_type = document.get("mime_type")
        if isinstance(mime_type, str) and mime_type in _STATIC_IMAGE_MIME_TYPES:
            return _media_from_mapping(
                document,
                kind=MediaKind.STATIC_DOCUMENT,
                mime_type=mime_type,
            )

    sticker = message.get("sticker")
    if isinstance(sticker, dict):
        is_animated = sticker.get("is_animated") is True
        is_video = sticker.get("is_video") is True
        if not is_animated and not is_video:
            return _media_from_mapping(
                sticker,
                kind=MediaKind.STATIC_STICKER,
                mime_type="image/webp",
                sticker_set_name=(
                    str(sticker["set_name"]) if isinstance(sticker.get("set_name"), str) else None
                ),
            )
    return None


def _media_from_mapping(
    payload: dict[str, Any],
    *,
    kind: MediaKind,
    mime_type: str,
    sticker_set_name: str | None = None,
) -> InboundMedia | None:
    file_id = payload.get("file_id")
    unique_id = payload.get("file_unique_id")
    if (
        not isinstance(file_id, str)
        or not file_id
        or not isinstance(unique_id, str)
        or not unique_id
    ):
        return None
    return InboundMedia(
        kind=kind,
        file_id=file_id,
        file_unique_id=unique_id,
        mime_type=mime_type,
        file_size=_optional_nonnegative_int(payload.get("file_size")),
        width=_optional_nonnegative_int(payload.get("width")),
        height=_optional_nonnegative_int(payload.get("height")),
        sticker_set_name=sticker_set_name,
        is_animated=payload.get("is_animated") is True,
        is_video=payload.get("is_video") is True,
    )


def _optional_nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _safe_int(value: object) -> int:
    parsed = _optional_nonnegative_int(value)
    return parsed if parsed is not None else 0


def _safe_file_path(value: str) -> bool:
    if not value or len(value) > 512 or value.startswith(("/", "\\")):
        return False
    if "://" in value or "?" in value or "#" in value or "\\" in value:
        return False
    parts = value.split("/")
    return all(part not in {"", ".", ".."} for part in parts)
