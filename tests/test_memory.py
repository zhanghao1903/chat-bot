from __future__ import annotations

import sqlite3
import unittest
from datetime import UTC, datetime, timedelta

from helpers import temporary_database

from group_llm_agent.events import MemoryCategory, PersonaSnapshot, TelegramTextMessage
from group_llm_agent.memory import MemoryRepository
from group_llm_agent.messages import MessageRepository

_PERSONA_V1 = PersonaSnapshot("test-persona", "v1", "digest-v1")
_PERSONA_V2 = PersonaSnapshot("test-persona", "v2", "digest-v2")


def _message(chat_id: str, message_id: str, sender_id: str = "member-1") -> TelegramTextMessage:
    return TelegramTextMessage(
        event_id=f"event-{chat_id}-{message_id}",
        group_id=chat_id,
        message_id=message_id,
        sender_id=sender_id,
        sender_display_name=sender_id,
        text=f"source {message_id}",
        timestamp=datetime(2026, 7, 29, tzinfo=UTC),
    )


def _enable_and_ingest(
    messages: MessageRepository,
    *,
    chat_id: str,
    message_id: str,
    sender_id: str = "member-1",
) -> int:
    messages.policies.set_memory_status(
        chat_id=chat_id,
        status="enabled",
        persona=_PERSONA_V1,
        notice_message_id=f"notice-{chat_id}",
        enabled_by_user_id="admin",
    )
    result = messages.ingest_inbound(
        _message(chat_id, message_id, sender_id),
        persona=_PERSONA_V1,
        recognition_policy_version="policy-v1",
    )
    assert result.message_id is not None
    return result.message_id


class MemoryRepositoryTests(unittest.TestCase):
    def test_confidence_decay_persona_compatibility_and_group_scope(self) -> None:
        with temporary_database() as database:
            messages = MessageRepository(database)
            source_a = _enable_and_ingest(
                messages,
                chat_id="group-a",
                message_id="1",
            )
            source_b = _enable_and_ingest(
                messages,
                chat_id="group-b",
                message_id="1",
            )
            memory = MemoryRepository(database)
            now = datetime(2026, 7, 29, tzinfo=UTC)
            old = now - timedelta(days=60)
            memory.add(
                memory_id="fact-a",
                chat_id="group-a",
                member_user_id="member-1",
                category=MemoryCategory.FACT,
                statement="The member publicly prefers concise examples.",
                confidence=0.8,
                source_message_ids=(source_a,),
                recognition_policy_version="policy-v1",
                persona=None,
                observed_at=old,
            )
            memory.add(
                memory_id="impression-v1",
                chat_id="group-a",
                member_user_id="member-1",
                category=MemoryCategory.IMPRESSION,
                statement="The member currently enjoys careful disagreement.",
                confidence=0.8,
                source_message_ids=(source_a,),
                recognition_policy_version="policy-v1",
                persona=_PERSONA_V1,
                observed_at=now,
            )
            memory.add(
                memory_id="preference-v2",
                chat_id="group-a",
                member_user_id="member-1",
                category=MemoryCategory.PREFERENCE,
                statement="The v2 persona prefers a more formal stance.",
                confidence=0.9,
                source_message_ids=(source_a,),
                recognition_policy_version="policy-v1",
                persona=_PERSONA_V2,
                observed_at=now,
            )
            memory.add(
                memory_id="other-group",
                chat_id="group-b",
                member_user_id="member-1",
                category=MemoryCategory.FACT,
                statement="This is isolated to group B.",
                confidence=1,
                source_message_ids=(source_b,),
                recognition_policy_version="policy-v1",
                persona=None,
                observed_at=now,
            )

            active = memory.list_active(
                chat_id="group-a",
                member_user_id="member-1",
                persona=_PERSONA_V1,
                recognition_policy_version="policy-v1",
                at=now,
            )
            self.assertEqual(
                {"fact-a", "impression-v1"},
                {item.memory_id for item in active},
            )
            fact = next(item for item in active if item.memory_id == "fact-a")
            self.assertGreater(fact.effective_confidence, 0.35)
            self.assertNotIn("other-group", {item.memory_id for item in active})

            with self.assertRaises(sqlite3.IntegrityError):
                memory.add(
                    memory_id="cross-group-source",
                    chat_id="group-a",
                    member_user_id="member-1",
                    category=MemoryCategory.FACT,
                    statement="Invalid cross-group source.",
                    confidence=0.8,
                    source_message_ids=(source_b,),
                    recognition_policy_version="policy-v1",
                    persona=None,
                    observed_at=now,
                )

    def test_old_impression_falls_below_threshold(self) -> None:
        with temporary_database() as database:
            messages = MessageRepository(database)
            source = _enable_and_ingest(
                messages,
                chat_id="group-a",
                message_id="1",
            )
            memory = MemoryRepository(database)
            now = datetime(2026, 7, 29, tzinfo=UTC)
            memory.add(
                memory_id="old-impression",
                chat_id="group-a",
                member_user_id="member-1",
                category=MemoryCategory.IMPRESSION,
                statement="A stale subjective impression.",
                confidence=0.8,
                source_message_ids=(source,),
                recognition_policy_version="policy-v1",
                persona=_PERSONA_V1,
                observed_at=now - timedelta(days=60),
            )
            self.assertEqual(
                (),
                memory.list_active(
                    chat_id="group-a",
                    member_user_id="member-1",
                    persona=_PERSONA_V1,
                    recognition_policy_version="policy-v1",
                    at=now,
                ),
            )

    def test_later_evidence_can_revise_and_revoke_memory(self) -> None:
        with temporary_database() as database:
            messages = MessageRepository(database)
            source_1 = _enable_and_ingest(
                messages,
                chat_id="group-a",
                message_id="1",
            )
            source_2 = _enable_and_ingest(
                messages,
                chat_id="group-a",
                message_id="2",
            )
            memory = MemoryRepository(database)
            memory.add(
                memory_id="old",
                chat_id="group-a",
                member_user_id="member-1",
                category=MemoryCategory.OBSERVATION,
                statement="The member always avoids follow-up.",
                confidence=0.7,
                source_message_ids=(source_1,),
                recognition_policy_version="policy-v1",
                persona=None,
            )
            revision = memory.revise(
                old_memory_id="old",
                new_memory_id="revised",
                chat_id="group-a",
                member_user_id="member-1",
                expected_revision=1,
                statement="The member sometimes follows up after a reminder.",
                confidence=0.85,
                source_message_ids=(source_2,),
                recognition_policy_version="policy-v1",
                persona=None,
            )
            self.assertEqual(2, revision)
            active = memory.list_active(
                chat_id="group-a",
                member_user_id="member-1",
                persona=_PERSONA_V1,
                recognition_policy_version="policy-v1",
            )
            self.assertEqual(["revised"], [item.memory_id for item in active])

            memory.revoke(
                memory_id="revised",
                chat_id="group-a",
                member_user_id="member-1",
                expected_revision=2,
            )
            self.assertEqual(
                (),
                memory.list_active(
                    chat_id="group-a",
                    member_user_id="member-1",
                    persona=_PERSONA_V1,
                    recognition_policy_version="policy-v1",
                ),
            )

    def test_reset_purges_only_target_member_in_current_group(self) -> None:
        with temporary_database() as database:
            messages = MessageRepository(database)
            source_target = _enable_and_ingest(
                messages,
                chat_id="group-a",
                message_id="1",
                sender_id="member-1",
            )
            _enable_and_ingest(
                messages,
                chat_id="group-a",
                message_id="2",
                sender_id="member-2",
            )
            source_other_group = _enable_and_ingest(
                messages,
                chat_id="group-b",
                message_id="1",
                sender_id="member-1",
            )
            memory = MemoryRepository(database)
            for memory_id, chat_id, source in (
                ("target", "group-a", source_target),
                ("other-group", "group-b", source_other_group),
            ):
                memory.add(
                    memory_id=memory_id,
                    chat_id=chat_id,
                    member_user_id="member-1",
                    category=MemoryCategory.FACT,
                    statement=f"Fact for {chat_id}.",
                    confidence=0.9,
                    source_message_ids=(source,),
                    recognition_policy_version="policy-v1",
                    persona=None,
                )

            generation = memory.reset_member(
                chat_id="group-a",
                member_user_id="member-1",
                reset_by_user_id="member-1",
            )

            self.assertEqual(1, generation)
            self.assertEqual(
                (),
                memory.list_active(
                    chat_id="group-a",
                    member_user_id="member-1",
                    persona=_PERSONA_V1,
                    recognition_policy_version="policy-v1",
                ),
            )
            self.assertEqual(
                ["other-group"],
                [
                    item.memory_id
                    for item in memory.list_active(
                        chat_id="group-b",
                        member_user_id="member-1",
                        persona=_PERSONA_V1,
                        recognition_policy_version="policy-v1",
                    )
                ],
            )
            group_a_text = messages.search(chat_id="group-a", query="source")
            self.assertEqual(["member-2"], [item.sender_user_id for item in group_a_text])


if __name__ == "__main__":
    unittest.main()
