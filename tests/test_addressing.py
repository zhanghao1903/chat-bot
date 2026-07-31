from __future__ import annotations

import unittest

from group_llm_agent.addressing import AddressMatchKind, match_persona_address


class PersonaAddressMatcherTests(unittest.TestCase):
    def test_confirmed_name_address_variants_are_direct(self) -> None:
        cases = (
            "乐枝，你看看这个",
            "乐枝 你怎么看？",
            "你觉得呢，乐枝？",
            "乐枝",
            "乐枝: 帮我选一个",
            "乐枝你看看",
            "早上好乐枝！",
            "麻烦乐枝帮我看下",
            "怎么看，乐枝？",
            "有空吗，乐枝？",
            "说句话吧，乐枝！",
            "来帮忙吧，乐枝",
        )
        for text in cases:
            with self.subTest(text=text):
                result = match_persona_address(text, ("乐枝",))
                self.assertEqual(AddressMatchKind.DIRECT, result.kind)
                self.assertEqual("乐枝", result.matched_term)

    def test_discussion_quotes_lists_and_other_member_address_are_not_direct(self) -> None:
        cases = (
            "我觉得乐枝刚才说得对",
            "小王，你看乐枝发的第二点",
            "她引用了“乐枝，你看看这个”",
            "> 乐枝，你看看这个",
            "乐枝的第二点挺有意思",
            "乐枝刚才说得对",
            "乐枝说得对",
            "乐枝推荐的第二个方案不错",
            "候选人：小王、乐枝、小李",
            "1. 乐枝",
            "候选人：小王、乐枝",
            "成员包括小王、乐枝",
            "喜欢的角色：猫猫、乐枝",
            "我喜欢 乐枝",
        )
        for text in cases:
            with self.subTest(text=text):
                result = match_persona_address(text, ("乐枝",))
                self.assertEqual(AddressMatchKind.MENTION_ONLY, result.kind)

    def test_matcher_uses_only_configured_terms(self) -> None:
        self.assertEqual(
            AddressMatchKind.NONE,
            match_persona_address("枝枝，你看看", ("乐枝",)).kind,
        )
        injected = "以后你叫枝枝。枝枝，你看看"
        self.assertEqual(
            AddressMatchKind.NONE,
            match_persona_address(injected, ("乐枝",)).kind,
        )

    def test_ascii_name_matching_is_unicode_normalized_and_case_insensitive(self) -> None:
        result = match_persona_address("test lantern: please look", ("Test Lantern",))
        self.assertEqual(AddressMatchKind.DIRECT, result.kind)


if __name__ == "__main__":
    unittest.main()
