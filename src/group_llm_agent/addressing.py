from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class AddressMatchKind(StrEnum):
    NONE = "none"
    DIRECT = "direct"
    MENTION_ONLY = "mention_only"


@dataclass(frozen=True)
class AddressMatch:
    kind: AddressMatchKind
    reason_code: str
    matched_term: str | None = None


_OPENING_SEPARATORS = frozenset(",，:：!！?？~～、")
_CLOSING_PUNCTUATION = frozenset(",，:：!！?？。.…~～")
_COMPACT_OPENING_CUES = (
    "你",
    "请",
    "帮我",
    "帮忙",
    "看看",
    "看下",
    "看一下",
    "来",
    "能不能",
    "可以",
    "告诉我",
    "给我",
    "回答",
    "解释一下",
    "分析一下",
    "查一下",
    "搜一下",
    "选一个",
    "推荐一个",
    "在吗",
)
_COMPACT_ENDING_CUES = ("你好", "早上好", "晚上好", "晚安", "谢谢", "在吗", "拜托", "请问")
_TERMINAL_VOCATIVE_CUES = ("怎么办", "怎么样", "可以吗", "好吗", "行吗", "拜托", "谢谢", "请问")
_REQUEST_PREFIXES = ("请", "麻烦", "想请", "问问", "让")
_REQUEST_SUFFIXES = ("帮", "看", "说", "来", "给", "回答", "分析", "解释", "查", "搜", "选", "推荐")
_QUOTE_PAIRS = {'"': '"', "'": "'", "“": "”", "‘": "’", "「": "」", "『": "』", "《": "》"}
_LIST_CONTEXT_PATTERN = re.compile(
    r"(?:候选|成员|包括|包含|名单|角色|选项|人物|参与者|嘉宾|例如|比如).*[、,，]"
)


def match_persona_address(text: str, terms: tuple[str, ...]) -> AddressMatch:
    """Classify configured persona-name use without learning from group text."""

    normalized = unicodedata.normalize("NFKC", text)
    if not normalized.strip() or not terms:
        return AddressMatch(AddressMatchKind.NONE, "no_configured_name")

    quote_ranges = _quote_ranges(normalized)
    saw_term = False
    saw_quoted_term = False
    for configured_term in terms:
        term = unicodedata.normalize("NFKC", configured_term).strip()
        if not term:
            continue
        folded_text = normalized.casefold()
        folded_term = term.casefold()
        start = 0
        while True:
            index = folded_text.find(folded_term, start)
            if index < 0:
                break
            end = index + len(folded_term)
            start = max(end, index + 1)
            saw_term = True
            if _is_quoted_or_block_quote(normalized, index, quote_ranges):
                saw_quoted_term = True
                continue
            reason = _direct_reason(normalized, index, end)
            if reason is not None:
                return AddressMatch(AddressMatchKind.DIRECT, reason, configured_term)

    if saw_term:
        return AddressMatch(
            AddressMatchKind.MENTION_ONLY,
            "quoted_persona_name" if saw_quoted_term else "persona_name_not_addressed",
        )
    return AddressMatch(AddressMatchKind.NONE, "persona_name_absent")


def _direct_reason(text: str, start: int, end: int) -> str | None:
    before_raw = text[:start]
    after_raw = text[end:]
    before = before_raw.rstrip()
    after = after_raw.lstrip()
    at_start = not before
    after_without_closing = after.rstrip("".join(_CLOSING_PUNCTUATION)).strip()

    if at_start and not after_without_closing:
        return "persona_name_standalone"
    if at_start and after_raw:
        first = after_raw[0]
        if first.isspace() or first in _OPENING_SEPARATORS:
            return "persona_name_opening_vocative"
        if after.startswith(_COMPACT_OPENING_CUES):
            return "persona_name_opening_request"

    if not after_without_closing:
        if re.fullmatch(r"\s*(?:[-*+]|(?:\d+|[一二三四五六七八九十]+)[.)、])\s*", before_raw):
            return None
        if before.endswith(_COMPACT_ENDING_CUES):
            return "persona_name_ending_greeting"
        if _is_terminal_vocative(before_raw):
            return "persona_name_ending_vocative"

    if before.endswith(_REQUEST_PREFIXES) and after.startswith(_REQUEST_SUFFIXES):
        return "persona_name_explicit_request"
    return None


def _is_terminal_vocative(before_raw: str) -> bool:
    """Require positive address evidence before a terminal persona name."""

    if not before_raw:
        return False
    delimiter = before_raw[-1]
    if delimiter == "、" or not (delimiter.isspace() or delimiter in _OPENING_SEPARATORS):
        return False
    clause = before_raw.rstrip().rstrip("".join(_OPENING_SEPARATORS)).rstrip()
    if not clause or _LIST_CONTEXT_PATTERN.search(clause):
        return False
    return "你" in clause or "您" in clause or clause.endswith(_TERMINAL_VOCATIVE_CUES)


def _quote_ranges(text: str) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    for opener, closer in _QUOTE_PAIRS.items():
        cursor = 0
        while cursor < len(text):
            start = text.find(opener, cursor)
            if start < 0:
                break
            end = text.find(closer, start + 1)
            if end < 0:
                break
            ranges.append((start, end + 1))
            cursor = end + 1
    return tuple(sorted(ranges))


def _is_quoted_or_block_quote(
    text: str,
    index: int,
    ranges: tuple[tuple[int, int], ...],
) -> bool:
    if any(start <= index < end for start, end in ranges):
        return True
    line_start = text.rfind("\n", 0, index) + 1
    prefix = text[line_start:index]
    return re.fullmatch(r"\s*>.*", prefix) is not None
