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
        "required": ["kind", "reason_code", *required],
        "properties": {
            "kind": {"const": kind},
            "reason_code": _REASON_CODE,
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
            required=("text",),
            properties={"text": {"type": "string", "minLength": 1, "maxLength": 4096}},
        ),
        _object_schema(
            kind="reply_with_sticker",
            required=("text", "sticker_id", "catalog_version", "catalog_digest"),
            properties={
                "text": {"type": "string", "minLength": 1, "maxLength": 4096},
                **_CATALOG_FIELDS,
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
        '{"kind":"reply","reason_code":"snake_case","text":"reply text",'
        '"mood_signal":"neutral"}\n'
        '{"kind":"reply_with_sticker","reason_code":"snake_case",'
        '"text":"one Telegram text message","sticker_id":"semantic_id",'
        '"catalog_version":"version","catalog_digest":"sha256",'
        '"mood_signal":"neutral"}\n'
        '{"kind":"silence","reason_code":"snake_case","mood_signal":"neutral"}\n'
        '{"kind":"sticker","reason_code":"snake_case","sticker_id":"semantic_id",'
        '"catalog_version":"version","catalog_digest":"sha256",'
        '"fallback_text":null,"mood_signal":"neutral"}\n'
    )
