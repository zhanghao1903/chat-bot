from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from helpers import ScriptedModelClient, temporary_database

from group_llm_agent.context import ContextAssembler
from group_llm_agent.continuity import (
    CONTINUITY_DECISION_VALUES,
    CONTINUITY_RESPONSE_SCHEMA,
    ConversationContinuityDecider,
    ConversationContinuityGate,
)
from group_llm_agent.events import (
    ContinuityDecisionKind,
    ModelErrorCode,
    TelegramTextMessage,
    TriggerModelStatus,
)
from group_llm_agent.memory import MemoryRepository
from group_llm_agent.messages import MessageRepository
from group_llm_agent.model import ModelApiError, ModelRole, StructuredModelResult
from group_llm_agent.persona import CharacterBundle, load_character_bundle
from group_llm_agent.runs import RunRepository

_NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)


def _bundle() -> CharacterBundle:
    return load_character_bundle(Path(__file__).parent / "fixtures/personas/test-original/v1")


def _message(index: int, *, timestamp: datetime = _NOW) -> TelegramTextMessage:
    return TelegramTextMessage(
        event_id=f"event-{index}",
        group_id="group-a",
        message_id=str(index),
        sender_id=f"human-{index}",
        sender_display_name=f"Human {index}",
        text="current public response",
        timestamp=timestamp,
    )


def _record_anchor(
    messages: MessageRepository,
    *,
    sent_at: datetime,
    message_id: str = "bot-10",
) -> None:
    messages.record_outbound(
        chat_id="group-a",
        telegram_message_id=message_id,
        event_id=f"outbound:{message_id}",
        bot_user_id="bot-1",
        bot_display_name="Bot",
        text="你更喜欢哪个方案？",
        sent_at=sent_at,
        replied_to_message_id=None,
    )


def _ingest(
    messages: MessageRepository,
    message: TelegramTextMessage,
    *,
    bundle: CharacterBundle,
) -> None:
    messages.ingest_inbound(
        message,
        persona=bundle.snapshot,
        recognition_policy_version="policy-v1",
    )


class ConversationContinuityGateTests(unittest.TestCase):
    def test_exact_age_and_human_message_boundaries(self) -> None:
        bundle = _bundle()
        with temporary_database() as database:
            messages = MessageRepository(database)
            _record_anchor(messages, sent_at=_NOW - timedelta(minutes=10))
            for index in range(1, 6):
                _ingest(
                    messages,
                    _message(index, timestamp=_NOW - timedelta(seconds=5 - index)),
                    bundle=bundle,
                )
            gate = ConversationContinuityGate(bot_user_id="bot-1", messages=messages)

            accepted = gate.evaluate(_message(5), now=_NOW)

            self.assertTrue(accepted.eligible)
            assert accepted.anchor is not None
            self.assertEqual("bot-10", accepted.anchor.telegram_message_id)

        with temporary_database() as database:
            messages = MessageRepository(database)
            _record_anchor(
                messages,
                sent_at=_NOW - timedelta(minutes=10, microseconds=1),
            )
            current = _message(1)
            _ingest(messages, current, bundle=bundle)

            rejected = ConversationContinuityGate(bot_user_id="bot-1", messages=messages).evaluate(
                current, now=_NOW
            )

            self.assertFalse(rejected.eligible)
            self.assertEqual("anchor_expired", rejected.reason_code)

        with temporary_database() as database:
            messages = MessageRepository(database)
            _record_anchor(messages, sent_at=_NOW - timedelta(minutes=1))
            for index in range(1, 7):
                _ingest(messages, _message(index), bundle=bundle)

            rejected = ConversationContinuityGate(bot_user_id="bot-1", messages=messages).evaluate(
                _message(6), now=_NOW
            )

            self.assertFalse(rejected.eligible)
            self.assertEqual("too_many_human_messages", rejected.reason_code)

    def test_missing_current_future_and_wrong_bot_anchor_fail_closed(self) -> None:
        bundle = _bundle()
        with temporary_database() as database:
            messages = MessageRepository(database)
            gate = ConversationContinuityGate(bot_user_id="bot-1", messages=messages)
            self.assertEqual(
                "current_message_missing",
                gate.evaluate(_message(1), now=_NOW).reason_code,
            )

            _record_anchor(messages, sent_at=_NOW + timedelta(seconds=1))
            current = _message(1)
            _ingest(messages, current, bundle=bundle)
            self.assertEqual("future_anchor", gate.evaluate(current, now=_NOW).reason_code)

        with temporary_database() as database:
            messages = MessageRepository(database)
            messages.record_outbound(
                chat_id="group-a",
                telegram_message_id="other-bot",
                event_id="outbound:other",
                bot_user_id="bot-2",
                bot_display_name="Other Bot",
                text="other bot text",
                sent_at=_NOW - timedelta(seconds=1),
                replied_to_message_id=None,
            )
            current = _message(1)
            _ingest(messages, current, bundle=bundle)
            result = ConversationContinuityGate(bot_user_id="bot-1", messages=messages).evaluate(
                current, now=_NOW
            )
            self.assertEqual("no_recent_bot_message", result.reason_code)


class ConversationContinuityDeciderTests(unittest.TestCase):
    def test_prompt_schema_parser_and_all_four_decisions_agree(self) -> None:
        self.assertEqual(
            set(CONTINUITY_DECISION_VALUES),
            set(CONTINUITY_RESPONSE_SCHEMA["properties"]["kind"]["enum"]),  # type: ignore[index]
        )
        for index, kind in enumerate(ContinuityDecisionKind, start=1):
            with self.subTest(kind=kind.value), temporary_database() as database:
                bundle = _bundle()
                messages = MessageRepository(database)
                _record_anchor(messages, sent_at=_NOW - timedelta(minutes=1))
                current = _message(index)
                _ingest(messages, current, bundle=bundle)
                context = ContextAssembler(
                    messages=messages,
                    memory=MemoryRepository(database),
                    recognition_policy_version="policy-v1",
                ).trigger_context(
                    bundle=bundle,
                    message=current,
                    hard_gate_reason="eligible_recent_bot_anchor",
                    continuity_anchor_message_id="bot-10",
                    at=_NOW,
                )
                model = ScriptedModelClient(
                    StructuredModelResult({"kind": kind.value, "reason_code": "case_result"})
                )
                evaluation = ConversationContinuityDecider(
                    model=model,
                    runs=RunRepository(database),
                    clock=lambda: _NOW,
                ).decide(
                    request_id=f"continuity-{index}",
                    message=current,
                    bundle=bundle,
                    context=context,
                    now=_NOW,
                )

                self.assertEqual(kind, evaluation.decision.kind)
                self.assertEqual(TriggerModelStatus.COMPLETED, evaluation.model_status)
                self.assertEqual(ModelRole.TRIGGER, model.calls[0]["model_role"])
                self.assertEqual(CONTINUITY_RESPONSE_SCHEMA, model.calls[0]["response_schema"])
                system = model.calls[0]["messages"][0].content
                self.assertIn("Time adjacency is eligibility only", system)
                self.assertIn("not_addressed", system)

    def test_provider_failure_is_audited_ambiguous_fallback(self) -> None:
        bundle = _bundle()
        with temporary_database() as database:
            messages = MessageRepository(database)
            _record_anchor(messages, sent_at=_NOW - timedelta(minutes=1))
            current = _message(1)
            _ingest(messages, current, bundle=bundle)
            context = ContextAssembler(
                messages=messages,
                memory=MemoryRepository(database),
                recognition_policy_version="policy-v1",
            ).trigger_context(
                bundle=bundle,
                message=current,
                hard_gate_reason="eligible_recent_bot_anchor",
                continuity_anchor_message_id="bot-10",
                at=_NOW,
            )
            model = ScriptedModelClient(ModelApiError(ModelRole.TRIGGER, ModelErrorCode.TIMEOUT))
            evaluation = ConversationContinuityDecider(
                model=model,
                runs=RunRepository(database),
                clock=lambda: _NOW,
            ).decide(
                request_id="continuity-timeout",
                message=current,
                bundle=bundle,
                context=context,
                now=_NOW,
            )

            self.assertEqual(ContinuityDecisionKind.AMBIGUOUS, evaluation.decision.kind)
            self.assertEqual("model_timeout", evaluation.decision.reason_code)
            self.assertEqual(TriggerModelStatus.FAILED, evaluation.model_status)


if __name__ == "__main__":
    unittest.main()
