from __future__ import annotations

import json
import unittest
import urllib.error
from typing import Any, Self

from group_llm_agent.platforms.telegram import TelegramApiError
from group_llm_agent.telegram_multipart import TelegramMultipartTransport


class _Response:
    def __init__(self, payload: object) -> None:
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _maximum: int) -> bytes:
        return self.body


class _Opener:
    def __init__(self, result: object) -> None:
        self.result = result
        self.requests: list[Any] = []

    def __call__(self, request: Any, _timeout: float) -> _Response:
        self.requests.append(request)
        return _Response({"ok": True, "result": self.result})


class TelegramMultipartTransportTests(unittest.TestCase):
    def test_upload_sticker_uses_bounded_static_multipart_contract(self) -> None:
        opener = _Opener({"file_id": "file-1", "file_unique_id": "unique-1"})
        transport = TelegramMultipartTransport(token="123:safe", opener=opener)

        result = transport.upload_sticker_file(
            owner_user_id="42",
            content=b"webp",
            filename="lezhi.webp",
        )

        self.assertEqual(("file-1", "unique-1"), result)
        request = opener.requests[0]
        self.assertTrue(request.full_url.endswith("/uploadStickerFile"))
        self.assertIn(b'name="user_id"\r\n\r\n42', request.data)
        self.assertIn(b'name="sticker_format"\r\n\r\nstatic', request.data)
        self.assertIn(b"Content-Type: image/webp", request.data)
        self.assertNotIn("123:safe", repr(transport))

    def test_profile_photo_uses_attach_reference_and_jpeg(self) -> None:
        opener = _Opener(True)
        transport = TelegramMultipartTransport(token="123:safe", opener=opener)

        transport.set_static_profile_photo(jpeg=b"jpeg")

        request = opener.requests[0]
        self.assertIn(b"attach://profile_photo", request.data)
        self.assertIn(b"Content-Type: image/jpeg", request.data)

    def test_transport_error_is_redacted(self) -> None:
        token = "123:never-print-me"

        def fail(_request: Any, _timeout: float) -> Any:
            raise urllib.error.URLError("offline")

        transport = TelegramMultipartTransport(token=token, opener=fail)
        with self.assertRaises(TelegramApiError) as captured:
            transport.set_static_profile_photo(jpeg=b"jpeg")
        self.assertEqual("transport_error", captured.exception.category)
        self.assertNotIn(token, str(captured.exception))


if __name__ == "__main__":
    unittest.main()
