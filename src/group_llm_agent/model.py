from __future__ import annotations

import http.client
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from group_llm_agent.events import (
    ContinuityDecisionKind,
    ConversationContinuityDecision,
    MemoryCategory,
    ModelErrorCode,
    PersonaSnapshot,
    PersonaTriggerDecision,
    PersonaTriggerKind,
)
from group_llm_agent.memory_safety import resolve_memory_semantic
from group_llm_agent.temporal import FreshnessMode

_MAX_RESPONSE_BYTES = 256_000
_MAX_MESSAGES = 32
_MAX_MESSAGE_CHARS = 80_000
_MAX_TOOL_ARGUMENT_BYTES = 8_000
_MAX_RESPONSE_SCHEMA_BYTES = 32_000
_REASON_CODE = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")
_SAFE_MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_TEMPORAL_CONTEXT_ID = re.compile(r"^time:v1:[0-9a-f]{64}$")
_WEB_RESULT_ID = re.compile(r"^web:[1-9][0-9]{0,2}$")


class ModelRole(StrEnum):
    TRIGGER = "trigger"
    WRITER = "writer"
    RECOGNITION = "recognition"


class WriterDecisionKind(StrEnum):
    CALL_TOOL = "call_tool"
    REPLY = "reply"
    REPLY_WITH_STICKER = "reply_with_sticker"
    STICKER = "sticker"
    SILENCE = "silence"
    FOOD_RECOMMENDATION = "food_recommendation"


class RecognitionOperation(StrEnum):
    ADD = "add"
    STRENGTHEN = "strengthen"
    REVISE = "revise"
    WEAKEN = "weaken"
    REVOKE = "revoke"


class ModelApiError(RuntimeError):
    """A provider failure that is safe to include in logs."""

    def __init__(
        self,
        role: ModelRole,
        category: ModelErrorCode,
        status_code: int | None = None,
    ) -> None:
        self.role = role
        self.category = category
        self.status_code = status_code
        suffix = f" http_status={status_code}" if status_code is not None else ""
        super().__init__(f"model_role={role.value} category={category.value}{suffix}")


class ModelResultError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(f"model_result_error category={category}")


@dataclass(frozen=True)
class ModelMessage:
    role: str
    content: str


@dataclass(frozen=True)
class StructuredModelResult:
    payload: dict[str, Any]


@dataclass(frozen=True)
class FoodChoice:
    choice_type: str
    generic_dish_id: str | None
    source_result_id: str | None
    reason_tag: str


@dataclass(frozen=True)
class WriterDecision:
    kind: WriterDecisionKind
    reason_code: str
    temporal_context_id: str | None = None
    freshness_mode: FreshnessMode | None = None
    source_result_ids: tuple[str, ...] = ()
    text: str | None = None
    sticker_id: str | None = None
    catalog_version: str | None = None
    catalog_digest: str | None = None
    fallback_text: str | None = None
    mood_signal: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] | None = None
    tool_purpose_code: str | None = None
    tool_extension_reason_code: str | None = None
    food_mode: str | None = None
    food_primary: FoodChoice | None = None
    food_alternatives: tuple[FoodChoice, ...] = ()


@dataclass(frozen=True)
class RecognitionProposal:
    subject_user_id: str
    operation: RecognitionOperation
    category: MemoryCategory
    semantic_key: str
    statement: str
    confidence: float
    source_message_ids: tuple[str, ...]
    supersedes_memory_id: str | None


class StructuredModelPort(Protocol):
    def complete(
        self,
        *,
        model_role: ModelRole,
        messages: Sequence[ModelMessage],
        response_schema: Mapping[str, Any],
        deadline: datetime,
        max_output_tokens: int,
        temperature: float,
    ) -> StructuredModelResult: ...


UrlOpener = Callable[[urllib.request.Request, float], Any]


class OpenAICompatibleStructuredModelClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        models: Mapping[ModelRole, str],
        timeout_seconds: float = 30.0,
        opener: UrlOpener | None = None,
    ) -> None:
        self._base_url = _validate_base_url(base_url)
        self._api_key = _validate_secret(api_key)
        self._models = _validate_models(models)
        if timeout_seconds <= 0 or timeout_seconds > 120:
            raise ValueError("timeout_seconds must be in (0, 120]")
        self._timeout_seconds = timeout_seconds
        self._opener = opener or _urlopen

    def __repr__(self) -> str:
        return (
            "OpenAICompatibleStructuredModelClient("
            f"base_url={self._base_url!r}, api_key=<redacted>)"
        )

    def complete(
        self,
        *,
        model_role: ModelRole,
        messages: Sequence[ModelMessage],
        response_schema: Mapping[str, Any],
        deadline: datetime,
        max_output_tokens: int,
        temperature: float,
    ) -> StructuredModelResult:
        _validate_messages(messages)
        if not response_schema:
            raise ValueError("response_schema must not be empty")
        if max_output_tokens <= 0 or max_output_tokens > 8_192:
            raise ValueError("max_output_tokens must be in [1, 8192]")
        if temperature < 0 or temperature > 2:
            raise ValueError("temperature must be in [0, 2]")
        schema_instruction = _response_schema_instruction(response_schema)
        timeout = _remaining_timeout(deadline, maximum=self._timeout_seconds)
        if timeout <= 0:
            raise ModelApiError(model_role, ModelErrorCode.BUDGET_EXHAUSTED)

        body = json.dumps(
            {
                "model": self._models[model_role],
                "messages": _messages_with_response_schema(
                    messages,
                    schema_instruction=schema_instruction,
                ),
                "response_format": {"type": "json_object"},
                "temperature": temperature,
                "max_tokens": max_output_tokens,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self._opener(request, timeout) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            category = _http_error_category(error.code)
            raise ModelApiError(model_role, category, error.code) from None
        except urllib.error.URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                category = ModelErrorCode.TIMEOUT
            else:
                category = ModelErrorCode.PROVIDER_ERROR
            raise ModelApiError(model_role, category) from None
        except TimeoutError:
            raise ModelApiError(model_role, ModelErrorCode.TIMEOUT) from None
        except (http.client.InvalidURL, ValueError):
            raise ModelApiError(model_role, ModelErrorCode.PROVIDER_ERROR) from None
        except (http.client.HTTPException, OSError):
            raise ModelApiError(model_role, ModelErrorCode.PROVIDER_ERROR) from None

        if not isinstance(raw, bytes) or len(raw) > _MAX_RESPONSE_BYTES:
            raise ModelApiError(model_role, ModelErrorCode.INVALID_RESPONSE)
        try:
            envelope = json.loads(raw.decode("utf-8"))
            content = envelope["choices"][0]["message"]["content"]
            payload = json.loads(content)
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            KeyError,
            IndexError,
            TypeError,
        ):
            raise ModelApiError(model_role, ModelErrorCode.INVALID_RESPONSE) from None
        if not isinstance(payload, dict):
            raise ModelApiError(model_role, ModelErrorCode.INVALID_RESPONSE)
        return StructuredModelResult(payload=payload)


def _response_schema_instruction(response_schema: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            response_schema,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        raise ValueError("response_schema must be JSON serializable") from None
    if len(encoded.encode("utf-8")) > _MAX_RESPONSE_SCHEMA_BYTES:
        raise ValueError("response_schema is too large")
    return (
        "OUTPUT_PROTOCOL: Return exactly one JSON object matching "
        "APPLICATION_RESPONSE_SCHEMA. Do not add fields, prose, or Markdown.\n"
        f"APPLICATION_RESPONSE_SCHEMA={encoded}"
    )


def _messages_with_response_schema(
    messages: Sequence[ModelMessage],
    *,
    schema_instruction: str,
) -> list[dict[str, str]]:
    wire = [{"role": message.role, "content": message.content} for message in messages]
    if wire and wire[0]["role"] == "system":
        wire[0] = {
            "role": "system",
            "content": f"{wire[0]['content']}\n{schema_instruction}",
        }
    else:
        wire.insert(0, {"role": "system", "content": schema_instruction})
    return wire


def parse_trigger_decision(
    result: StructuredModelResult,
    *,
    persona: PersonaSnapshot,
) -> PersonaTriggerDecision:
    payload = result.payload
    _require_fields(payload, {"kind", "reason_code"})
    try:
        kind = PersonaTriggerKind(payload["kind"])
    except (TypeError, ValueError):
        raise ModelResultError("invalid_trigger_kind") from None
    reason_code = _parse_reason_code(payload["reason_code"])
    return PersonaTriggerDecision(kind=kind, reason_code=reason_code, persona=persona)


def parse_continuity_decision(
    result: StructuredModelResult,
    *,
    persona: PersonaSnapshot,
) -> ConversationContinuityDecision:
    payload = result.payload
    _require_fields(payload, {"kind", "reason_code"})
    try:
        kind = ContinuityDecisionKind(payload["kind"])
    except (TypeError, ValueError):
        raise ModelResultError("invalid_continuity_kind") from None
    reason_code = _parse_reason_code(payload["reason_code"])
    return ConversationContinuityDecision(kind=kind, reason_code=reason_code, persona=persona)


def parse_writer_decision(
    result: StructuredModelResult,
    *,
    allowed_tools: frozenset[str],
    expected_temporal_context_id: str | None = None,
) -> WriterDecision:
    payload = result.payload
    kind_value = payload.get("kind")
    if not isinstance(kind_value, str):
        raise ModelResultError("invalid_writer_kind")
    try:
        kind = WriterDecisionKind(kind_value)
    except ValueError:
        raise ModelResultError("invalid_writer_kind") from None

    if kind is WriterDecisionKind.REPLY:
        expected = {"kind", "reason_code", "text"}
        _add_temporal_fields(
            payload,
            expected,
            require=expected_temporal_context_id is not None,
            include_freshness=True,
        )
        _require_optional_mood_fields(payload, expected)
        text = _parse_text(payload["text"], maximum=4_096, category="invalid_reply_text")
        temporal_id = _parse_temporal_context_id(payload, expected_temporal_context_id)
        freshness_mode, source_result_ids = _parse_freshness(
            payload,
            required=expected_temporal_context_id is not None,
        )
        return WriterDecision(
            kind=kind,
            reason_code=_parse_reason_code(payload["reason_code"]),
            temporal_context_id=temporal_id,
            freshness_mode=freshness_mode,
            source_result_ids=source_result_ids,
            text=text,
            mood_signal=_parse_mood_signal(payload.get("mood_signal")),
        )
    if kind is WriterDecisionKind.REPLY_WITH_STICKER:
        required_composite = {
            "kind",
            "reason_code",
            "text",
            "sticker_id",
            "catalog_version",
            "catalog_digest",
        }
        _add_temporal_fields(
            payload,
            required_composite,
            require=expected_temporal_context_id is not None,
            include_freshness=True,
        )
        _require_optional_mood_fields(payload, required_composite)
        temporal_id = _parse_temporal_context_id(payload, expected_temporal_context_id)
        freshness_mode, source_result_ids = _parse_freshness(
            payload,
            required=expected_temporal_context_id is not None,
        )
        digest = payload["catalog_digest"]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise ModelResultError("invalid_catalog_digest")
        return WriterDecision(
            kind=kind,
            reason_code=_parse_reason_code(payload["reason_code"]),
            temporal_context_id=temporal_id,
            freshness_mode=freshness_mode,
            source_result_ids=source_result_ids,
            text=_parse_text(payload["text"], maximum=4_096, category="invalid_reply_text"),
            sticker_id=_parse_identifier(
                payload["sticker_id"], maximum=128, category="invalid_sticker_id"
            ),
            catalog_version=_parse_identifier(
                payload["catalog_version"],
                maximum=128,
                category="invalid_catalog_version",
            ),
            catalog_digest=digest,
            mood_signal=_parse_mood_signal(payload.get("mood_signal")),
        )
    if kind is WriterDecisionKind.STICKER:
        required_sticker = {
            "kind",
            "reason_code",
            "sticker_id",
            "catalog_version",
            "catalog_digest",
            "fallback_text",
        }
        _add_temporal_fields(
            payload,
            required_sticker,
            require=expected_temporal_context_id is not None,
        )
        _require_optional_mood_fields(payload, required_sticker)
        temporal_id = _parse_temporal_context_id(payload, expected_temporal_context_id)
        fallback = payload["fallback_text"]
        if fallback is not None:
            fallback = _parse_text(fallback, maximum=4_096, category="invalid_fallback_text")
        digest = payload["catalog_digest"]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise ModelResultError("invalid_catalog_digest")
        return WriterDecision(
            kind=kind,
            reason_code=_parse_reason_code(payload["reason_code"]),
            temporal_context_id=temporal_id,
            sticker_id=_parse_identifier(
                payload["sticker_id"], maximum=128, category="invalid_sticker_id"
            ),
            catalog_version=_parse_identifier(
                payload["catalog_version"], maximum=128, category="invalid_catalog_version"
            ),
            catalog_digest=digest,
            fallback_text=fallback,
            mood_signal=_parse_mood_signal(payload.get("mood_signal")),
        )
    if kind is WriterDecisionKind.SILENCE:
        expected = {"kind", "reason_code"}
        _add_temporal_fields(
            payload,
            expected,
            require=expected_temporal_context_id is not None,
        )
        _require_optional_mood_fields(payload, expected)
        return WriterDecision(
            kind=kind,
            reason_code=_parse_reason_code(payload["reason_code"]),
            temporal_context_id=_parse_temporal_context_id(
                payload, expected_temporal_context_id
            ),
            mood_signal=_parse_mood_signal(payload.get("mood_signal")),
        )
    if kind is WriterDecisionKind.FOOD_RECOMMENDATION:
        expected = {
            "kind",
            "reason_code",
            "mode",
            "primary",
            "alternatives",
        }
        _add_temporal_fields(
            payload,
            expected,
            require=expected_temporal_context_id is not None,
        )
        _require_fields(payload, expected)
        mode = payload["mode"]
        if mode not in {"generic", "sourced"}:
            raise ModelResultError("invalid_food_mode")
        alternatives = payload["alternatives"]
        if not isinstance(alternatives, list) or len(alternatives) != 2:
            raise ModelResultError("invalid_food_alternatives")
        return WriterDecision(
            kind=kind,
            reason_code=_parse_reason_code(payload["reason_code"]),
            temporal_context_id=_parse_temporal_context_id(
                payload, expected_temporal_context_id
            ),
            food_mode=str(mode),
            food_primary=_parse_food_choice(payload["primary"]),
            food_alternatives=tuple(_parse_food_choice(item) for item in alternatives),
        )

    required = {"kind", "reason_code", "tool_name", "tool_arguments", "tool_purpose_code"}
    _add_temporal_fields(
        payload,
        required,
        require=expected_temporal_context_id is not None,
    )
    actual_fields = frozenset(payload)
    if actual_fields not in {
        frozenset(required),
        frozenset((*required, "extension_reason_code")),
    }:
        raise ModelResultError("unexpected_fields")
    tool_name = payload["tool_name"]
    if not isinstance(tool_name, str) or tool_name not in allowed_tools:
        raise ModelResultError("unknown_tool")
    arguments = payload["tool_arguments"]
    if (
        not isinstance(arguments, dict)
        or len(arguments) > 8
        or len(json.dumps(arguments, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        > _MAX_TOOL_ARGUMENT_BYTES
    ):
        raise ModelResultError("invalid_tool_arguments")
    return WriterDecision(
        kind=kind,
        reason_code=_parse_reason_code(payload["reason_code"]),
        temporal_context_id=_parse_temporal_context_id(payload, expected_temporal_context_id),
        tool_name=tool_name,
        tool_arguments=arguments,
        tool_purpose_code=_parse_reason_code(payload["tool_purpose_code"]),
        tool_extension_reason_code=(
            _parse_reason_code(payload["extension_reason_code"])
            if "extension_reason_code" in payload
            else None
        ),
    )


def parse_recognition_proposals(
    result: StructuredModelResult,
    *,
    maximum: int = 8,
) -> tuple[RecognitionProposal, ...]:
    payload = result.payload
    _require_fields(payload, {"proposals"})
    proposals = payload["proposals"]
    if not isinstance(proposals, list) or len(proposals) > maximum:
        raise ModelResultError("invalid_proposals")
    parsed: list[RecognitionProposal] = []
    for item in proposals:
        if not isinstance(item, dict):
            raise ModelResultError("invalid_proposal")
        _require_fields(
            item,
            {
                "subject_user_id",
                "operation",
                "category",
                "semantic_key",
                "confidence",
                "source_message_ids",
                "supersedes_memory_id",
            },
        )
        try:
            operation = RecognitionOperation(item["operation"])
            category = MemoryCategory(item["category"])
        except (TypeError, ValueError):
            raise ModelResultError("invalid_proposal_enum") from None
        confidence = item["confidence"]
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= float(confidence) <= 1
        ):
            raise ModelResultError("invalid_confidence")
        source_ids = item["source_message_ids"]
        if (
            not isinstance(source_ids, list)
            or not source_ids
            or len(source_ids) > 12
            or not all(_is_identifier(value, maximum=64) for value in source_ids)
            or len(set(source_ids)) != len(source_ids)
        ):
            raise ModelResultError("invalid_source_ids")
        supersedes = item["supersedes_memory_id"]
        if supersedes is not None and not _is_identifier(supersedes, maximum=128):
            raise ModelResultError("invalid_supersedes_id")
        semantic_key = _parse_identifier(
            item["semantic_key"],
            maximum=64,
            category="invalid_semantic_key",
        )
        semantic = resolve_memory_semantic(semantic_key, category)
        parsed.append(
            RecognitionProposal(
                subject_user_id=_parse_identifier(
                    item["subject_user_id"],
                    maximum=64,
                    category="invalid_subject",
                ),
                operation=operation,
                category=category,
                semantic_key=semantic_key,
                statement=semantic.statement if semantic is not None else "",
                confidence=float(confidence),
                source_message_ids=tuple(source_ids),
                supersedes_memory_id=supersedes,
            )
        )
    return tuple(parsed)


def _validate_base_url(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(character.isspace() or ord(character) == 127 for character in value)
    ):
        raise ValueError("MODEL_BASE_URL is invalid")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError("MODEL_BASE_URL is invalid") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port is not None
        and not 1 <= port <= 65_535
    ):
        raise ValueError("MODEL_BASE_URL must be a credential-free https URL")
    return value.rstrip("/")


def _validate_secret(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 33 or ord(character) == 127 for character in value)
    ):
        raise ValueError("MODEL_API_KEY is invalid")
    return value


def _validate_models(models: Mapping[ModelRole, str]) -> dict[ModelRole, str]:
    if set(models) != set(ModelRole):
        raise ValueError("A model name is required for every model role")
    result: dict[ModelRole, str] = {}
    for role, value in models.items():
        if not isinstance(value, str) or _SAFE_MODEL_NAME.fullmatch(value) is None:
            raise ValueError(f"Invalid model name for role: {role.value}")
        result[role] = value
    return result


def _validate_messages(messages: Sequence[ModelMessage]) -> None:
    if not messages or len(messages) > _MAX_MESSAGES:
        raise ValueError("messages must contain between 1 and 32 entries")
    total = 0
    for message in messages:
        if message.role not in {"system", "user", "assistant"} or not message.content:
            raise ValueError("Invalid model message")
        total += len(message.content)
    if total > _MAX_MESSAGE_CHARS:
        raise ValueError("Model messages exceed the character budget")


def _remaining_timeout(deadline: datetime, *, maximum: float) -> float:
    if deadline.tzinfo is None:
        raise ValueError("deadline must be timezone-aware")
    return min(maximum, (deadline - datetime.now(UTC)).total_seconds())


def _http_error_category(status_code: int) -> ModelErrorCode:
    if status_code in {401, 403}:
        return ModelErrorCode.AUTHENTICATION
    if status_code == 429:
        return ModelErrorCode.RATE_LIMITED
    return ModelErrorCode.PROVIDER_ERROR


def _require_fields(payload: dict[str, Any], expected: set[str]) -> None:
    if set(payload) != expected:
        raise ModelResultError("unexpected_fields")


def _require_optional_mood_fields(payload: dict[str, Any], expected: set[str]) -> None:
    actual = set(payload)
    if actual != expected and actual != {*expected, "mood_signal"}:
        raise ModelResultError("unexpected_fields")


def _add_temporal_fields(
    payload: dict[str, Any],
    expected: set[str],
    *,
    require: bool,
    include_freshness: bool = False,
) -> None:
    if require or "temporal_context_id" in payload:
        expected.add("temporal_context_id")
    if include_freshness and (require or "freshness" in payload):
        expected.add("freshness")


def _parse_temporal_context_id(
    payload: dict[str, Any],
    expected: str | None,
) -> str | None:
    value = payload.get("temporal_context_id")
    if value is None and expected is None:
        return None
    if not isinstance(value, str) or _TEMPORAL_CONTEXT_ID.fullmatch(value) is None:
        raise ModelResultError("invalid_temporal_context_id")
    if expected is not None and value != expected:
        raise ModelResultError("stale_temporal_context")
    return value


def _parse_freshness(
    payload: dict[str, Any],
    *,
    required: bool,
) -> tuple[FreshnessMode, tuple[str, ...]]:
    value = payload.get("freshness")
    if value is None and not required:
        return FreshnessMode.STABLE, ()
    if not isinstance(value, dict) or set(value) != {"mode", "source_result_ids"}:
        raise ModelResultError("invalid_freshness")
    try:
        mode = FreshnessMode(value["mode"])
    except (TypeError, ValueError):
        raise ModelResultError("invalid_freshness_mode") from None
    source_ids = value["source_result_ids"]
    if (
        not isinstance(source_ids, list)
        or len(source_ids) > 3
        or not all(
            isinstance(item, str) and _WEB_RESULT_ID.fullmatch(item) is not None
            for item in source_ids
        )
        or len(set(source_ids)) != len(source_ids)
    ):
        raise ModelResultError("invalid_freshness_sources")
    if mode in {FreshnessMode.STABLE, FreshnessMode.CLOCK} and source_ids:
        raise ModelResultError("invalid_freshness_sources")
    if mode is FreshnessMode.CURRENT_VERIFIED and not source_ids:
        raise ModelResultError("invalid_freshness_sources")
    return mode, tuple(source_ids)


def _parse_mood_signal(value: object) -> str | None:
    if value is None:
        return None
    if value not in {"neutral", "joyful", "playful", "gentle", "pouty"}:
        raise ModelResultError("invalid_mood_signal")
    return str(value)


def _parse_reason_code(value: Any) -> str:
    if not isinstance(value, str) or _REASON_CODE.fullmatch(value) is None:
        raise ModelResultError("invalid_reason_code")
    return value


def _parse_food_choice(value: object) -> FoodChoice:
    if not isinstance(value, dict):
        raise ModelResultError("invalid_food_choice")
    _require_fields(value, {"choice_type", "generic_dish_id", "source_result_id", "reason_tag"})
    choice_type = value["choice_type"]
    if choice_type not in {"generic_dish", "merchant"}:
        raise ModelResultError("invalid_food_choice_type")
    generic_dish_id = value["generic_dish_id"]
    if generic_dish_id is not None and not _is_identifier(generic_dish_id, maximum=64):
        raise ModelResultError("invalid_food_generic_dish_id")
    source_result_id = value["source_result_id"]
    if source_result_id is not None and not _is_identifier(source_result_id, maximum=32):
        raise ModelResultError("invalid_food_source_result_id")
    reason_tag = value["reason_tag"]
    if reason_tag not in {"warming", "hearty", "light", "shareable", "quick", "variety"}:
        raise ModelResultError("invalid_food_reason_tag")
    return FoodChoice(
        choice_type=str(choice_type),
        generic_dish_id=str(generic_dish_id) if generic_dish_id is not None else None,
        source_result_id=str(source_result_id) if source_result_id is not None else None,
        reason_tag=str(reason_tag),
    )


def _parse_text(value: Any, *, maximum: int, category: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ModelResultError(category)
    return value


def _parse_identifier(value: Any, *, maximum: int, category: str) -> str:
    if not _is_identifier(value, maximum=maximum):
        raise ModelResultError(category)
    return str(value)


def _is_identifier(value: Any, *, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= maximum
        and all(character.isalnum() or character in "-_:." for character in value)
    )


def _urlopen(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)
