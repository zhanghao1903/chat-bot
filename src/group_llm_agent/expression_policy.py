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
_CHINESE_EXCLUSIVITY_MARKER = r"(?:必须\s*只|务必\s*只|只能|只准|只许|仅限|只)\s*"
_CHINESE_TO_ME_ACTION = (
    r"(?:"
    r"对我(?:撒(?:个)?娇|亲昵|偏心)(?:就好|就行|而已)?|"
    r"站(?:在)?我(?:这边|一边)|"
    r"(?:支持|喜欢|偏爱|偏袒|偏心|宠)我(?![们的])"
    r"(?:一个人?)?(?:就好|就行|而已)?"
    r")(?=$|[\s，,。.!！？?；;：:、吧嘛呢呀哦啦吗\"'“”‘’）)】\]])"
)
_ENGLISH_TO_ME_ACTION = r"(?:like|love|favor|support|back|side with|stand by|care for)\s+me\b"
_RELATIONSHIP_EXCLUSIVITY_NEGATIONS = (
    re.compile(
        r"(?:别|不要|不是|并非|并不是|不能|不可以|不该|不应该|不应|不必|"
        r"无需|不许|不准)(?:再|再去)?(?:说|是说|代表|意味着)?\s*(?:你\s*)?"
        + _CHINESE_EXCLUSIVITY_MARKER
        + _CHINESE_TO_ME_ACTION,
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:不只|不仅|不光)\s*" + _CHINESE_TO_ME_ACTION,
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:"
        r"(?:do not|don't|never|should not|shouldn't|must not|mustn't)\s+"
        r"(?:only|just)\s+"
        r"|not(?:\s+that)?(?:\s+you)?(?:\s+(?:can|must|should))?\s+only\s+"
        r")" + _ENGLISH_TO_ME_ACTION,
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:do not|don't|never|should not|shouldn't|must not|mustn't)\s+"
        r"(?:take|be on|stay on)\s+(?:only\s+)?my\s+side\b",
        re.IGNORECASE,
    ),
)
_RELATIONSHIP_STICKER_FORBIDDEN = (
    re.compile(
        _CHINESE_EXCLUSIVITY_MARKER + _CHINESE_TO_ME_ACTION,
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:不许|不准|不要|不能|别)(?:再)?(?:站(?:在)?|支持|偏向|偏袒)"
        r"(?:别人|其他人|任何其他人)(?:那边|一边)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:"
        r"(?:only|must only|can only|should only|have to only)\s+" + _ENGLISH_TO_ME_ACTION + r"|"
        r"(?:take|be on|stay on)\s+(?:only\s+)?my\s+side|"
        r"(?:do not|don't|must not)\s+(?:side with|support|back|favor)\s+"
        r"(?:anyone|anybody|someone|others?)\s+else|"
        r"(?:choose|favor|prefer)\s+me\s+over\s+(?:anyone|anybody|others?)"
        r")\b",
        re.IGNORECASE,
    ),
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
    if context.current_message is None:
        return False
    text = context.current_message.text
    negated_spans = tuple(
        match.span()
        for pattern in _RELATIONSHIP_EXCLUSIVITY_NEGATIONS
        for match in pattern.finditer(text)
    )
    for pattern in _RELATIONSHIP_STICKER_FORBIDDEN:
        for match in pattern.finditer(text):
            if not any(
                match.start() < negated_end and match.end() > negated_start
                for negated_start, negated_end in negated_spans
            ):
                return True
    return False


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
