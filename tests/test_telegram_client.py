from __future__ import annotations

import json
import unittest
import urllib.error
from typing import Self
from unittest.mock import patch

from group_llm_agent.platforms.telegram import TelegramApiError, TelegramBotApiClient


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class TelegramBotApiClientTests(unittest.TestCase):
    def test_get_me_returns_valid_result(self) -> None:
        client = TelegramBotApiClient("secret-token")
        with patch(
            "urllib.request.urlopen",
            return_value=_Response(
                {"ok": True, "result": {"id": 7, "is_bot": True, "username": "agent"}}
            ),
        ):
            identity = client.get_me()

        self.assertEqual(identity["id"], 7)

    def test_get_updates_requests_only_message_updates(self) -> None:
        client = TelegramBotApiClient("secret-token")
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

    def test_api_error_does_not_include_response_description(self) -> None:
        client = TelegramBotApiClient("secret-token")
        with (
            patch(
                "urllib.request.urlopen",
                return_value=_Response(
                    {
                        "ok": False,
                        "error_code": 401,
                        "description": "Unauthorized secret-token",
                    }
                ),
            ),
            self.assertRaises(TelegramApiError) as caught,
        ):
            client.get_me()

        self.assertEqual(
            str(caught.exception), "telegram_method=getMe category=api_error http_status=401"
        )
        self.assertNotIn("secret-token", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
