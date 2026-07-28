from __future__ import annotations

import unittest
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from helpers import temporary_database

from group_llm_agent.control import MEMORY_DISCLOSURE, MemoryControlService
from group_llm_agent.events import MemoryCategory, TelegramTextMessage
from group_llm_agent.memory import MemoryRepository
from group_llm_agent.messages import MessageRepository
from group_llm_agent.persona import CharacterBundle, load_character_bundle
from group_llm_agent.platforms.telegram import (
    ChatMemberStatus,
    SentMessage,
    TelegramApiError,
    TelegramMemberStatus,
)
from group_llm_agent.runs import RunRepository

_NOW = datetime(2026, 7, 29, 4, tzinfo=UTC)


class FakeControlTelegram:
    def __init__(
        self,
        *,
        status: TelegramMemberStatus = TelegramMemberStatus.ADMINISTRATOR,
        authorization_error: TelegramApiError | None = None,
        send_results: tuple[SentMessage | TelegramApiError, ...] = (),
    ) -> None:
        self.status = status
        self.authorization_error = authorization_error
        self.send_results = deque(send_results)
        self.sent: list[tuple[str, str, str | None]] = []
        self.authorization_calls: list[tuple[str, str]] = []

    def get_chat_member(self, *, chat_id: str, user_id: str) -> ChatMemberStatus:
        self.authorization_calls.append((chat_id, user_id))
        if self.authorization_error is not None:
            raise self.authorization_error
        return ChatMemberStatus(user_id=user_id, status=self.status)

    def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        reply_to_message_id: str | None = None,
    ) -> SentMessage:
        self.sent.append((chat_id, text, reply_to_message_id))
        result = self.send_results.popleft() if self.send_results else SentMessage("sent-1")
        if isinstance(result, TelegramApiError):
            raise result
        return result


class MemoryControlServiceTests(unittest.TestCase):
    def test_enable_requires_confirmed_public_notice(self) -> None:
        bundle = _bundle()
        cases = (
            (
                FakeControlTelegram(
                    send_results=(TelegramApiError("sendMessage", "transport_error"),)
                ),
                "notice_failed",
                "disabled",
                "uncertain",
            ),
            (
                FakeControlTelegram(send_results=(SentMessage("notice-77"),)),
                "enabled",
                "enabled",
                "sent",
            ),
        )
        for index, (telegram, expected, memory_status, effect_status) in enumerate(cases):
            with self.subTest(expected=expected), temporary_database() as database:
                service, messages, _ = _service(database, telegram)
                event = _command(index + 1, "/memory_enable")

                outcome = service.handle(event, persona=bundle.snapshot, now=_NOW)

                policy = messages.policies.get(chat_id="group-a")
                assert policy is not None
                connection = database.connect()
                try:
                    effect = connection.execute(
                        """
                        SELECT status, platform_message_id
                        FROM external_effects
                        """
                    ).fetchone()
                    notice_message_id = connection.execute(
                        """
                        SELECT notice_message_id FROM group_policies
                        WHERE chat_id = 'group-a'
                        """
                    ).fetchone()["notice_message_id"]
                finally:
                    connection.close()
                self.assertEqual(expected, outcome.status)
                self.assertEqual(memory_status, policy.memory_status)
                self.assertEqual(effect_status, effect["status"])
                if expected == "enabled":
                    self.assertEqual("notice-77", notice_message_id)
                    self.assertEqual("notice-77", outcome.platform_message_id)
                    self.assertEqual(MEMORY_DISCLOSURE, telegram.sent[0][1])
                else:
                    self.assertIsNone(notice_message_id)

    def test_permission_timeout_or_non_admin_changes_nothing(self) -> None:
        bundle = _bundle()
        clients = (
            FakeControlTelegram(authorization_error=TelegramApiError("getChatMember", "timeout")),
            FakeControlTelegram(status=TelegramMemberStatus.MEMBER),
        )
        for client in clients:
            with self.subTest(client=client), temporary_database() as database:
                service, messages, _ = _service(database, client)

                outcome = service.handle(
                    _command(1, "/memory_enable"),
                    persona=bundle.snapshot,
                    now=_NOW,
                )

                policy = messages.policies.get(chat_id="group-a")
                connection = database.connect()
                try:
                    effects = connection.execute(
                        "SELECT count(*) FROM external_effects"
                    ).fetchone()[0]
                    audit = connection.execute(
                        """
                        SELECT authorization_status
                        FROM control_action_audit
                        """
                    ).fetchone()["authorization_status"]
                finally:
                    connection.close()
                self.assertEqual("not_authorized", outcome.status)
                self.assertTrue(policy is None or policy.memory_status == "disabled")
                self.assertEqual(0, effects)
                self.assertIn(audit, {"unavailable", "denied"})
                self.assertEqual([], client.sent)

    def test_self_reset_scope_persists_even_if_acknowledgement_fails(self) -> None:
        bundle = _bundle()
        telegram = FakeControlTelegram(send_results=(TelegramApiError("sendMessage", "timeout"),))
        with temporary_database() as database:
            service, messages, memory = _service(database, telegram)
            _seed_member(messages, memory, bundle, "group-a", "member-a", "1")
            _seed_member(messages, memory, bundle, "group-a", "member-b", "2")
            _seed_member(messages, memory, bundle, "group-b", "member-a", "3")

            outcome = service.handle(
                _command(
                    10,
                    "/memory_forget_me",
                    sender_id="member-a",
                ),
                persona=bundle.snapshot,
                now=_NOW,
            )

            connection = database.connect()
            try:
                rows = connection.execute(
                    """
                    SELECT chat_id, member_user_id, status
                    FROM member_memory_items ORDER BY chat_id, member_user_id
                    """
                ).fetchall()
                texts = connection.execute(
                    """
                    SELECT chat_id, sender_user_id, text
                    FROM group_messages ORDER BY chat_id, sender_user_id
                    """
                ).fetchall()
                effect = connection.execute("SELECT status FROM external_effects").fetchone()[
                    "status"
                ]
            finally:
                connection.close()
            statuses = {
                (str(row["chat_id"]), str(row["member_user_id"])): str(row["status"])
                for row in rows
            }
            retained = {
                (str(row["chat_id"]), str(row["sender_user_id"])): row["text"] for row in texts
            }
            self.assertEqual("member_forgotten_ack_failed", outcome.status)
            self.assertIsNotNone(outcome.reset_generation)
            self.assertEqual("revoked", statuses[("group-a", "member-a")])
            self.assertEqual("active", statuses[("group-a", "member-b")])
            self.assertEqual("active", statuses[("group-b", "member-a")])
            self.assertIsNone(retained[("group-a", "member-a")])
            self.assertIsNotNone(retained[("group-a", "member-b")])
            self.assertIsNotNone(retained[("group-b", "member-a")])
            self.assertEqual("uncertain", effect)

    def test_admin_member_and_confirmed_group_reset_stay_group_scoped(self) -> None:
        bundle = _bundle()
        telegram = FakeControlTelegram(send_results=(SentMessage("ack-1"), SentMessage("ack-2")))
        with temporary_database() as database:
            service, messages, memory = _service(database, telegram)
            _seed_member(messages, memory, bundle, "group-a", "member-a", "1")
            _seed_member(messages, memory, bundle, "group-a", "member-b", "2")
            _seed_member(messages, memory, bundle, "group-b", "member-a", "3")

            member_outcome = service.handle(
                _command(
                    20,
                    "/memory_forget_member",
                    replied_to_user_id="member-a",
                ),
                persona=bundle.snapshot,
                now=_NOW,
            )
            group_outcome = service.handle(
                _command(21, "/memory_forget_group CONFIRM"),
                persona=bundle.snapshot,
                now=_NOW,
            )

            connection = database.connect()
            try:
                statuses = {
                    (str(row["chat_id"]), str(row["member_user_id"])): str(row["status"])
                    for row in connection.execute(
                        """
                        SELECT chat_id, member_user_id, status
                        FROM member_memory_items
                        """
                    ).fetchall()
                }
            finally:
                connection.close()
            self.assertEqual("member_forgotten", member_outcome.status)
            self.assertEqual("group_forgotten", group_outcome.status)
            self.assertEqual("revoked", statuses[("group-a", "member-a")])
            self.assertEqual("revoked", statuses[("group-a", "member-b")])
            self.assertEqual("active", statuses[("group-b", "member-a")])
            self.assertEqual(2, len(telegram.authorization_calls))

    def test_disable_stops_memory_reads_before_acknowledgement(self) -> None:
        bundle = _bundle()
        telegram = FakeControlTelegram(send_results=(SentMessage("ack-disable"),))
        with temporary_database() as database:
            service, messages, memory = _service(database, telegram)
            _seed_member(messages, memory, bundle, "group-a", "member-a", "1")

            outcome = service.handle(
                _command(30, "/memory_disable"),
                persona=bundle.snapshot,
                now=_NOW,
            )
            active = memory.list_active(
                chat_id="group-a",
                member_user_id="member-a",
                persona=bundle.snapshot,
                recognition_policy_version="policy-v1",
            )

            self.assertEqual("disabled", outcome.status)
            self.assertEqual((), active)


def _bundle() -> CharacterBundle:
    return load_character_bundle(Path(__file__).parent / "fixtures/personas/test-original/v1")


def _service(
    database,
    telegram: FakeControlTelegram,
) -> tuple[MemoryControlService, MessageRepository, MemoryRepository]:
    messages = MessageRepository(database)
    memory = MemoryRepository(database)
    service = MemoryControlService(
        allowed_chat_id="group-a",
        bot_user_id="bot-1",
        telegram=telegram,
        messages=messages,
        memory=memory,
        runs=RunRepository(database),
    )
    return service, messages, memory


def _seed_member(
    messages: MessageRepository,
    memory: MemoryRepository,
    bundle: CharacterBundle,
    chat_id: str,
    member_user_id: str,
    message_id: str,
) -> None:
    messages.policies.set_memory_status(
        chat_id=chat_id,
        status="enabled",
        persona=bundle.snapshot,
        notice_message_id=f"notice-{chat_id}",
        enabled_by_user_id="admin",
    )
    result = messages.ingest_inbound(
        TelegramTextMessage(
            event_id=f"seed-{chat_id}-{message_id}",
            group_id=chat_id,
            message_id=message_id,
            sender_id=member_user_id,
            sender_display_name=member_user_id,
            text=f"public seed {message_id}",
            timestamp=_NOW,
        ),
        persona=bundle.snapshot,
        recognition_policy_version="policy-v1",
    )
    assert result.message_id is not None
    memory.add(
        memory_id=f"memory-{chat_id}-{member_user_id}",
        chat_id=chat_id,
        member_user_id=member_user_id,
        category=MemoryCategory.OBSERVATION,
        statement=f"{member_user_id} made a public contribution.",
        confidence=0.7,
        source_message_ids=(result.message_id,),
        recognition_policy_version="policy-v1",
        persona=None,
        observed_at=_NOW,
    )


def _command(
    index: int,
    text: str,
    *,
    sender_id: str = "admin",
    replied_to_user_id: str | None = None,
) -> TelegramTextMessage:
    return TelegramTextMessage(
        event_id=f"control-event-{index}",
        group_id="group-a",
        message_id=str(100 + index),
        sender_id=sender_id,
        sender_display_name=sender_id,
        text=text,
        timestamp=_NOW,
        replied_to_user_id=replied_to_user_id,
        is_bot_command=True,
    )


if __name__ == "__main__":
    unittest.main()
