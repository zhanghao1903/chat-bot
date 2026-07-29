from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from group_llm_agent.events import MemoryCategory


class MemorySemanticKey(StrEnum):
    """Application-owned meanings that are safe to persist as member memory."""

    STATED_INTEREST_GAMES = "stated_interest_games"
    STATED_INTEREST_READING = "stated_interest_reading"
    STATED_INTEREST_MUSIC = "stated_interest_music"
    STATED_INTEREST_FILM = "stated_interest_film"
    STATED_INTEREST_FOOD = "stated_interest_food"
    STATED_INTEREST_TECHNOLOGY = "stated_interest_technology"
    STATED_INTEREST_ART = "stated_interest_art"
    STATED_INTEREST_WRITING = "stated_interest_writing"
    STATED_INTEREST_PHOTOGRAPHY = "stated_interest_photography"
    STATED_INTEREST_PETS = "stated_interest_pets"
    STATED_INTEREST_NATURE = "stated_interest_nature"
    STATED_INTEREST_LEARNING = "stated_interest_learning"
    STATED_INTEREST_TRAVEL = "stated_interest_travel"
    STATED_INTEREST_SPORTS = "stated_interest_sports"
    STATED_INTEREST_RECREATION = "stated_interest_recreation"
    MADE_PUBLIC_GROUP_COMMITMENT = "made_public_group_commitment"
    ASKED_QUESTION = "asked_question"
    ASKED_FOLLOW_UP = "asked_follow_up"
    ANSWERED_QUESTION = "answered_question"
    SUPPORTED_MEMBER = "supported_member"
    SUPPORTED_GROUP_PLAN = "supported_group_plan"
    SHARED_RESOURCE = "shared_resource"
    CORRECTED_INFORMATION = "corrected_information"
    MADE_JOKE = "made_joke"
    JOINED_GROUP_ACTIVITY = "joined_group_activity"
    FOLLOWED_UP = "followed_up"
    WELCOMES_PLAYFUL_FOLLOW_UP = "welcomes_playful_follow_up"
    WELCOMES_DIRECT_FOLLOW_UP = "welcomes_direct_follow_up"
    PREFERS_CONCISE_REPLIES = "prefers_concise_replies"
    ENJOYS_PLAYFUL_EXCHANGE = "enjoys_playful_exchange"
    PARTICIPATED_TOGETHER = "participated_together"
    RESOLVED_QUESTION_TOGETHER = "resolved_question_together"


@dataclass(frozen=True)
class SafeMemorySemantic:
    category: MemoryCategory
    statement: str


_SAFE_MEMORY_SEMANTICS: Final = MappingProxyType(
    {
        MemorySemanticKey.STATED_INTEREST_GAMES: SafeMemorySemantic(
            MemoryCategory.FACT,
            "The member publicly expressed interest in games.",
        ),
        MemorySemanticKey.STATED_INTEREST_READING: SafeMemorySemantic(
            MemoryCategory.FACT,
            "The member publicly expressed interest in reading.",
        ),
        MemorySemanticKey.STATED_INTEREST_MUSIC: SafeMemorySemantic(
            MemoryCategory.FACT,
            "The member publicly expressed interest in music.",
        ),
        MemorySemanticKey.STATED_INTEREST_FILM: SafeMemorySemantic(
            MemoryCategory.FACT,
            "The member publicly expressed interest in film.",
        ),
        MemorySemanticKey.STATED_INTEREST_FOOD: SafeMemorySemantic(
            MemoryCategory.FACT,
            "The member publicly expressed interest in food.",
        ),
        MemorySemanticKey.STATED_INTEREST_TECHNOLOGY: SafeMemorySemantic(
            MemoryCategory.FACT,
            "The member publicly expressed interest in technology.",
        ),
        MemorySemanticKey.STATED_INTEREST_ART: SafeMemorySemantic(
            MemoryCategory.FACT,
            "The member publicly expressed interest in art.",
        ),
        MemorySemanticKey.STATED_INTEREST_WRITING: SafeMemorySemantic(
            MemoryCategory.FACT,
            "The member publicly expressed interest in writing.",
        ),
        MemorySemanticKey.STATED_INTEREST_PHOTOGRAPHY: SafeMemorySemantic(
            MemoryCategory.FACT,
            "The member publicly expressed interest in photography.",
        ),
        MemorySemanticKey.STATED_INTEREST_PETS: SafeMemorySemantic(
            MemoryCategory.FACT,
            "The member publicly expressed interest in pets.",
        ),
        MemorySemanticKey.STATED_INTEREST_NATURE: SafeMemorySemantic(
            MemoryCategory.FACT,
            "The member publicly expressed interest in nature.",
        ),
        MemorySemanticKey.STATED_INTEREST_LEARNING: SafeMemorySemantic(
            MemoryCategory.FACT,
            "The member publicly expressed interest in learning.",
        ),
        MemorySemanticKey.STATED_INTEREST_TRAVEL: SafeMemorySemantic(
            MemoryCategory.FACT,
            "The member publicly expressed interest in travel.",
        ),
        MemorySemanticKey.STATED_INTEREST_SPORTS: SafeMemorySemantic(
            MemoryCategory.FACT,
            "The member publicly expressed interest in sports.",
        ),
        MemorySemanticKey.STATED_INTEREST_RECREATION: SafeMemorySemantic(
            MemoryCategory.FACT,
            "The member publicly expressed interest in a recreational activity.",
        ),
        MemorySemanticKey.MADE_PUBLIC_GROUP_COMMITMENT: SafeMemorySemantic(
            MemoryCategory.FACT,
            "The member made a public commitment to the group.",
        ),
        MemorySemanticKey.ASKED_QUESTION: SafeMemorySemantic(
            MemoryCategory.OBSERVATION,
            "The member asked a public group question.",
        ),
        MemorySemanticKey.ASKED_FOLLOW_UP: SafeMemorySemantic(
            MemoryCategory.OBSERVATION,
            "The member asked a public follow-up question.",
        ),
        MemorySemanticKey.ANSWERED_QUESTION: SafeMemorySemantic(
            MemoryCategory.OBSERVATION,
            "The member answered a public group question.",
        ),
        MemorySemanticKey.SUPPORTED_MEMBER: SafeMemorySemantic(
            MemoryCategory.OBSERVATION,
            "The member supported another group member.",
        ),
        MemorySemanticKey.SUPPORTED_GROUP_PLAN: SafeMemorySemantic(
            MemoryCategory.OBSERVATION,
            "The member supported a public group plan.",
        ),
        MemorySemanticKey.SHARED_RESOURCE: SafeMemorySemantic(
            MemoryCategory.OBSERVATION,
            "The member shared a resource with the group.",
        ),
        MemorySemanticKey.CORRECTED_INFORMATION: SafeMemorySemantic(
            MemoryCategory.OBSERVATION,
            "The member corrected information in the group.",
        ),
        MemorySemanticKey.MADE_JOKE: SafeMemorySemantic(
            MemoryCategory.OBSERVATION,
            "The member made a joke in the group.",
        ),
        MemorySemanticKey.JOINED_GROUP_ACTIVITY: SafeMemorySemantic(
            MemoryCategory.OBSERVATION,
            "The member joined a public group activity.",
        ),
        MemorySemanticKey.FOLLOWED_UP: SafeMemorySemantic(
            MemoryCategory.OBSERVATION,
            "The member followed up on an earlier group discussion.",
        ),
        MemorySemanticKey.WELCOMES_PLAYFUL_FOLLOW_UP: SafeMemorySemantic(
            MemoryCategory.IMPRESSION,
            "The member currently welcomes playful follow-up questions.",
        ),
        MemorySemanticKey.WELCOMES_DIRECT_FOLLOW_UP: SafeMemorySemantic(
            MemoryCategory.IMPRESSION,
            "The member currently welcomes direct follow-up questions.",
        ),
        MemorySemanticKey.PREFERS_CONCISE_REPLIES: SafeMemorySemantic(
            MemoryCategory.PREFERENCE,
            "The member currently prefers concise replies.",
        ),
        MemorySemanticKey.ENJOYS_PLAYFUL_EXCHANGE: SafeMemorySemantic(
            MemoryCategory.PREFERENCE,
            "The member currently enjoys playful group exchanges.",
        ),
        MemorySemanticKey.PARTICIPATED_TOGETHER: SafeMemorySemantic(
            MemoryCategory.SHARED_EXPERIENCE,
            "The member and character participated in a public group activity together.",
        ),
        MemorySemanticKey.RESOLVED_QUESTION_TOGETHER: SafeMemorySemantic(
            MemoryCategory.SHARED_EXPERIENCE,
            "The member and character resolved a public group question together.",
        ),
    }
)


def resolve_memory_semantic(
    semantic_key: str,
    category: MemoryCategory,
) -> SafeMemorySemantic | None:
    """Resolve only explicitly safe meanings; every unknown or mismatched key is rejected."""

    try:
        key = MemorySemanticKey(semantic_key)
    except ValueError:
        return None
    semantic = _SAFE_MEMORY_SEMANTICS[key]
    return semantic if semantic.category is category else None


def memory_semantic_catalog() -> tuple[dict[str, str], ...]:
    """Return the exact model-facing contract without exposing mutable policy state."""

    return tuple(
        {
            "semantic_key": key.value,
            "category": semantic.category.value,
            "persisted_statement": semantic.statement,
        }
        for key, semantic in _SAFE_MEMORY_SEMANTICS.items()
    )
