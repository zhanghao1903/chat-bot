from __future__ import annotations

import io
import json
import unittest
import urllib.error
from datetime import UTC, datetime, timedelta

from group_llm_agent.tavily import TavilyApiError, TavilyClient


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.body = io.BytesIO(json.dumps(payload).encode())

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self, maximum: int) -> bytes:
        return self.body.read(maximum)


class RecordingOpener:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.requests = []

    def __call__(self, request, timeout: float):
        self.requests.append((request, timeout))
        return FakeResponse(self.payload)


class TavilyClientTests(unittest.TestCase):
    def test_search_uses_fixed_bounded_contract(self) -> None:
        opener = RecordingOpener(
            {
                "results": [
                    {
                        "title": "Restaurant",
                        "url": "https://example.com/food",
                        "content": "Open for lunch.",
                        "score": 0.9,
                    }
                ],
                "request_id": "request-1",
                "usage": {"credits": 1},
            }
        )
        client = TavilyClient(api_key="secret-key", opener=opener)
        result = client.search(
            query="Shanghai lunch noodles",
            deadline=datetime.now(UTC) + timedelta(seconds=30),
        )
        self.assertEqual(1, len(result.results))
        request, timeout = opener.requests[0]
        self.assertEqual("https://api.tavily.com/search", request.full_url)
        self.assertEqual("Bearer secret-key", request.headers["Authorization"])
        body = json.loads(request.data)
        self.assertEqual("basic", body["search_depth"])
        self.assertEqual(5, body["max_results"])
        self.assertFalse(body["include_answer"])
        self.assertFalse(body["include_raw_content"])
        self.assertTrue(body["safe_search"])
        self.assertLessEqual(timeout, 8)
        self.assertNotIn("secret-key", repr(client))

    def test_extract_uses_one_url_and_bounded_content(self) -> None:
        opener = RecordingOpener(
            {
                "results": [
                    {
                        "url": "https://example.com/food",
                        "raw_content": "Menu and address",
                    }
                ],
                "failed_results": [],
                "request_id": "extract-1",
                "usage": {"credits": 1},
            }
        )
        client = TavilyClient(api_key="secret-key", project_id="project", opener=opener)
        result = client.extract(
            url="https://example.com/food",
            deadline=datetime.now(UTC) + timedelta(seconds=30),
        )
        self.assertEqual("Menu and address", result.result.content)
        request, _ = opener.requests[0]
        self.assertEqual("https://api.tavily.com/extract", request.full_url)
        self.assertEqual("project", request.headers["X-project-id"])
        body = json.loads(request.data)
        self.assertEqual(["https://example.com/food"], body["urls"])
        self.assertEqual("basic", body["extract_depth"])
        self.assertFalse(body["include_images"])

    def test_http_errors_are_redacted_and_classified(self) -> None:
        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 429, "rate", {}, None)

        key = "do-not-print-this-key"
        client = TavilyClient(api_key=key, opener=opener)
        with self.assertRaises(TavilyApiError) as caught:
            client.search(
                query="food",
                deadline=datetime.now(UTC) + timedelta(seconds=30),
            )
        self.assertEqual("rate_limited", caught.exception.category)
        self.assertNotIn(key, str(caught.exception))

    def test_invalid_and_oversized_provider_shapes_fail_closed(self) -> None:
        client = TavilyClient(
            api_key="secret",
            opener=RecordingOpener(
                {
                    "results": [
                        {
                            "title": "x",
                            "url": "https://example.com",
                            "content": "x" * 2_001,
                            "score": 1,
                        }
                    ]
                }
            ),
        )
        with self.assertRaises(TavilyApiError):
            client.search(
                query="food",
                deadline=datetime.now(UTC) + timedelta(seconds=30),
            )


if __name__ == "__main__":
    unittest.main()
