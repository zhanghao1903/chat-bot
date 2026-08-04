from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from group_llm_agent.events import EffectRequest
from group_llm_agent.model import FoodChoice, WriterDecision

GENERIC_DISHES: Mapping[str, str] = {
    "dish:hot-noodles": "热汤面",
    "dish:rice-bowl": "家常盖饭",
    "dish:dumplings": "饺子配小菜",
    "dish:wonton": "馄饨",
    "dish:congee": "粥配小菜",
    "dish:curry-rice": "咖喱饭",
    "dish:rice-noodles": "汤米粉",
    "dish:soup-rice": "汤饭",
    "dish:stir-fry-rice": "炒饭配时蔬",
    "dish:sandwich": "三明治套餐",
    "dish:salad-bowl": "沙拉碗",
    "dish:hotpot": "小火锅",
}

FOOD_REASON_TEXT: Mapping[str, str] = {
    "warming": "来点热乎的，吃起来很踏实。",
    "hearty": "饱足感更强，适合认真吃一顿。",
    "light": "口味清爽，想吃轻一点时很合适。",
    "shareable": "方便一起分着吃，选择也灵活。",
    "quick": "做决定省心，赶时间也比较友好。",
    "variety": "换个方向，给这一餐一点新鲜感。",
}

_CHOICE_TYPES = ("generic_dish", "merchant")
_REASON_TAGS = tuple(FOOD_REASON_TEXT)

FOOD_CHOICE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["choice_type", "generic_dish_id", "source_result_id", "reason_tag"],
    "properties": {
        "choice_type": {"enum": list(_CHOICE_TYPES)},
        "generic_dish_id": {
            "type": ["string", "null"],
            "enum": [*GENERIC_DISHES, None],
        },
        "source_result_id": {
            "type": ["string", "null"],
            "pattern": "^web:[1-9][0-9]{0,5}$",
        },
        "reason_tag": {"enum": list(_REASON_TAGS)},
    },
}

FOOD_RECOMMENDATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "reason_code", "mode", "primary", "alternatives"],
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
    },
}

FOOD_WRITER_PROTOCOL = (
    '{"kind":"food_recommendation","reason_code":"snake_case","mode":"generic|sourced",'
    '"primary":{"choice_type":"generic_dish|merchant","generic_dish_id":'
    '"registered_id_or_null","source_result_id":"current_web_id_or_null",'
    '"reason_tag":"warming|hearty|light|shareable|quick|variety"},'
    '"alternatives":[{"choice_type":"generic_dish|merchant","generic_dish_id":'
    '"registered_id_or_null","source_result_id":"current_web_id_or_null",'
    '"reason_tag":"warming|hearty|light|shareable|quick|variety"},'
    '{"choice_type":"generic_dish|merchant","generic_dish_id":"registered_id_or_null",'
    '"source_result_id":"current_web_id_or_null",'
    '"reason_tag":"warming|hearty|light|shareable|quick|variety"}]}'
)

TextValidator = Callable[[str | None], str | None]


@dataclass(frozen=True)
class FoodCitation:
    url: str


@dataclass(frozen=True)
class ValidatedFoodRecommendation:
    text: str
    primary_key: str
    source_urls: tuple[str, ...]


def validate_food_recommendation(
    *,
    decision: WriterDecision,
    request: EffectRequest,
    citations: Mapping[str, FoodCitation],
    validate_text: TextValidator,
) -> tuple[ValidatedFoodRecommendation | None, str | None]:
    scheduled = request.scheduled
    if scheduled is None:
        return None, "food_not_scheduled"
    primary = decision.food_primary
    alternatives = decision.food_alternatives
    mode = decision.food_mode
    if not isinstance(primary, FoodChoice) or len(alternatives) != 2:
        return None, "food_invalid_choices"
    choices = (primary, *alternatives)

    if mode == "generic":
        rendered = _render_generic_choices(choices)
    elif mode == "sourced":
        if scheduled.location_text is None or not scheduled.location_text.strip():
            return None, "food_sourced_location_required"
        rendered = _render_sourced_choices(choices, citations=citations)
    else:
        return None, "food_invalid_mode"
    if isinstance(rendered, str):
        return None, rendered

    labels, descriptions, canonical_keys, source_urls = rendered
    if len(set(canonical_keys)) != 3 or len(set(labels)) != 3:
        return None, "food_choices_not_distinct"
    if canonical_keys[0].casefold() in {key.casefold() for key in scheduled.recent_primary_keys}:
        return None, "food_primary_recently_used"

    meal_label = {"lunch": "午餐", "dinner": "晚餐"}.get(
        scheduled.meal_slot,
        scheduled.meal_slot,
    )
    lines = [
        f"到点了，乐枝给{meal_label}出个主意：",
        f"主推：{labels[0]} — {descriptions[0]}",
        f"备选一：{labels[1]} — {descriptions[1]}",
        f"备选二：{labels[2]} — {descriptions[2]}",
    ]
    if source_urls:
        lines.append("商家与近期信息可能变化，出发前请再确认。")
        lines.append("来源：" + " ".join(source_urls))
    text = "\n".join(lines)
    validation_error = validate_text(text)
    if validation_error is not None:
        return None, validation_error
    return (
        ValidatedFoodRecommendation(
            text=text,
            primary_key=canonical_keys[0],
            source_urls=source_urls,
        ),
        None,
    )


def _render_generic_choices(
    choices: tuple[FoodChoice, FoodChoice, FoodChoice],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]] | str:
    labels: list[str] = []
    descriptions: list[str] = []
    keys: list[str] = []
    for choice in choices:
        dish_id = choice.generic_dish_id
        if (
            choice.choice_type != "generic_dish"
            or dish_id is None
            or dish_id not in GENERIC_DISHES
            or choice.source_result_id is not None
        ):
            return "food_generic_choice_not_registered"
        labels.append(GENERIC_DISHES[dish_id])
        descriptions.append(FOOD_REASON_TEXT[choice.reason_tag])
        keys.append(dish_id)
    return tuple(labels), tuple(descriptions), tuple(keys), ()


def _render_sourced_choices(
    choices: tuple[FoodChoice, FoodChoice, FoodChoice],
    *,
    citations: Mapping[str, FoodCitation],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]] | str:
    labels: list[str] = []
    descriptions: list[str] = []
    keys: list[str] = []
    urls: list[str] = []
    used_ids: set[str] = set()
    for index, choice in enumerate(choices, start=1):
        if (
            choice.choice_type != "merchant"
            or choice.generic_dish_id is not None
            or choice.source_result_id is None
            or choice.source_result_id in used_ids
        ):
            return "food_sourced_choice_invalid"
        citation = citations.get(choice.source_result_id)
        if citation is None:
            return "food_source_not_current"
        used_ids.add(choice.source_result_id)
        labels.append(("来源商家候选一", "来源商家候选二", "来源商家候选三")[index - 1])
        descriptions.append(FOOD_REASON_TEXT[choice.reason_tag])
        urls.append(citation.url)
        keys.append("merchant:" + hashlib.sha256(citation.url.encode()).hexdigest()[:24])
    if len(set(urls)) != 3:
        return "food_duplicate_sources"
    return tuple(labels), tuple(descriptions), tuple(keys), tuple(urls)
