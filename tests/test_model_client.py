from __future__ import annotations

import io
import json
import unittest
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any, Self

from group_llm_agent.events import ModelErrorCode, PersonaSnapshot
from group_llm_agent.model import (
    ModelApiError,
    ModelMessage,
    ModelResultError,
    ModelRole,
    OpenAICompatibleStructuredModelClient,
    StructuredModelResult,
    WriterDecisionKind,
    parse_trigger_decision,
    parse_writer_decision,
)

_API_KEY = "test-secret-key-never-log"
_MODELS = {
    ModelRole.TRIGGER: "test-trigger",
    ModelRole.WRITER: "test-writer",
    ModelRole.RECOGNITION: "test-recognition",
}


class FakeResponse:
    def __init__(self, body: bytes, *, read_error: Exception | None = None) -> None:
        self.body = body
        self.read_error = read_error

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        if self.read_error is not None:
            raise self.read_error
        return self.body[:size]


class RecordingOpener:
    def __init__(
        self,
        response: FakeResponse | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.requests: list[tuple[urllib.request.Request, float]] = []

    def __call__(
        self,
        request: urllib.request.Request,
        timeout: float,
    ) -> FakeResponse:
        self.requests.append((request, timeout))
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def _response(payload: dict[str, Any]) -> FakeResponse:
    content = json.dumps(payload, separators=(",", ":"))
    body = json.dumps(
        {"choices": [{"message": {"content": content}}]},
        separators=(",", ":"),
    ).encode("utf-8")
    return FakeResponse(body)


def _client(opener: RecordingOpener) -> OpenAICompatibleStructuredModelClient:
    return OpenAICompatibleStructuredModelClient(
        base_url="https://models.example.test/v1",
        api_key=_API_KEY,
        models=_MODELS,
        opener=opener,
    )


def _complete(
    client: OpenAICompatibleStructuredModelClient,
) -> StructuredModelResult:
    return client.complete(
        model_role=ModelRole.WRITER,
        messages=(ModelMessage("user", "bounded test input"),),
        response_schema={"type": "object"},
        deadline=datetime.now(UTC) + timedelta(seconds=5),
        max_output_tokens=200,
        temperature=0.2,
    )


class ModelClientTests(unittest.TestCase):
    def test_successful_json_object_request_and_safe_repr(self) -> None:
        opener = RecordingOpener(_response({"kind": "silence", "reason_code": "no_value"}))
        client = _client(opener)

        result = _complete(client)

        self.assertEqual("silence", result.payload["kind"])
        self.assertNotIn(_API_KEY, repr(client))
        request, timeout = opener.requests[0]
        self.assertEqual(
            "https://models.example.test/v1/chat/completions",
            request.full_url,
        )
        self.assertGreater(timeout, 0)
        sent = json.loads(request.data.decode("utf-8"))  # type: ignore[union-attr]
        self.assertEqual({"type": "json_object"}, sent["response_format"])
        self.assertEqual("test-writer", sent["model"])

    def test_http_timeout_and_malformed_body_are_redacted(self) -> None:
        cases = (
            RecordingOpener(
                error=urllib.error.HTTPError(
                    "https://models.example.test/v1/chat/completions",
                    401,
                    "header may be unsafe",
                    {},
                    io.BytesIO(b"provider body"),
                )
            ),
            RecordingOpener(FakeResponse(b"", read_error=TimeoutError(_API_KEY))),
            RecordingOpener(FakeResponse(b"{malformed")),
        )
        expected = (
            ModelErrorCode.AUTHENTICATION,
            ModelErrorCode.TIMEOUT,
            ModelErrorCode.INVALID_RESPONSE,
        )
        for opener, category in zip(cases, expected, strict=True):
            with self.subTest(category=category):
                with self.assertRaises(ModelApiError) as raised:
                    _complete(_client(opener))
                self.assertEqual(category, raised.exception.category)
                self.assertNotIn(_API_KEY, str(raised.exception))
                self.assertIsNone(raised.exception.__cause__)

    def test_invalid_url_and_secret_are_rejected_without_echoing_values(self) -> None:
        unsafe_base = f"https://{_API_KEY}@models.example.test/v1"
        with self.assertRaises(ValueError) as base_error:
            OpenAICompatibleStructuredModelClient(
                base_url=unsafe_base,
                api_key=_API_KEY,
                models=_MODELS,
            )
        self.assertNotIn(_API_KEY, str(base_error.exception))

        with self.assertRaises(ValueError) as key_error:
            OpenAICompatibleStructuredModelClient(
                base_url="https://models.example.test/v1",
                api_key=f"{_API_KEY}\nunsafe",
                models=_MODELS,
            )
        self.assertNotIn(_API_KEY, str(key_error.exception))

    def test_expired_deadline_never_opens_network(self) -> None:
        opener = RecordingOpener(_response({"kind": "silence", "reason_code": "late"}))
        client = _client(opener)
        with self.assertRaises(ModelApiError) as raised:
            client.complete(
                model_role=ModelRole.TRIGGER,
                messages=(ModelMessage("user", "test"),),
                response_schema={"type": "object"},
                deadline=datetime.now(UTC) - timedelta(seconds=1),
                max_output_tokens=20,
                temperature=0,
            )
        self.assertEqual(ModelErrorCode.BUDGET_EXHAUSTED, raised.exception.category)
        self.assertEqual([], opener.requests)


class ModelResultParserTests(unittest.TestCase):
    def test_trigger_parser_carries_exact_persona_snapshot(self) -> None:
        persona = PersonaSnapshot("test", "v1", "digest")
        decision = parse_trigger_decision(
            StructuredModelResult({"kind": "engage", "reason_code": "useful_opening"}),
            persona=persona,
        )
        self.assertEqual(persona, decision.persona)
        self.assertEqual("engage", decision.kind.value)

    def test_writer_parser_rejects_provider_injected_tool_name(self) -> None:
        result = StructuredModelResult(
            {
                "kind": "call_tool",
                "reason_code": "need_context",
                "tool_name": "send_telegram_message",
                "tool_arguments": {"chat_id": "-999"},
                "tool_purpose_code": "send_now",
            }
        )
        with self.assertRaisesRegex(ModelResultError, "unknown_tool"):
            parse_writer_decision(
                result,
                allowed_tools=frozenset({"lookup_member_memory", "search_recent_group_messages"}),
            )

    def test_writer_reply_parser_rejects_unknown_fields(self) -> None:
        result = StructuredModelResult(
            {
                "kind": "reply",
                "reason_code": "answer",
                "text": "hello",
                "telegram_action": "send",
            }
        )
        with self.assertRaisesRegex(ModelResultError, "unexpected_fields"):
            parse_writer_decision(result, allowed_tools=frozenset())

        valid = parse_writer_decision(
            StructuredModelResult({"kind": "reply", "reason_code": "answer", "text": "hello"}),
            allowed_tools=frozenset(),
        )
        self.assertEqual(WriterDecisionKind.REPLY, valid.kind)


if __name__ == "__main__":
    unittest.main()
