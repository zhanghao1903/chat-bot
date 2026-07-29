from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from helpers import temporary_database

from group_llm_agent.context import ContextAssembler
from group_llm_agent.events import MemoryCategory, TelegramTextMessage, TriggerPath
from group_llm_agent.memory import MemoryRepository
from group_llm_agent.messages import MessageRepository
from group_llm_agent.persona import load_character_bundle


class ContextAssemblerTests(unittest.TestCase):
    def test_context_is_bounded_scoped_and_uses_one_persona_snapshot(self) -> None:
        fixture = Path(__file__).parent / "fixtures/personas/test-original/v1"
        bundle = load_character_bundle(fixture)
        with temporary_database() as database:
            messages = MessageRepository(database)
            messages.policies.set_memory_status(
                chat_id="group-a",
                status="enabled",
                persona=bundle.snapshot,
                notice_message_id="notice-1",
                enabled_by_user_id="admin",
            )
            source_ids: dict[str, int] = {}
            for index in range(1, 23):
                sender_id = "sender" if index == 22 else f"member-{index}"
                message = TelegramTextMessage(
                    event_id=f"event-{index}",
                    group_id="group-a",
                    message_id=str(index),
                    sender_id=sender_id,
                    sender_display_name=sender_id,
                    text=f"scene message {index}",
                    timestamp=datetime(2026, 7, 29, tzinfo=UTC) + timedelta(seconds=index),
                )
                result = messages.ingest_inbound(
                    message,
                    persona=bundle.snapshot,
                    recognition_policy_version="policy-v1",
                )
                assert result.message_id is not None
                source_ids[sender_id] = result.message_id

            memory = MemoryRepository(database)
            for memory_id, member_id in (
                ("sender-memory", "sender"),
                ("reply-memory", "member-21"),
                ("unrelated-memory", "member-20"),
            ):
                memory.add(
                    memory_id=memory_id,
                    chat_id="group-a",
                    member_user_id=member_id,
                    category=MemoryCategory.FACT,
                    statement=f"Public fact for {member_id}.",
                    confidence=0.9,
                    source_message_ids=(source_ids[member_id],),
                    recognition_policy_version="policy-v1",
                    persona=None,
                )
            current = TelegramTextMessage(
                event_id="event-22",
                group_id="group-a",
                message_id="22",
                sender_id="sender",
                sender_display_name="Sender",
                text="scene message 22",
                timestamp=datetime(2026, 7, 29, tzinfo=UTC),
                replied_to_user_id="member-21",
                mentioned_user_ids=("member-20",),
            )
            assembler = ContextAssembler(
                messages=messages,
                memory=memory,
                recognition_policy_version="policy-v1",
            )

            trigger = assembler.trigger_context(
                bundle=bundle,
                message=current,
                hard_gate_reason="cadence_ready",
            )
            effect = assembler.effect_context(
                bundle=bundle,
                message=current,
                trigger_path=TriggerPath.CONTEXTUAL,
                model_calls_remaining=3,
                tool_calls_remaining=2,
                deadline_at=datetime.now(UTC) + timedelta(seconds=20),
            )

            self.assertEqual(20, len(effect.recent_scene))
            self.assertEqual("3", effect.recent_scene[0].telegram_message_id)
            self.assertEqual("22", effect.recent_scene[-1].telegram_message_id)
            self.assertEqual(bundle.snapshot, trigger.persona)
            self.assertEqual(bundle.snapshot, effect.persona)
            self.assertEqual(bundle.snapshot, trigger.character.snapshot)
            self.assertEqual(bundle.snapshot, effect.character.snapshot)
            self.assertEqual((), trigger.character.examples_jsonl)
            self.assertEqual(2, len(effect.character.examples_jsonl))
            self.assertEqual(
                {"sender", "member-21", "member-20"},
                {item.member_user_id for item in effect.member_memory},
            )
            self.assertEqual(
                {"sender-memory", "reply-memory", "unrelated-memory"},
                {
                    memory_item.memory_id
                    for member in effect.member_memory
                    for memory_item in member.items
                },
            )

    def test_unknown_member_has_empty_memory_without_invented_relationship(self) -> None:
        fixture = Path(__file__).parent / "fixtures/personas/test-original/v1"
        bundle = load_character_bundle(fixture)
        with temporary_database() as database:
            messages = MessageRepository(database)
            memory = MemoryRepository(database)
            assembler = ContextAssembler(
                messages=messages,
                memory=memory,
                recognition_policy_version="policy-v1",
            )
            current = TelegramTextMessage(
                event_id="unknown-event",
                group_id="group-a",
                message_id="1",
                sender_id="unknown-member",
                sender_display_name="Unknown",
                text="hello",
                timestamp=datetime(2026, 7, 29, tzinfo=UTC),
            )
            messages.ingest_inbound(
                current,
                persona=bundle.snapshot,
                recognition_policy_version="policy-v1",
            )

            context = assembler.effect_context(
                bundle=bundle,
                message=current,
                trigger_path=TriggerPath.DIRECT,
                model_calls_remaining=3,
                tool_calls_remaining=2,
                deadline_at=datetime.now(UTC) + timedelta(seconds=20),
            )

            self.assertEqual(1, len(context.member_memory))
            self.assertEqual("unknown-member", context.member_memory[0].member_user_id)
            self.assertEqual((), context.member_memory[0].items)


if __name__ == "__main__":
    unittest.main()
