from __future__ import annotations

from group_llm_agent.food_recommendation import FOOD_RECOMMENDATION_SCHEMA

_REASON_CODE = {
    "type": "string",
    "pattern": "^[a-z0-9][a-z0-9_]{0,63}$",
}
_MOOD_SIGNAL = {
    "type": "string",
    "enum": ["neutral", "joyful", "playful", "gentle", "pouty"],
}
_TEMPORAL_CONTEXT_ID = {
    "type": "string",
    "pattern": "^time:v1:[0-9a-f]{64}$",
}
_FRESHNESS = {
    "type": "object",
    "additionalProperties": False,
    "required": ["mode", "source_result_ids"],
    "properties": {
        "mode": {
            "enum": ["stable", "clock", "current_verified", "current_unverified"]
        },
        "source_result_ids": {
            "type": "array",
            "minItems": 0,
            "maxItems": 3,
            "uniqueItems": True,
            "items": {"type": "string", "pattern": "^web:[1-9][0-9]{0,2}$"},
        },
    },
}
_CATALOG_FIELDS = {
    "sticker_id": {"type": "string", "minLength": 1, "maxLength": 128},
    "catalog_version": {"type": "string", "minLength": 1, "maxLength": 128},
    "catalog_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
}


def _object_schema(
    *,
    kind: str,
    required: tuple[str, ...],
    properties: dict[str, object],
    include_mood: bool = True,
) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", "reason_code", "temporal_context_id", *required],
        "properties": {
            "kind": {"const": kind},
            "reason_code": _REASON_CODE,
            "temporal_context_id": _TEMPORAL_CONTEXT_ID,
            **properties,
            **({"mood_signal": _MOOD_SIGNAL} if include_mood else {}),
        },
    }


WRITER_RESPONSE_SCHEMA = {
    "type": "object",
    "oneOf": [
        _object_schema(
            kind="sticker",
            required=(
                "sticker_id",
                "catalog_version",
                "catalog_digest",
                "fallback_text",
            ),
            properties={
                **_CATALOG_FIELDS,
                "fallback_text": {"type": ["string", "null"], "maxLength": 4096},
            },
        ),
        _object_schema(
            kind="reply",
            required=("text", "freshness"),
            properties={
                "text": {"type": "string", "minLength": 1, "maxLength": 4096},
                "freshness": _FRESHNESS,
            },
        ),
        _object_schema(
            kind="reply_with_sticker",
            required=(
                "text",
                "sticker_id",
                "catalog_version",
                "catalog_digest",
                "freshness",
            ),
            properties={
                "text": {"type": "string", "minLength": 1, "maxLength": 4096},
                **_CATALOG_FIELDS,
                "freshness": _FRESHNESS,
            },
        ),
        _object_schema(kind="silence", required=(), properties={}),
        FOOD_RECOMMENDATION_SCHEMA,
        _object_schema(
            kind="call_tool",
            required=("tool_name", "tool_arguments", "tool_purpose_code"),
            properties={
                "tool_name": {"type": "string"},
                "tool_arguments": {"type": "object", "maxProperties": 8},
                "tool_purpose_code": _REASON_CODE,
                "extension_reason_code": _REASON_CODE,
            },
            include_mood=False,
        ),
    ],
}

WRITER_FINAL_KINDS = frozenset(
    {"reply", "reply_with_sticker", "sticker", "food_recommendation", "silence"}
)


def writer_protocol_text() -> str:
    return (
        "Return exactly one JSON object in one of these shapes:\n"
        '{"kind":"reply","reason_code":"snake_case",'
        '"temporal_context_id":"current_time_context_id","text":"reply text",'
        '"freshness":{"mode":"stable|clock|current_verified|current_unverified",'
        '"source_result_ids":[]},'
        '"mood_signal":"neutral"}\n'
        '{"kind":"reply_with_sticker","reason_code":"snake_case",'
        '"temporal_context_id":"current_time_context_id",'
        '"text":"one Telegram text message","sticker_id":"semantic_id",'
        '"catalog_version":"version","catalog_digest":"sha256",'
        '"freshness":{"mode":"stable|clock|current_verified|current_unverified",'
        '"source_result_ids":[]},'
        '"mood_signal":"neutral"}\n'
        '{"kind":"silence","reason_code":"snake_case",'
        '"temporal_context_id":"current_time_context_id","mood_signal":"neutral"}\n'
        '{"kind":"sticker","reason_code":"snake_case","sticker_id":"semantic_id",'
        '"temporal_context_id":"current_time_context_id",'
        '"catalog_version":"version","catalog_digest":"sha256",'
        '"fallback_text":null,"mood_signal":"neutral"}\n'
    )
