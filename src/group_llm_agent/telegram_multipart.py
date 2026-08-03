from __future__ import annotations

import http.client
import json
import secrets
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from group_llm_agent.platforms.telegram import TelegramApiError

_MAX_MULTIPART_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class MultipartFile:
    filename: str
    content_type: str
    content: bytes


UrlOpener = Callable[[urllib.request.Request, float], Any]


class TelegramMultipartTransport:
    """Bounded multipart transport used only by explicit operator workflows."""

    def __init__(
        self,
        *,
        token: str,
        timeout_seconds: float = 30,
        opener: UrlOpener | None = None,
    ) -> None:
        if not token or any(character.isspace() for character in token):
            raise ValueError("Telegram token is invalid")
        if not 0 < timeout_seconds <= 120:
            raise ValueError("timeout_seconds must be in (0, 120]")
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._opener = opener or _urlopen

    def __repr__(self) -> str:
        return "TelegramMultipartTransport(token=<redacted>)"

    def request(
        self,
        method: str,
        *,
        fields: Mapping[str, str],
        files: Mapping[str, MultipartFile],
    ) -> Any:
        boundary = f"codex-{secrets.token_hex(16)}"
        body = _multipart_body(boundary=boundary, fields=fields, files=files)
        if len(body) > _MAX_MULTIPART_BYTES:
            raise TelegramApiError(method, "upload_too_large")
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self._token}/{method}",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with self._opener(request, self._timeout_seconds) as response:
                raw = response.read(256_001)
        except urllib.error.HTTPError as error:
            raise TelegramApiError(method, "http_error", error.code) from None
        except urllib.error.URLError:
            raise TelegramApiError(method, "transport_error") from None
        except TimeoutError:
            raise TelegramApiError(method, "timeout") from None
        except (http.client.InvalidURL, ValueError):
            raise TelegramApiError(method, "invalid_url") from None
        except (http.client.HTTPException, OSError):
            raise TelegramApiError(method, "transport_error") from None
        if not isinstance(raw, bytes) or len(raw) > 256_000:
            raise TelegramApiError(method, "invalid_response")
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise TelegramApiError(method, "invalid_json") from None
        if not isinstance(parsed, dict) or not parsed.get("ok"):
            status = parsed.get("error_code") if isinstance(parsed, dict) else None
            raise TelegramApiError(
                method,
                "api_error",
                status if isinstance(status, int) and not isinstance(status, bool) else None,
            )
        return parsed.get("result")

    def upload_sticker_file(
        self,
        *,
        owner_user_id: str,
        content: bytes,
        filename: str,
    ) -> tuple[str, str]:
        result = self.request(
            "uploadStickerFile",
            fields={"user_id": owner_user_id, "sticker_format": "static"},
            files={
                "sticker": MultipartFile(
                    filename=filename,
                    content_type="image/webp",
                    content=content,
                )
            },
        )
        if not isinstance(result, dict):
            raise TelegramApiError("uploadStickerFile", "invalid_result")
        file_id = result.get("file_id")
        unique_id = result.get("file_unique_id")
        if not isinstance(file_id, str) or not isinstance(unique_id, str):
            raise TelegramApiError("uploadStickerFile", "invalid_result")
        return file_id, unique_id

    def set_static_profile_photo(self, *, jpeg: bytes) -> None:
        result = self.request(
            "setMyProfilePhoto",
            fields={
                "photo": json.dumps(
                    {"type": "static", "photo": "attach://profile_photo"},
                    separators=(",", ":"),
                )
            },
            files={
                "profile_photo": MultipartFile(
                    filename="profile.jpg",
                    content_type="image/jpeg",
                    content=jpeg,
                )
            },
        )
        if result is not True:
            raise TelegramApiError("setMyProfilePhoto", "invalid_result")


def _multipart_body(
    *,
    boundary: str,
    fields: Mapping[str, str],
    files: Mapping[str, MultipartFile],
) -> bytes:
    chunks: list[bytes] = []
    for name, value in fields.items():
        _validate_disposition_token(name)
        chunks.extend(
            (
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            )
        )
    for name, upload in files.items():
        _validate_disposition_token(name)
        _validate_disposition_token(upload.filename)
        chunks.extend(
            (
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{upload.filename}"\r\n'
                ).encode(),
                f"Content-Type: {upload.content_type}\r\n\r\n".encode(),
                upload.content,
                b"\r\n",
            )
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks)


def _validate_disposition_token(value: str) -> None:
    if not value or any(character in value for character in '\r\n"\\'):
        raise ValueError("Invalid multipart field")


def _urlopen(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)
