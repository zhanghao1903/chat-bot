from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from group_llm_agent.events import PersonaSnapshot
from group_llm_agent.memory import MemoryRepository
from group_llm_agent.messages import MessageRepository
from group_llm_agent.model import WriterDecision, WriterDecisionKind
from group_llm_agent.runs import RunRepository

LOOKUP_MEMBER_MEMORY = "lookup_member_memory"
SEARCH_RECENT_GROUP_MESSAGES = "search_recent_group_messages"


@dataclass(frozen=True)
class ToolExecutionScope:
    effect_run_id: int
    chat_id: str
    allowed_member_ids: frozenset[str]
    persona: PersonaSnapshot
    recognition_policy_version: str
    deadline_at: datetime


@dataclass(frozen=True)
class ToolExecutionResult:
    audit_id: int
    capability: str
    status: str
    content_json: str
    result_count: int
    result_char_count: int

    def as_untrusted_prompt_data(self) -> str:
        return f"BEGIN_UNTRUSTED_TOOL_RESULT\n{self.content_json}\nEND_UNTRUSTED_TOOL_RESULT"


class ReadOnlyToolRegistry:
    def __init__(
        self,
        *,
        messages: MessageRepository,
        memory: MemoryRepository,
        runs: RunRepository,
    ) -> None:
        self.messages = messages
        self.memory = memory
        self.runs = runs
        self.allowed_tools = frozenset({LOOKUP_MEMBER_MEMORY, SEARCH_RECENT_GROUP_MESSAGES})

    def execute(
        self,
        decision: WriterDecision,
        *,
        scope: ToolExecutionScope,
    ) -> ToolExecutionResult:
        if (
            decision.kind is not WriterDecisionKind.CALL_TOOL
            or decision.tool_name is None
            or decision.tool_arguments is None
            or decision.tool_purpose_code is None
        ):
            raise ValueError("Tool registry requires a complete call_tool decision")
        started = monotonic()
        capability = decision.tool_name
        if datetime.now(UTC) >= scope.deadline_at:
            return self._result(
                scope=scope,
                capability=capability,
                purpose_code=decision.tool_purpose_code,
                source_scope="deadline",
                status="timeout",
                payload={"error": "deadline_exhausted"},
                result_count=0,
                started=started,
            )
        if capability not in self.allowed_tools:
            return self._result(
                scope=scope,
                capability=capability,
                purpose_code=decision.tool_purpose_code,
                source_scope="rejected",
                status="invalid_tool",
                payload={"error": "invalid_tool"},
                result_count=0,
                started=started,
            )
        try:
            if capability == LOOKUP_MEMBER_MEMORY:
                return self._lookup_member_memory(decision, scope=scope, started=started)
            return self._search_recent_messages(decision, scope=scope, started=started)
        except (ValueError, TypeError):
            return self._result(
                scope=scope,
                capability=capability,
                purpose_code=decision.tool_purpose_code,
                source_scope="rejected",
                status="invalid_arguments",
                payload={"error": "invalid_arguments"},
                result_count=0,
                started=started,
            )
        except (OSError, sqlite3.Error):
            return self._result(
                scope=scope,
                capability=capability,
                purpose_code=decision.tool_purpose_code,
                source_scope="runtime",
                status="unavailable",
                payload={"error": "tool_unavailable"},
                result_count=0,
                started=started,
            )

    def record_rejected_attempt(
        self,
        *,
        scope: ToolExecutionScope,
        capability: str,
        purpose_code: str,
        status: str,
    ) -> ToolExecutionResult:
        return self._result(
            scope=scope,
            capability=capability[:128] or "invalid",
            purpose_code=purpose_code[:64] or "invalid",
            source_scope="rejected",
            status=status,
            payload={"error": status},
            result_count=0,
            started=monotonic(),
        )

    def _lookup_member_memory(
        self,
        decision: WriterDecision,
        *,
        scope: ToolExecutionScope,
        started: float,
    ) -> ToolExecutionResult:
        arguments = decision.tool_arguments
        assert arguments is not None
        if set(arguments) != {"member_user_id"}:
            raise ValueError("Unexpected member-memory arguments")
        member_user_id = arguments["member_user_id"]
        if not isinstance(member_user_id, str) or member_user_id not in scope.allowed_member_ids:
            raise ValueError("Member is outside the current scene")
        items = self.memory.list_active(
            chat_id=scope.chat_id,
            member_user_id=member_user_id,
            persona=scope.persona,
            recognition_policy_version=scope.recognition_policy_version,
            limit=8,
        )
        payload = {
            "capability": LOOKUP_MEMBER_MEMORY,
            "member_user_id": member_user_id,
            "items": [
                {
                    "memory_id": item.memory_id,
                    "category": item.category.value,
                    "statement": item.statement,
                    "effective_confidence": round(item.effective_confidence, 4),
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in items
            ],
        }
        return self._result(
            scope=scope,
            capability=LOOKUP_MEMBER_MEMORY,
            purpose_code=decision.tool_purpose_code or "unspecified",
            source_scope=f"member:{member_user_id}",
            status="success" if items else "empty",
            payload=payload,
            result_count=len(items),
            started=started,
        )

    def _search_recent_messages(
        self,
        decision: WriterDecision,
        *,
        scope: ToolExecutionScope,
        started: float,
    ) -> ToolExecutionResult:
        arguments = decision.tool_arguments
        assert arguments is not None
        if set(arguments) != {"query"}:
            raise ValueError("Unexpected group-message arguments")
        query = arguments["query"]
        if not isinstance(query, str):
            raise TypeError("Query must be text")
        items = self.messages.search(
            chat_id=scope.chat_id,
            query=query,
            limit=10,
            maximum_characters=4_000,
        )
        payload = {
            "capability": SEARCH_RECENT_GROUP_MESSAGES,
            "items": [
                {
                    "message_id": item.telegram_message_id,
                    "sender_user_id": item.sender_user_id,
                    "sent_at": item.sent_at.isoformat(),
                    "text": item.text,
                }
                for item in items
            ],
        }
        return self._result(
            scope=scope,
            capability=SEARCH_RECENT_GROUP_MESSAGES,
            purpose_code=decision.tool_purpose_code or "unspecified",
            source_scope="current_group_recent_text",
            status="success" if items else "empty",
            payload=payload,
            result_count=len(items),
            started=started,
        )

    def _result(
        self,
        *,
        scope: ToolExecutionScope,
        capability: str,
        purpose_code: str,
        source_scope: str,
        status: str,
        payload: dict[str, Any],
        result_count: int,
        started: float,
    ) -> ToolExecutionResult:
        content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(content) > 4_000:
            content = json.dumps(
                {"capability": capability, "error": "result_too_large"},
                separators=(",", ":"),
            )
            status = "result_too_large"
            result_count = 0
        latency_ms = max(0, int((monotonic() - started) * 1_000))
        audit_id = self.runs.record_tool_call(
            owner_kind="effect",
            owner_id=scope.effect_run_id,
            chat_id=scope.chat_id,
            capability=capability,
            purpose_code=purpose_code,
            source_scope=source_scope,
            status=status,
            latency_ms=latency_ms,
            result_count=result_count,
            result_char_count=len(content),
        )
        return ToolExecutionResult(
            audit_id=audit_id,
            capability=capability,
            status=status,
            content_json=content,
            result_count=result_count,
            result_char_count=len(content),
        )
