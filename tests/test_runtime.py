from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from group_llm_agent.delivery import SQLiteDeliveryLedger
from group_llm_agent.events import TelegramTextMessage
from group_llm_agent.platforms.telegram import (
    TelegramAdapter,
    TelegramApiError,
)
from group_llm_agent.runtime import (
    FIXED_REPLY_ACTION,
    FixedReplyProcessor,
    TelegramPollingService,
)


class FakeTelegramClient:
    def __init__(self, updates: list[dict] | None = None) -> None:
        self.updates = updates or []
        self.sent: list[tuple[str, str, str | None]] = []
        self.fail_message_ids: set[str] = set()
        self.get_updates_calls = 0

    def get_updates(self, *, offset: int | None, timeout_seconds: int) -> list[dict]:
        self.get_updates_calls += 1
        return list(self.updates)

    def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        reply_to_message_id: str | None = None,
    ) -> None:
        if reply_to_message_id in self.fail_message_ids:
            raise TelegramApiError("sendMessage", "transport_error")
        self.sent.append((chat_id, text, reply_to_message_id))


class FixedReplyProcessorTests(unittest.TestCase):
    def test_exact_one_replies_once_and_replay_is_silent(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ledger.sqlite3"
            client = FakeTelegramClient()
            store = _store(path)
            processor = _processor(client, store)
            event = _message("1", message_id="10")

            first = processor.handle_message(event)
            duplicate = processor.handle_message(event)

            self.assertEqual(first.status, "sent")
            self.assertEqual(duplicate.status, "duplicate")
            self.assertEqual(client.sent, [("-1001", "1", "10")])
            record = store.get(
                chat_id="-1001",
                message_id="10",
                action_kind=FIXED_REPLY_ACTION,
            )
            self.assertIsNotNone(record)
            self.assertEqual(record.status, "sent")
            store.close()

            reopened = _store(path)
            replay_after_restart = _processor(client, reopened).handle_message(event)
            self.assertEqual(replay_after_restart.status, "duplicate")
            self.assertEqual(len(client.sent), 1)
            reopened.close()

    def test_unmatched_whitespace_and_other_group_are_silent(self) -> None:
        with TemporaryDirectory() as tmpdir:
            client = FakeTelegramClient()
            store = _store(Path(tmpdir) / "ledger.sqlite3")
            processor = _processor(client, store)

            unmatched = processor.handle_message(_message(" 1", message_id="11"))
            other_group = processor.handle_message(_message("1", group_id="-2002", message_id="12"))

            self.assertEqual(unmatched.status, "unmatched")
            self.assertEqual(other_group.status, "ignored_group")
            self.assertEqual(client.sent, [])
            store.close()

    def test_self_message_is_silent(self) -> None:
        with TemporaryDirectory() as tmpdir:
            client = FakeTelegramClient()
            store = _store(Path(tmpdir) / "ledger.sqlite3")
            processor = _processor(client, store)
            event = _message("1", message_id="13")
            self_event = event.__class__(**{**event.__dict__, "sender_id": "bot-7"})

            outcome = processor.handle_message(self_event)

            self.assertEqual(outcome.status, "ignored_self")
            self.assertEqual(client.sent, [])
            store.close()

    def test_send_failure_is_recorded_and_later_message_continues(self) -> None:
        with TemporaryDirectory() as tmpdir:
            client = FakeTelegramClient()
            client.fail_message_ids.add("14")
            store = _store(Path(tmpdir) / "ledger.sqlite3")
            processor = _processor(client, store)

            failed = processor.handle_message(_message("1", message_id="14"))
            sent = processor.handle_message(_message("1", message_id="15"))

            self.assertEqual(failed.status, "send_failed")
            self.assertEqual(sent.status, "sent")
            failed_record = store.get(
                chat_id="-1001",
                message_id="14",
                action_kind=FIXED_REPLY_ACTION,
            )
            self.assertIsNotNone(failed_record)
            self.assertEqual(failed_record.status, "failed")
            self.assertEqual(failed_record.error_code, "transport_error")
            self.assertEqual(client.sent, [("-1001", "1", "15")])
            store.close()


class TelegramPollingServiceTests(unittest.TestCase):
    def test_malformed_update_does_not_stop_following_message(self) -> None:
        malformed = {
            "update_id": 20,
            "message": {
                "message_id": 20,
                "date": "not-a-timestamp",
                "chat": {"id": -1001, "type": "supergroup"},
                "from": {"id": 42, "first_name": "Alice"},
                "text": "1",
            },
        }
        valid = {
            "update_id": 21,
            "message": {
                "message_id": 21,
                "date": 1781769600,
                "chat": {"id": -1001, "type": "supergroup"},
                "from": {"id": 42, "first_name": "Alice"},
                "text": "1",
            },
        }
        with TemporaryDirectory() as tmpdir:
            client = FakeTelegramClient([malformed, valid])
            store = _store(Path(tmpdir) / "ledger.sqlite3")
            service = TelegramPollingService(
                client=client,
                adapter=TelegramAdapter(),
                processor=_processor(client, store),
                polling_timeout_seconds=25,
                retry_delay_seconds=2,
                sleep=lambda _seconds: None,
            )

            count = service.run_once()

            self.assertEqual(count, 2)
            self.assertEqual(service.offset, 22)
            self.assertEqual(client.sent, [("-1001", "1", "21")])
            store.close()

    def test_poll_transport_failure_waits_and_retries(self) -> None:
        class RetryThenStopClient(FakeTelegramClient):
            def get_updates(self, *, offset: int | None, timeout_seconds: int) -> list[dict]:
                self.get_updates_calls += 1
                if self.get_updates_calls == 1:
                    raise TelegramApiError("getUpdates", "transport_error")
                raise KeyboardInterrupt

        with TemporaryDirectory() as tmpdir:
            client = RetryThenStopClient()
            store = _store(Path(tmpdir) / "ledger.sqlite3")
            sleeps: list[float] = []
            service = TelegramPollingService(
                client=client,
                adapter=TelegramAdapter(),
                processor=_processor(client, store),
                polling_timeout_seconds=25,
                retry_delay_seconds=2,
                sleep=sleeps.append,
            )

            with self.assertRaises(KeyboardInterrupt):
                service.run_forever()

            self.assertEqual(client.get_updates_calls, 2)
            self.assertEqual(sleeps, [2.0])
            store.close()


def _store(path: Path) -> SQLiteDeliveryLedger:
    store = SQLiteDeliveryLedger(path)
    store.initialize()
    return store


def _processor(
    client: FakeTelegramClient,
    store: SQLiteDeliveryLedger,
) -> FixedReplyProcessor:
    return FixedReplyProcessor(
        allowed_chat_id="-1001",
        bot_user_id="bot-7",
        client=client,
        store=store,
    )


def _message(
    text: str,
    *,
    group_id: str = "-1001",
    message_id: str = "10",
) -> TelegramTextMessage:
    return TelegramTextMessage(
        event_id=f"event:{message_id}",
        group_id=group_id,
        message_id=message_id,
        sender_id="user-1",
        sender_display_name="Alice",
        text=text,
        timestamp=datetime(2026, 7, 27, 0, 0, tzinfo=UTC),
    )


if __name__ == "__main__":
    unittest.main()
