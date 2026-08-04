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
    r"只许|只要|只会|仅限|仅|只)\s*"
)
_CHINESE_ADDRESSEE = r"(?:你|乐枝)\s*"
_CHINESE_DIRECT_PREFIX_TOKENS = tuple(
    sorted(
        {
            "可以不可以",
            "应该不应该",
            "应不应该",
            "愿不愿意",
            "答不答应",
            "可不可以",
            "能不能",
            "会不会",
            "肯不肯",
            "从今以后",
            "从现在起",
            "从现在开始",
            "拜托",
            "麻烦",
            "恳请",
            "为什么",
            "怎么可以",
            "怎么能",
            "是不是",
            "愿意",
            "答应",
            "可以",
            "能否",
            "是否",
            "应该",
            "必须",
            "务必",
            "一定",
            "会",
            "肯",
            "请",
            "求",
            "以后",
            "今后",
            "将来",
            "现在",
            "永远",
            "一直",
            "始终",
            "往后",
            "从此",
            "真的",
            "真",
            "到底",
            "要",
            "得",
            "还",
            "再",
            "也",
            "都",
            "乐枝你",
            "乐枝",
            "你",
        },
        key=len,
        reverse=True,
    )
)
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
_ENGLISH_PREFIX_MODIFIER = (
    r"(?:(?:always|forever|ever|still|now|really|truly|actually|please|kindly|"
    r"maybe|perhaps|just|from now on|going forward|in the future)\s*)*"
)
_ENGLISH_POST_ONLY_MODIFIER = r"(?:(?:ever|always|really|truly|just)\s+)*"
_ENGLISH_DIRECT_PREFIX_TOKENS = tuple(
    sorted(
        {
            "from now on",
            "going forward",
            "in the future",
            "how come",
            "need to",
            "have to",
            "would like",
            "at least",
            "can't",
            "couldn't",
            "wouldn't",
            "won't",
            "shouldn't",
            "don't",
            "doesn't",
            "didn't",
            "aren't",
            "isn't",
            "please",
            "kindly",
            "maybe",
            "perhaps",
            "possibly",
            "just",
            "always",
            "forever",
            "ever",
            "still",
            "now",
            "really",
            "truly",
            "actually",
            "why",
            "can",
            "could",
            "would",
            "will",
            "should",
            "may",
            "might",
            "must",
            "do",
            "does",
            "did",
            "are",
            "is",
            "was",
            "were",
            "shall",
            "need",
            "have",
            "am",
            "allowed",
            "permitted",
            "supposed",
            "expected",
            "to",
            "you",
            "lezhi",
        },
        key=len,
        reverse=True,
    )
)
_CHINESE_BENIGN_RELATIONSHIP_SUBJECTS = tuple(
    sorted(
        {
            *(
                f"{determiner}{noun}"
                for determiner in ("这个", "该", "本", "那个", "此")
                for noun in (
                    "应用",
                    "程序",
                    "软件",
                    "功能",
                    "系统",
                    "设备",
                    "服务",
                    "接口",
                    "工具",
                    "平台",
                    "账号",
                    "账户",
                    "版本",
                    "方案",
                    "模块",
                    "代码",
                    "文档",
                )
            ),
            "他",
            "她",
            "他们",
            "她们",
            "其他人",
            "别人",
            "某人",
            "这位成员",
            "那位成员",
            "其他成员",
            "另一位成员",
            "我爸",
            "我妈",
            "我爸爸",
            "我妈妈",
            "我的朋友",
            "我的同事",
            "我的家人",
        },
        key=len,
        reverse=True,
    )
)
_ENGLISH_BENIGN_RELATIONSHIP_SUBJECTS = tuple(
    sorted(
        {
            *(
                f"{determiner} {noun}"
                for determiner in ("this", "that", "the", "an", "another")
                for noun in (
                    "app",
                    "application",
                    "program",
                    "feature",
                    "function",
                    "system",
                    "device",
                    "service",
                    "interface",
                    "tool",
                    "platform",
                    "account",
                    "version",
                    "plan",
                    "module",
                    "code",
                    "document",
                )
            ),
            "he",
            "she",
            "they",
            "this member",
            "that member",
            "the member",
            "another member",
            "other members",
            "someone else",
            "my father",
            "my mother",
            "my friend",
            "my colleague",
            "my family",
        },
        key=len,
        reverse=True,
    )
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
            + _ENGLISH_POST_ONLY_MODIFIER
            + _ENGLISH_TO_ME_ACTION
            + r"|"
            + _ENGLISH_RELATIONSHIP_ACTION
            + r"\s+only\s+me|"
            + _ENGLISH_TO_ME_ACTION
            + r"\s+(?:alone|exclusively)|"
            r"only\s+(?:you|lezhi)(?:\s+(?:can|could|may|might|must|should|"
            r"will|would|shall))?\s+" + _ENGLISH_TO_ME_ACTION + r"|"
            r"(?:am|are|is)\s+(?:you|lezhi)\s+"
            + _ENGLISH_PREFIX_MODIFIER
            + r"only\s+(?:allowed|permitted)\s+to\s+"
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
            if any(
                match.start() < negated_end and match.end() > negated_start
                for negated_start, negated_end in negated_spans
            ):
                continue
            if _relationship_match_has_benign_subject(text, match):
                continue
            return True
    return False


def _relationship_match_has_benign_subject(text: str, match: re.Match[str]) -> bool:
    prefix = _RELATIONSHIP_CLAUSE_BREAK.split(text[: match.start()])[-1]
    prefix = prefix.strip(" \t\r\"'“”‘’（）()【】[]")
    if not prefix:
        return False
    if re.search(r"[\u3400-\u9fff]", match.group(0)):
        compact = re.sub(r"\s+", "", prefix)
        return _has_bounded_benign_subject(
            compact,
            _CHINESE_BENIGN_RELATIONSHIP_SUBJECTS,
            _CHINESE_DIRECT_PREFIX_TOKENS,
            spaced=False,
        )
    normalized = re.sub(r"\s+", " ", prefix.replace("’", "'").strip().lower())
    return _has_bounded_benign_subject(
        normalized,
        _ENGLISH_BENIGN_RELATIONSHIP_SUBJECTS,
        _ENGLISH_DIRECT_PREFIX_TOKENS,
        spaced=True,
    )


def _consume_prefix_tokens(
    value: str,
    tokens: tuple[str, ...],
    *,
    spaced: bool,
) -> bool:
    if not value:
        return False
    position = 0
    while position < len(value):
        for token in tokens:
            if not value.startswith(token, position):
                continue
            end = position + len(token)
            if spaced and end < len(value) and value[end] != " ":
                continue
            position = end
            if spaced:
                while position < len(value) and value[position] == " ":
                    position += 1
            break
        else:
            return False
    return True


def _has_bounded_benign_subject(
    value: str,
    subjects: tuple[str, ...],
    prefix_tokens: tuple[str, ...],
    *,
    spaced: bool,
) -> bool:
    for subject in subjects:
        search_from = 0
        while True:
            start = value.find(subject, search_from)
            if start < 0:
                break
            end = start + len(subject)
            search_from = start + 1
            if spaced and (
                (start > 0 and value[start - 1] != " ") or (end < len(value) and value[end] != " ")
            ):
                continue
            before = value[:start].strip()
            after = value[end:].strip()
            if (not before or _consume_prefix_tokens(before, prefix_tokens, spaced=spaced)) and (
                not after or _consume_prefix_tokens(after, prefix_tokens, spaced=spaced)
            ):
                return True
    return False


def _rhetorical_exclusivity_negation(text: str, match: re.Match[str]) -> bool:
    clause_prefix = _RELATIONSHIP_CLAUSE_BREAK.split(text[: match.start()])[-1]
    if any(marker in clause_prefix for marker in ("难道", "难不成", "岂不是")):
        return True
    if re.search(r"(?:我|你)?不是说(?:你|乐枝)?\s*$", clause_prefix) and re.match(
        r"(?:别|不要|不可以|不该|不应该|不应|不必|不用|不需要|无需|"
        r"没必要|没有必要)",
        match.group(0),
    ):
        return False
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
