from __future__ import annotations

from group_llm_agent.context import EffectContext
from group_llm_agent.expression import ExpressionCatalog, ExpressionEntry

_RELATIONSHIP_RANK = {"public": 0, "familiar": 1, "close": 2}
_STICKER_MARKER_PREFIX = "[sticker:"


def sticker_selection_error(
    *,
    context: EffectContext,
    catalog: ExpressionCatalog,
    entry: ExpressionEntry,
) -> str | None:
    """Validate only application-owned, non-semantic sticker invariants.

    The Writer model owns the semantic choice between reply, composite reply,
    sticker, and silence. This boundary deliberately does not inspect message,
    memory, or vision language.
    """

    if catalog.status != "enabled":
        return "catalog_not_enabled"
    if entry.status != "enabled":
        return "sticker_not_enabled"
    if _RELATIONSHIP_RANK[entry.minimum_relationship] > _relationship_rank(context):
        return "relationship_insufficient"
    if entry.semantic_id == _last_outbound_sticker(context):
        return "consecutive_repeat"
    return None


def _relationship_rank(context: EffectContext) -> int:
    return 1 if any(member.items for member in context.member_memory) else 0


def _last_outbound_sticker(context: EffectContext) -> str | None:
    for item in reversed(context.recent_scene):
        if item.direction != "outbound":
            continue
        value = item.text
        if value.startswith(_STICKER_MARKER_PREFIX) and value.endswith("]"):
            semantic_id = value[len(_STICKER_MARKER_PREFIX) : -1]
            return semantic_id or None
    return None
