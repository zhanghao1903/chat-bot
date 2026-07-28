from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from helpers import temporary_database

from group_llm_agent.events import (
    MemoryCategory,
    PersonaSnapshot,
    TelegramTextMessage,
)
from group_llm_agent.memory import MemoryRepository
from group_llm_agent.messages import MessageRepository
from group_llm_agent.model import WriterDecision, WriterDecisionKind
from group_llm_agent.persona import load_character_bundle
from group_llm_agent.runs import RunRepository
from group_llm_agent.tools import (
    LOOKUP_MEMBER_MEMORY,
    SEARCH_RECENT_GROUP_MESSAGES,
    ReadOnlyToolRegistry,
    ToolExecutionScope,
)


class ReadOnlyToolRegistryTests(unittest.TestCase):
    def test_member_lookup_injects_group_and_allowed_member_scope(self) -> None:
        bundle = load_character_bundle(Path(__file__).parent / "fixtures/personas/test-original/v1")
        with temporary_database() as database:
            messages = MessageRepository(database)
            messages.policies.set_memory_status(
                chat_id="group-a",
                status="enabled",
                persona=bundle.snapshot,
                notice_message_id="notice",
                enabled_by_user_id="admin",
            )
            source = messages.ingest_inbound(
                _message("group-a", "1", "member-a", "public preference"),
                persona=bundle.snapshot,
                recognition_policy_version="policy-v1",
            ).message_id
            assert source is not None
            memory = MemoryRepository(database)
            memory.add(
                memory_id="memory-a",
                chat_id="group-a",
                member_user_id="member-a",
                category=MemoryCategory.FACT,
                statement="Member A publicly prefers short examples.",
                confidence=0.9,
                source_message_ids=(source,),
                recognition_policy_version="policy-v1",
                persona=None,
            )
            runs = RunRepository(database)
            registry = ReadOnlyToolRegistry(messages=messages, memory=memory, runs=runs)
            scope = _scope(bundle.snapshot)

            success = registry.execute(
                _tool_call(
                    LOOKUP_MEMBER_MEMORY,
                    {"member_user_id": "member-a"},
                ),
                scope=scope,
            )
            rejected = registry.execute(
                _tool_call(
                    LOOKUP_MEMBER_MEMORY,
                    {"member_user_id": "member-b", "chat_id": "group-b"},
                ),
                scope=scope,
            )

            self.assertEqual(
                frozenset({LOOKUP_MEMBER_MEMORY, SEARCH_RECENT_GROUP_MESSAGES}),
                registry.allowed_tools,
            )
            self.assertEqual("success", success.status)
            self.assertIn("short examples", success.content_json)
            self.assertEqual("invalid_arguments", rejected.status)
            self.assertNotIn("group-b", success.content_json)

            connection = database.connect()
            try:
                audits = connection.execute(
                    """
                    SELECT chat_id, capability, source_scope, status
                    FROM tool_call_audit ORDER BY id
                    """
                ).fetchall()
            finally:
                connection.close()
            self.assertEqual("group-a", audits[0]["chat_id"])
            self.assertEqual("member:member-a", audits[0]["source_scope"])
            self.assertEqual("invalid_arguments", audits[1]["status"])

    def test_group_search_is_bounded_and_never_crosses_group(self) -> None:
        bundle = load_character_bundle(Path(__file__).parent / "fixtures/personas/test-original/v1")
        with temporary_database() as database:
            messages = MessageRepository(database)
            for chat_id in ("group-a", "group-b"):
                messages.policies.set_memory_status(
                    chat_id=chat_id,
                    status="enabled",
                    persona=bundle.snapshot,
                    notice_message_id=f"notice-{chat_id}",
                    enabled_by_user_id="admin",
                )
            for index in range(1, 13):
                messages.ingest_inbound(
                    _message(
                        "group-a",
                        str(index),
                        f"member-{index}",
                        "needle " + "x" * 250,
                    ),
                    persona=bundle.snapshot,
                    recognition_policy_version="policy-v1",
                )
            messages.ingest_inbound(
                _message("group-b", "1", "other", "needle secret-other-group"),
                persona=bundle.snapshot,
                recognition_policy_version="policy-v1",
            )
            registry = ReadOnlyToolRegistry(
                messages=messages,
                memory=MemoryRepository(database),
                runs=RunRepository(database),
            )

            result = registry.execute(
                _tool_call(SEARCH_RECENT_GROUP_MESSAGES, {"query": "needle"}),
                scope=_scope(bundle.snapshot),
            )
            payload = json.loads(result.content_json)

            self.assertLessEqual(result.result_count, 10)
            self.assertLessEqual(result.result_char_count, 4_000)
            self.assertNotIn("secret-other-group", result.content_json)
            self.assertTrue(all(item["text"].startswith("needle") for item in payload["items"]))

    def test_expired_deadline_returns_audited_timeout_without_query(self) -> None:
        bundle = load_character_bundle(Path(__file__).parent / "fixtures/personas/test-original/v1")
        with temporary_database() as database:
            registry = ReadOnlyToolRegistry(
                messages=MessageRepository(database),
                memory=MemoryRepository(database),
                runs=RunRepository(database),
            )
            scope = ToolExecutionScope(
                effect_run_id=1,
                chat_id="group-a",
                allowed_member_ids=frozenset({"member-a"}),
                persona=bundle.snapshot,
                recognition_policy_version="policy-v1",
                deadline_at=datetime.now(UTC) - timedelta(seconds=1),
            )

            result = registry.execute(
                _tool_call(SEARCH_RECENT_GROUP_MESSAGES, {"query": "anything"}),
                scope=scope,
            )

            self.assertEqual("timeout", result.status)
            self.assertEqual(0, result.result_count)


def _message(
    chat_id: str,
    message_id: str,
    sender_id: str,
    text: str,
) -> TelegramTextMessage:
    return TelegramTextMessage(
        event_id=f"event-{chat_id}-{message_id}",
        group_id=chat_id,
        message_id=message_id,
        sender_id=sender_id,
        sender_display_name=sender_id,
        text=text,
        timestamp=datetime.now(UTC),
    )


def _tool_call(name: str, arguments: dict[str, object]) -> WriterDecision:
    return WriterDecision(
        kind=WriterDecisionKind.CALL_TOOL,
        reason_code="need_context",
        tool_name=name,
        tool_arguments=arguments,
        tool_purpose_code="continue_scene",
    )


def _scope(persona: PersonaSnapshot) -> ToolExecutionScope:
    return ToolExecutionScope(
        effect_run_id=1,
        chat_id="group-a",
        allowed_member_ids=frozenset({"member-a"}),
        persona=persona,
        recognition_policy_version="policy-v1",
        deadline_at=datetime.now(UTC) + timedelta(seconds=10),
    )


if __name__ == "__main__":
    unittest.main()
