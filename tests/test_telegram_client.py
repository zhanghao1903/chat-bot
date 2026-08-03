from __future__ import annotations

import http.client
import json
import traceback
import unittest
import urllib.error
from typing import Self
from unittest.mock import patch

from group_llm_agent.platforms.telegram import (
    TelegramApiError,
    TelegramBotApiClient,
    TelegramMemberStatus,
)


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _BodyReadTimeoutResponse(_Response):
    def read(self) -> bytes:
        raise TimeoutError("response body timed out")


class _BinaryResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, amount: int = -1) -> bytes:
        return self.content if amount < 0 else self.content[:amount]


class TelegramBotApiClientTests(unittest.TestCase):
    def test_get_me_returns_valid_result(self) -> None:
        client = TelegramBotApiClient("123456:test-token")
        with patch(
            "urllib.request.urlopen",
            return_value=_Response(
                {"ok": True, "result": {"id": 7, "is_bot": True, "username": "agent"}}
            ),
        ):
            identity = client.get_me()

        self.assertEqual(identity["id"], 7)

    def test_get_updates_requests_only_message_updates(self) -> None:
        client = TelegramBotApiClient("123456:test-token")
        with patch(
            "urllib.request.urlopen",
            return_value=_Response({"ok": True, "result": []}),
        ) as urlopen:
            updates = client.get_updates(offset=10, timeout_seconds=25)

        self.assertEqual(updates, [])
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["offset"], 10)
        self.assertEqual(payload["allowed_updates"], ["message"])

    def test_send_message_returns_confirmed_message_id(self) -> None:
        client = TelegramBotApiClient("123456:test-token")
        with patch(
            "urllib.request.urlopen",
            return_value=_Response(
                {"ok": True, "result": {"message_id": 77, "chat": {"id": -1001}}}
            ),
        ) as urlopen:
            sent = client.send_message(
                chat_id="-1001",
                text="notice",
                reply_to_message_id="12",
            )

        self.assertEqual("77", sent.message_id)
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(
            {
                "chat_id": "-1001",
                "text": "notice",
                "reply_parameters": {"message_id": 12},
            },
            payload,
        )

    def test_get_file_and_bounded_download(self) -> None:
        client = TelegramBotApiClient("123456:test-token")
        with patch(
            "urllib.request.urlopen",
            side_effect=[
                _Response(
                    {
                        "ok": True,
                        "result": {"file_path": "photos/file.jpg", "file_size": 4},
                    }
                ),
                _BinaryResponse(b"data"),
            ],
        ) as urlopen:
            telegram_file = client.get_file(file_id="opaque-file-id")
            content = client.download_file(
                file_path=telegram_file.file_path,
                maximum_bytes=4,
            )

        self.assertEqual(b"data", content)
        self.assertEqual(4, telegram_file.file_size)
        request = urlopen.call_args_list[1].args[0]
        self.assertEqual("GET", request.method)

    def test_send_sticker_uses_mapping_and_validates_returned_identity(self) -> None:
        client = TelegramBotApiClient("123456:test-token")
        with patch(
            "urllib.request.urlopen",
            return_value=_Response(
                {
                    "ok": True,
                    "result": {
                        "message_id": 88,
                        "sticker": {"file_unique_id": "stable-unique"},
                    },
                }
            ),
        ) as urlopen:
            sent = client.send_sticker(
                chat_id="-1001",
                sticker="mapped-file-id",
                reply_to_message_id="12",
            )

        self.assertEqual("88", sent.message_id)
        payload = json.loads(urlopen.call_args.args[0].data.decode())
        self.assertEqual("mapped-file-id", payload["sticker"])
        self.assertEqual({"message_id": 12}, payload["reply_parameters"])

    def test_download_rejects_paths_and_stream_overflow_without_leakage(self) -> None:
        token = "123456:very-secret"
        client = TelegramBotApiClient(token)
        for path in ("../secret", "/absolute", "https://example.test/file", "a\\b"):
            with self.subTest(path=path), self.assertRaises(TelegramApiError) as caught:
                client.download_file(file_path=path, maximum_bytes=4)
            self.assertEqual("invalid_file_path", caught.exception.category)
            self.assertNotIn(path, str(caught.exception))
            self.assertNotIn(token, str(caught.exception))

        with (
            patch("urllib.request.urlopen", return_value=_BinaryResponse(b"12345")),
            self.assertRaises(TelegramApiError) as caught,
        ):
            client.download_file(file_path="photos/file.jpg", maximum_bytes=4)
        self.assertEqual("too_large", caught.exception.category)

    def test_get_chat_member_returns_live_admin_status(self) -> None:
        client = TelegramBotApiClient("123456:test-token")
        with patch(
            "urllib.request.urlopen",
            return_value=_Response(
                {
                    "ok": True,
                    "result": {
                        "status": "administrator",
                        "user": {"id": 42, "is_bot": False},
                    },
                }
            ),
        ) as urlopen:
            member = client.get_chat_member(chat_id="-1001", user_id="42")

        self.assertEqual(TelegramMemberStatus.ADMINISTRATOR, member.status)
        self.assertTrue(member.is_administrator)
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual({"chat_id": "-1001", "user_id": 42}, payload)

    def test_get_chat_member_rejects_mismatched_or_ambiguous_result(self) -> None:
        client = TelegramBotApiClient("123456:test-token")
        for result in (
            {"status": "administrator", "user": {"id": 99}},
            {"status": "unknown", "user": {"id": 42}},
        ):
            with (
                self.subTest(result=result),
                patch(
                    "urllib.request.urlopen",
                    return_value=_Response({"ok": True, "result": result}),
                ),
                self.assertRaises(TelegramApiError) as caught,
            ):
                client.get_chat_member(chat_id="-1001", user_id="42")
            self.assertEqual("invalid_result", caught.exception.category)

    def test_transport_error_does_not_expose_token(self) -> None:
        token = "123456:very-secret"
        client = TelegramBotApiClient(token)
        with (
            patch(
                "urllib.request.urlopen",
                side_effect=urllib.error.URLError(f"https://api.telegram.org/bot{token}/getMe"),
            ),
            self.assertRaises(TelegramApiError) as caught,
        ):
            client.get_me()

        self.assertEqual(caught.exception.category, "transport_error")
        self.assertNotIn(token, str(caught.exception))

    def test_invalid_url_is_translated_without_exposing_token(self) -> None:
        token = "123456:bad token"
        client = TelegramBotApiClient(token)
        caught_error: TelegramApiError | None = None
        with patch(
            "urllib.request.urlopen",
            side_effect=http.client.InvalidURL(
                f"URL contains token https://api.telegram.org/bot{token}/getMe"
            ),
        ):
            try:
                client.get_me()
            except TelegramApiError as exc:
                caught_error = exc
                rendered_traceback = traceback.format_exc()
            else:
                self.fail("TelegramApiError was not raised")

        self.assertIsNotNone(caught_error)
        self.assertEqual(caught_error.category, "invalid_url")
        self.assertNotIn(token, str(caught_error))
        self.assertNotIn(token, rendered_traceback)

    def test_response_body_timeout_is_translated_without_exposing_token(self) -> None:
        token = "123456:very-secret"
        client = TelegramBotApiClient(token)
        with (
            patch(
                "urllib.request.urlopen",
                return_value=_BodyReadTimeoutResponse({"ok": True}),
            ),
            self.assertRaises(TelegramApiError) as caught,
        ):
            client.get_updates(offset=None, timeout_seconds=25)

        self.assertEqual(caught.exception.category, "timeout")
        self.assertNotIn(token, str(caught.exception))

    def test_api_error_does_not_include_response_description(self) -> None:
        client = TelegramBotApiClient("123456:test-token")
        with (
            patch(
                "urllib.request.urlopen",
                return_value=_Response(
                    {
                        "ok": False,
                        "error_code": 401,
                        "description": "Unauthorized 123456:test-token",
                    }
                ),
            ),
            self.assertRaises(TelegramApiError) as caught,
        ):
            client.get_me()

        self.assertEqual(
            str(caught.exception), "telegram_method=getMe category=api_error http_status=401"
        )
        self.assertNotIn("123456:test-token", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
