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
_CHINESE_EXCLUSIVITY_MARKER = (
    r"(?:必须\s*(?:只|只能)|务必\s*只|一定(?:要)?\s*(?:只|只能)|"
    r"(?:要|得)\s*只|只能够|只能|只允许|只可以|只需要|只用|只可|只准|"
    r"只许|只要|仅限|仅|只)\s*"
)
_CHINESE_ADDRESSEE = r"(?:你|乐枝)\s*"
_CHINESE_TO_ME_ACTION = (
    r"(?:"
    r"对我(?:(?:一个人?|一人)?好|撒(?:个)?娇|亲昵|偏心)"
    r"(?:就好|就行|而已)?|"
    r"(?:跟|和)我(?:一个人?|一人)?(?:玩|聊天|说话)|"
    r"站(?:在)?我(?:这边|一边)|"
    r"(?:支持|喜欢|爱|偏爱|偏袒|偏心|宠|陪|关心|在乎|理|搭理|夸|哄|"
    r"选|选择|向着|护着)我(?![们的])"
    r"(?:一个人?|一人)?(?:就好|就行|就可以了?|而已|好吗|好不好|行吗|"
    r"行不行|可以吗|可以不|才行|才可以|才对吗?|就够了?|就足够了?|"
    r"懂吗|知道吗)?"
    r")(?=$|[\s，,。.!！？?；;：:、吧嘛呢呀哦啦吗\"'“”‘’）)】\]])"
)
_ENGLISH_RELATIONSHIP_ACTION = (
    r"(?:like|love|favor|support|back|side with|stand by|care for|care about|"
    r"talk to|chat with|play with|choose|praise|comfort)"
)
_ENGLISH_TO_ME_ACTION = _ENGLISH_RELATIONSHIP_ACTION + r"\s+me\b"
_ENGLISH_MODAL_ONLY = (
    r"(?:only|(?:must|can|could|may|might|should|will|would|shall|need|"
    r"need to|have to)\s+only|(?:am|are|is)\s+only\s+"
    r"(?:allowed|permitted)\s+to)"
)
_RELATIONSHIP_CLAUSE_BREAK = re.compile(r"[，,。.!！？?；;\n]")
_RELATIONSHIP_EXCLUSIVITY_NEGATIONS = (
    re.compile(
        r"(?:别|不要|不是|并非|并不是|不能|不可以|不该|不应该|不应|不必|"
        r"不用|不需要|无需|没必要|没有必要|不许|不准)(?:再|再去)?\s*"
        r"(?:(?:说|要求|让|希望)\s*)?(?:你\s*)?"
        + _CHINESE_EXCLUSIVITY_MARKER
        + r"(?:"
        + _CHINESE_ADDRESSEE
        + r")?"
        + _CHINESE_TO_ME_ACTION,
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:不只|不仅|不光)\s*" + _CHINESE_TO_ME_ACTION,
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:"
        r"(?:do not|don['’]t|cannot|can not|can['’]t|never|should not|"
        r"shouldn['’]t|must not|mustn['’]t)\s+"
        r"(?:only|just)\s+"
        r"|not(?:\s+that)?(?:\s+you)?(?:\s+(?:can|must|should))?\s+only\s+"
        r")" + _ENGLISH_TO_ME_ACTION,
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:"
        r"(?:do not|don['’]t)\s+(?:have|need)\s+to|"
        r"(?:are not|aren['’]t|do not|don['’]t)\s+(?:required|expected)\s+to|"
        r"need not|needn['’]t|it(?:'s| is)\s+not\s+that\s+you\s+"
        r"(?:must|should|have to)"
        r")\s+(?:only\s+)?" + _ENGLISH_RELATIONSHIP_ACTION + r"\s+(?:only\s+)?me\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:do not|don['’]t|cannot|can not|can['’]t|never|should not|"
        r"shouldn['’]t|must not|mustn['’]t)\s+"
        r"(?:take|be on|stay on)\s+(?:only\s+)?my\s+side\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:do not|don['’]t|cannot|can not|can['’]t|never|should not|"
        r"shouldn['’]t|must not|mustn['’]t)\s+" + _ENGLISH_RELATIONSHIP_ACTION + r"\s+only\s+me\b",
        re.IGNORECASE,
    ),
)
_RELATIONSHIP_STICKER_FORBIDDEN = (
    re.compile(
        _CHINESE_EXCLUSIVITY_MARKER + r"(?:" + _CHINESE_ADDRESSEE + r")?" + _CHINESE_TO_ME_ACTION,
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:不许|不准|不允许|不要|不能|不可以|不该|不应该|别)(?:再)?"
        r"(?:" + _CHINESE_ADDRESSEE + r")?"
        r"(?:"
        r"站(?:在)?(?:别人|其他人|任何其他人)(?:那边|一边)?|"
        r"(?:跟|和)(?:别人|其他人|任何其他人)(?:玩|聊天|说话)|"
        r"对(?:别人|其他人|任何其他人)好|"
        r"(?:支持|喜欢|爱|偏爱|偏向|偏袒|偏心|宠|陪|关心|在乎|理|搭理|"
        r"夸|哄|选|选择|向着|护着)(?:别人|其他人|任何其他人)"
        r")",
        re.IGNORECASE,
    ),
    re.compile(
        (
            r"\b(?:"
            + _ENGLISH_MODAL_ONLY
            + r"\s+"
            + _ENGLISH_TO_ME_ACTION
            + r"|"
            + _ENGLISH_RELATIONSHIP_ACTION
            + r"\s+only\s+me|"
            + _ENGLISH_TO_ME_ACTION
            + r"\s+(?:alone|exclusively)|"
            r"only\s+(?:you|lezhi)(?:\s+(?:can|could|may|might|must|should|"
            r"will|would|shall))?\s+" + _ENGLISH_TO_ME_ACTION + r"|"
            r"(?:am|are|is)\s+you\s+only\s+(?:allowed|permitted)\s+to\s+"
            + _ENGLISH_TO_ME_ACTION
            + r"|"
            r"(?:side|stand)\s+only\s+with\s+me|"
            r"(?:take|be on|stay on)\s+(?:only\s+)?my\s+side|"
            r"(?:do not|don['’]t|cannot|can not|can['’]t|must not|mustn['’]t|"
            r"should not|shouldn['’]t|may not|never|not allowed to)\s+"
            + _ENGLISH_RELATIONSHIP_ACTION
            + r"\s+"
            r"(?:(?:anyone|anybody|someone|no one|nobody)\s+else|others?|"
            r"any other (?:person|member))|" + _ENGLISH_RELATIONSHIP_ACTION + r"\s+me\s+(?:and\s+)?"
            r"(?:no one|nobody)\s+else|"
            r"(?:choose|favor|prefer)\s+me\s+over\s+(?:anyone|anybody|others?)"
            r")\b"
        ),
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
        if not _rhetorical_exclusivity_negation(text, match)
    )
    for pattern in _RELATIONSHIP_STICKER_FORBIDDEN:
        for match in pattern.finditer(text):
            if not _relationship_match_has_direct_subject(text, match):
                continue
            if not any(
                match.start() < negated_end and match.end() > negated_start
                for negated_start, negated_end in negated_spans
            ):
                return True
    return False


def _relationship_match_has_direct_subject(text: str, match: re.Match[str]) -> bool:
    prefix = _RELATIONSHIP_CLAUSE_BREAK.split(text[: match.start()])[-1]
    prefix = prefix.strip(" \t\r\"'“”‘’（）()【】[]")
    if not prefix:
        return True

    matched_text = match.group(0)
    if re.search(r"[\u3400-\u9fff]", matched_text):
        prefix = re.sub(r"^(?:但|但是|不过|而且|所以|然后)\s*", "", prefix)
        if prefix in {"你", "乐枝", "乐枝你", "请", "请你", "拜托", "拜托你"}:
            return True
        if re.fullmatch(
            r"(?:(?:你|乐枝)\s*)?(?:能不能|可不可以|可以不可以|能否|是否|"
            r"愿不愿意|愿意|会不会|会|肯不肯|肯|答不答应|答应|"
            r"应该不应该|应不应该|为什么|凭什么|怎么能|怎么可以|能|可以|"
            r"是不是)",
            prefix,
        ):
            return True
        if re.fullmatch(r"我(?:希望|想让|要|要求|只想让)你", prefix):
            return True
        if prefix == "我" and re.match(
            r"(?:不许|不准|不允许|不要|不能|不可以|不该|不应该|别)(?:再)?你",
            matched_text,
        ):
            return True
        return _rhetorical_exclusivity_negation(text, match) and (
            re.fullmatch(
                r"(?:我|你)?不是(?:说|要求|让|希望)(?:你|乐枝)?",
                prefix,
            )
            is not None
            or re.fullmatch(
                r"(?:难道|难不成|岂不是)(?:你|乐枝).+",
                prefix,
            )
            is not None
        )

    normalized = re.sub(r"^(?:but|and|so|then)\s+", "", prefix.lower())
    if re.match(r"only\s+(?:you|lezhi)\b", matched_text, re.IGNORECASE) and re.fullmatch(
        r"(?:(?:why|how come)\s+)?(?:can|could|would|will|should|may|might|must)",
        normalized,
    ):
        return True
    return (
        re.fullmatch(
            r"(?:please|(?:you|lezhi)(?:\s+(?:can|could|may|might|must|should|"
            r"will|would|shall|need to|have to|are allowed to|are permitted to))?|"
            r"(?:(?:why|how come)\s+)?(?:can|could|would|will|should|may|might|"
            r"must|do|does|did|are|is|was|were|can['’]t|couldn['’]t|"
            r"wouldn['’]t|won['’]t|shouldn['’]t|don['’]t|doesn['’]t|"
            r"didn['’]t|aren['’]t|isn['’]t)\s+(?:you|lezhi)"
            r"(?:\s+(?:allowed|permitted|"
            r"supposed|expected)\s+to)?|"
            r"(?:why|how come)\s+(?:you|lezhi)|"
            r"(?:didn['’]t|did not)\s+you\s+(?:say|tell me)\s+you|"
            r"(?:i|we)\s+(?:want|need|expect|ask|require|would like)\s+you(?:\s+to)?)",
            normalized,
        )
        is not None
    )


def _rhetorical_exclusivity_negation(text: str, match: re.Match[str]) -> bool:
    clause_prefix = _RELATIONSHIP_CLAUSE_BREAK.split(text[: match.start()])[-1]
    if any(marker in clause_prefix for marker in ("难道", "难不成", "岂不是")):
        return True
    suffix = text[match.end() :].lstrip()
    return suffix.startswith(("吗", "嘛", "？", "?"))


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
