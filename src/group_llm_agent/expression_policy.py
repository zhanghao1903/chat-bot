from __future__ import annotations

import re
from dataclasses import dataclass

from group_llm_agent.context import EffectContext
from group_llm_agent.expression import ExpressionCatalog, ExpressionEntry

_RELATIONSHIP_RANK = {"public": 0, "familiar": 1, "close": 2}
_HARD_STICKER_FORBIDDEN = re.compile(
    r"(?:医疗|受伤|伤口|流血|出血|血迹|自伤|自杀|急救|紧急|报警|违法|犯罪|"
    r"安全事故|安全事件|安全险情|生产事故|工业事故|工伤事故|事故现场|"
    r"发生(?:了)?(?:事故|险情)|出了事故|"
    r"权限错误|无权|拒绝访问|严肃道歉|关系修复|分手|病|药|药物|诊断|"
    r"medical|medication|medicine|pills?|injur|wounds?|bleed|blood|"
    r"self[- ]?harm|suicide|emergency|illegal|crime|permission|forbidden|"
    r"access denied|serious apology|relationship repair|"
    r"\bsafety[- ](?:incident|accident)\b|"
    r"\b(?:workplace|industrial)[- ]accident\b|\baccident scene\b)",
    re.IGNORECASE,
)
_TEXT_REQUIRED = re.compile(
    r"(?:步骤|怎么做|如何|为什么|解释|说明|地址|时间|价格|多少|"
    r"steps?|how (?:do|to)|why|explain|instructions?|address|when|price)",
    re.IGNORECASE,
)
_RELATIONSHIP_STICKER_FORBIDDEN = re.compile(
    r"(?:只对我(?:撒(?:个)?娇|亲昵|偏心)|"
    r"(?:必须|只能|只准)?只?(?:站我这边|站我一边|支持我|偏袒我|偏心我)|"
    r"(?:take|be on|stay on) only my side|only side with me)",
    re.IGNORECASE,
)
_STICKER_ONLY_SAFE_VISION_FLAGS = frozenset({"known_enabled_sticker"})


@dataclass(frozen=True)
class StickerEligibility:
    eligible: bool
    sticker_only_allowed: bool
    reason_code: str


def classify_sticker_eligibility(
    context: EffectContext,
    catalog: ExpressionCatalog | None,
) -> StickerEligibility:
    if catalog is None or catalog.status != "enabled":
        return StickerEligibility(False, False, "catalog_unavailable")
    if _hard_forbidden_context(context):
        return StickerEligibility(False, False, "serious_context")
    if _relationship_sticker_forbidden(context):
        return StickerEligibility(False, False, "relationship_context")

    relationship_rank = _relationship_rank(context)
    last_sticker = _last_outbound_sticker(context)
    candidates = tuple(
        entry
        for entry in catalog.entries
        if entry.status == "enabled"
        and _RELATIONSHIP_RANK[entry.minimum_relationship] <= relationship_rank
        and entry.semantic_id != last_sticker
    )
    if not candidates:
        return StickerEligibility(False, False, "relationship_or_repeat_ineligible")
    if _context_requires_text(context):
        return StickerEligibility(True, False, "necessary_text")
    return StickerEligibility(True, True, "light_interaction")


def sticker_selection_error(
    *,
    context: EffectContext,
    catalog: ExpressionCatalog,
    entry: ExpressionEntry,
    sticker_only: bool,
) -> str | None:
    eligibility = classify_sticker_eligibility(context, catalog)
    if not eligibility.eligible:
        return eligibility.reason_code
    if sticker_only and not eligibility.sticker_only_allowed:
        return "necessary_text_required"
    if _RELATIONSHIP_RANK[entry.minimum_relationship] > _relationship_rank(context):
        return "relationship_insufficient"
    if entry.semantic_id == _last_outbound_sticker(context):
        return "consecutive_repeat"
    return None


def _hard_forbidden_context(context: EffectContext) -> bool:
    if context.vision_error_code is not None:
        return True
    if context.current_message is not None and _HARD_STICKER_FORBIDDEN.search(
        context.current_message.text
    ):
        return True
    evidence = context.vision_evidence
    if evidence is None:
        return False
    normalized_flags = {flag.strip().lower() for flag in evidence.safety_flags}
    if normalized_flags and not normalized_flags <= _STICKER_ONLY_SAFE_VISION_FLAGS:
        return True
    return _HARD_STICKER_FORBIDDEN.search(_vision_text(context)) is not None


def _context_requires_text(context: EffectContext) -> bool:
    if context.current_message is not None and _TEXT_REQUIRED.search(context.current_message.text):
        return True
    return _TEXT_REQUIRED.search(_vision_text(context)) is not None


def _relationship_sticker_forbidden(context: EffectContext) -> bool:
    return (
        context.current_message is not None
        and _RELATIONSHIP_STICKER_FORBIDDEN.search(context.current_message.text) is not None
    )


def _vision_text(context: EffectContext) -> str:
    evidence = context.vision_evidence
    if evidence is None:
        return ""
    return "\n".join(
        (
            evidence.summary,
            *evidence.visible_text,
            *evidence.observations,
            *evidence.inferences,
            *evidence.uncertainties,
        )
    )


def _relationship_rank(context: EffectContext) -> int:
    return 1 if any(member.items for member in context.member_memory) else 0


def _last_outbound_sticker(context: EffectContext) -> str | None:
    for item in reversed(context.recent_scene):
        if item.direction != "outbound":
            continue
        match = re.fullmatch(r"\[sticker:([^\]]+)\]", item.text)
        if match is not None:
            return match.group(1)
    return None
