from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from group_llm_agent.events import EffectRequest
from group_llm_agent.model import FoodChoice, WriterDecision

FOOD_CHOICE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["canonical_key", "label", "description"],
    "properties": {
        "canonical_key": {"type": "string", "minLength": 1, "maxLength": 64},
        "label": {"type": "string", "minLength": 1, "maxLength": 80},
        "description": {"type": "string", "minLength": 1, "maxLength": 240},
    },
}

FOOD_RECOMMENDATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "kind",
        "reason_code",
        "mode",
        "primary",
        "alternatives",
        "source_result_ids",
        "cautious_freshness_note",
    ],
    "properties": {
        "kind": {"const": "food_recommendation"},
        "reason_code": {
            "type": "string",
            "pattern": "^[a-z0-9][a-z0-9_]{0,63}$",
        },
        "mode": {"enum": ["generic", "sourced"]},
        "primary": FOOD_CHOICE_SCHEMA,
        "alternatives": {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "items": FOOD_CHOICE_SCHEMA,
        },
        "source_result_ids": {
            "type": "array",
            "maxItems": 3,
            "items": {"type": "string", "maxLength": 32},
        },
        "cautious_freshness_note": {
            "type": ["string", "null"],
            "maxLength": 240,
        },
    },
}

FOOD_WRITER_PROTOCOL = (
    '{"kind":"food_recommendation","reason_code":"snake_case","mode":"generic|sourced",'
    '"primary":{"canonical_key":"stable_key","label":"dish or merchant",'
    '"description":"short choice reason"},"alternatives":[{"canonical_key":"stable_key",'
    '"label":"choice","description":"short choice reason"},{"canonical_key":"stable_key",'
    '"label":"choice","description":"short choice reason"}],"source_result_ids":[],'
    '"cautious_freshness_note":null}'
)

_GENERIC_CURRENT_FACT_PATTERN = re.compile(
    r"(?:营业|开门|闭店|现价|价格|人均|地址|榜单|排名|附近|离你|到店|外卖|"
    r"open(?:ing)?|closed?|price|address|rank(?:ing)?|nearby|delivery|"
    r"(?:^|\s)[¥￥$]\s*\d|\d+\s*(?:元|块))",
    re.IGNORECASE,
)
_FORBIDDEN_CLAIM_PATTERN = re.compile(
    r"(?:订阅者|订阅名单|某位群友|@\S+|过敏(?:绝对)?安全|保证不过敏|治疗|诊断|"
    r"药物建议|宗教要求.*(?:保证|安全)|替你(?:下单|订座|付款|联系)|"
    r"已经(?:下单|订座|付款|导航|联系)|(?:order|reserve|book|pay|navigate|contact)\s+for\s+you|"
    r"allergy[- ]?safe|medical advice)",
    re.IGNORECASE,
)
_RAW_URL_PATTERN = re.compile(r"https?://|\bwww\.", re.IGNORECASE)

TextValidator = Callable[[str | None], str | None]


@dataclass(frozen=True)
class ValidatedFoodRecommendation:
    text: str
    primary_key: str
    source_urls: tuple[str, ...]


def validate_food_recommendation(
    *,
    decision: WriterDecision,
    request: EffectRequest,
    citation_urls: Mapping[str, str],
    validate_text: TextValidator,
) -> tuple[ValidatedFoodRecommendation | None, str | None]:
    scheduled = request.scheduled
    if scheduled is None:
        return None, "food_not_scheduled"
    primary = decision.food_primary
    alternatives = decision.food_alternatives
    mode = decision.food_mode
    source_result_ids = decision.source_result_ids
    freshness_note = decision.cautious_freshness_note
    if not isinstance(primary, FoodChoice) or len(alternatives) != 2:
        return None, "food_invalid_choices"
    choices = (primary, *alternatives)
    canonical_keys = tuple(choice.canonical_key.casefold() for choice in choices)
    labels = tuple(" ".join(choice.label.casefold().split()) for choice in choices)
    descriptions = tuple(" ".join(choice.description.casefold().split()) for choice in choices)
    if len(set(canonical_keys)) != 3 or len(set(labels)) != 3 or len(set(descriptions)) != 3:
        return None, "food_choices_not_distinct"
    if canonical_keys[0] in {key.casefold() for key in scheduled.recent_primary_keys}:
        return None, "food_primary_recently_used"

    model_text = "\n".join(
        (
            *(choice.label for choice in choices),
            *(choice.description for choice in choices),
            freshness_note or "",
        )
    )
    if _RAW_URL_PATTERN.search(model_text):
        return None, "food_raw_url_forbidden"
    if _FORBIDDEN_CLAIM_PATTERN.search(model_text):
        return None, "food_forbidden_claim"
    validation_error = validate_text(model_text)
    if validation_error is not None:
        return None, validation_error

    source_urls: tuple[str, ...] = ()
    if mode == "generic":
        if source_result_ids or freshness_note is not None:
            return None, "food_generic_source_forbidden"
        if _GENERIC_CURRENT_FACT_PATTERN.search(model_text):
            return None, "food_generic_current_fact"
    elif mode == "sourced":
        if scheduled.location_text is None or not scheduled.location_text.strip():
            return None, "food_sourced_location_required"
        if not 1 <= len(source_result_ids) <= 3:
            return None, "food_sourced_sources_required"
        if freshness_note is None or not freshness_note.strip():
            return None, "food_sourced_caution_required"
        try:
            source_urls = tuple(citation_urls[result_id] for result_id in source_result_ids)
        except KeyError:
            return None, "food_source_not_current"
        if len(set(source_urls)) != len(source_urls):
            return None, "food_duplicate_sources"
    else:
        return None, "food_invalid_mode"

    meal_label = {"lunch": "午餐", "dinner": "晚餐"}.get(
        scheduled.meal_slot,
        scheduled.meal_slot,
    )
    lines = [
        f"到点了，乐枝给{meal_label}出个主意：",
        f"主推：{primary.label} — {primary.description}",
        f"备选一：{alternatives[0].label} — {alternatives[0].description}",
        f"备选二：{alternatives[1].label} — {alternatives[1].description}",
    ]
    if freshness_note is not None:
        lines.append(freshness_note)
    if source_urls:
        lines.append("来源：" + " ".join(source_urls))
    text = "\n".join(lines)
    validation_error = validate_text(text)
    if validation_error is not None:
        return None, validation_error
    return (
        ValidatedFoodRecommendation(
            text=text,
            primary_key=primary.canonical_key,
            source_urls=source_urls,
        ),
        None,
    )
