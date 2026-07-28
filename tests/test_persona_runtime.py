from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from helpers import ScriptedModelClient

from group_llm_agent.app import run
from group_llm_agent.model import ModelRole, StructuredModelResult
from group_llm_agent.persona import CharacterBundle, load_character_bundle
from group_llm_agent.platforms.telegram import (
    ChatMemberStatus,
    SentMessage,
    TelegramMemberStatus,
)
from group_llm_agent.runtime import RecognitionBackgroundWorker


class PersonaTelegramClient:
    def __init__(self, updates: list[dict[str, object]]) -> None:
        self.updates = updates
        self.get_me_calls = 0
        self.get_updates_calls = 0
        self.sent: list[tuple[str, str, str | None]] = []

    def get_me(self) -> dict[str, object]:
        self.get_me_calls += 1
        return {"id": 7, "is_bot": True, "username": "agent"}

    def get_updates(
        self,
        *,
        offset: int | None,
        timeout_seconds: int,
    ) -> list[dict[str, object]]:
        self.get_updates_calls += 1
        if self.get_updates_calls == 1:
            return list(self.updates)
        raise KeyboardInterrupt

    def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        reply_to_message_id: str | None = None,
    ) -> SentMessage:
        self.sent.append((chat_id, text, reply_to_message_id))
        return SentMessage(str(900 + len(self.sent)))

    def get_chat_member(self, *, chat_id: str, user_id: str) -> ChatMemberStatus:
        return ChatMemberStatus(user_id=user_id, status=TelegramMemberStatus.ADMINISTRATOR)


class PersonaRuntimeTests(unittest.TestCase):
    def test_direct_end_to_end_sends_once_and_records_confirmed_effect(self) -> None:
        bundle = _bundle()
        with TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "runtime.sqlite3"
            client = PersonaTelegramClient([_update(1, direct=True)])
            model = ScriptedModelClient(
                StructuredModelResult(
                    {
                        "kind": "reply",
                        "reason_code": "direct_answer",
                        "text": "我接到了，沿着这个点继续。",
                    }
                )
            )

            exit_code = run(
                _env(bundle, database_path, mode="persona_direct"),
                client_factory=lambda *_args, **_kwargs: client,
                model_factory=lambda _settings: model,
            )

            self.assertEqual(0, exit_code)
            self.assertEqual(
                [("-1001", "我接到了，沿着这个点继续。", "1")],
                client.sent,
            )
            self.assertEqual([ModelRole.WRITER], [call["model_role"] for call in model.calls])
            connection = sqlite3.connect(database_path)
            try:
                effect = connection.execute(
                    """
                    SELECT status, effect_kind, platform_message_id
                    FROM external_effects
                    """
                ).fetchone()
                run_counts = connection.execute(
                    """
                    SELECT status, model_call_count, tool_call_count
                    FROM effect_runs
                    """
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(("sent", "reply", "901"), effect)
            self.assertEqual(("reply", 1, 0), run_counts)

    def test_full_mode_contextual_fifth_message_calls_trigger_then_writer(self) -> None:
        bundle = _bundle()
        with TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "runtime.sqlite3"
            client = PersonaTelegramClient([_update(index) for index in range(1, 6)])
            model = ScriptedModelClient(
                StructuredModelResult({"kind": "engage", "reason_code": "unfinished_branch"}),
                StructuredModelResult(
                    {
                        "kind": "reply",
                        "reason_code": "continue_branch",
                        "text": "等等，这里还有一根线没接上。",
                    }
                ),
            )

            exit_code = run(
                _env(bundle, database_path, mode="persona_full"),
                client_factory=lambda *_args, **_kwargs: client,
                model_factory=lambda _settings: model,
            )

            self.assertEqual(0, exit_code)
            self.assertEqual(
                [ModelRole.TRIGGER, ModelRole.WRITER],
                [call["model_role"] for call in model.calls],
            )
            self.assertEqual(
                [("-1001", "等等，这里还有一根线没接上。", "5")],
                client.sent,
            )

    def test_direct_mode_never_calls_contextual_trigger(self) -> None:
        bundle = _bundle()
        with TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "runtime.sqlite3"
            client = PersonaTelegramClient([_update(index) for index in range(1, 6)])
            model = ScriptedModelClient()

            exit_code = run(
                _env(bundle, database_path, mode="persona_direct"),
                client_factory=lambda *_args, **_kwargs: client,
                model_factory=lambda _settings: model,
            )

            self.assertEqual(0, exit_code)
            self.assertEqual([], model.calls)
            self.assertEqual([], client.sent)

    def test_duplicate_event_across_restart_cannot_send_or_call_model_twice(self) -> None:
        bundle = _bundle()
        with TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "runtime.sqlite3"
            first_client = PersonaTelegramClient([_update(1, direct=True)])
            first_model = ScriptedModelClient(
                StructuredModelResult(
                    {"kind": "reply", "reason_code": "first", "text": "只发送一次。"}
                )
            )
            second_client = PersonaTelegramClient([_update(1, direct=True)])
            second_model = ScriptedModelClient()

            first_exit = run(
                _env(bundle, database_path, mode="persona_direct"),
                client_factory=lambda *_args, **_kwargs: first_client,
                model_factory=lambda _settings: first_model,
            )
            second_exit = run(
                _env(bundle, database_path, mode="persona_direct"),
                client_factory=lambda *_args, **_kwargs: second_client,
                model_factory=lambda _settings: second_model,
            )

            self.assertEqual((0, 0), (first_exit, second_exit))
            self.assertEqual(1, len(first_client.sent))
            self.assertEqual([], second_client.sent)
            self.assertEqual([], second_model.calls)

    def test_invalid_bundle_fails_before_telegram_identity_or_polling(self) -> None:
        bundle = _bundle()
        with TemporaryDirectory() as tmpdir:
            database_path = Path(tmpdir) / "runtime.sqlite3"
            client = PersonaTelegramClient([])
            env = _env(bundle, database_path, mode="persona_direct")
            env["PERSONA_EXPECTED_SHA256"] = "f" * 64

            exit_code = run(
                env,
                client_factory=lambda *_args, **_kwargs: client,
                model_factory=lambda _settings: ScriptedModelClient(),
            )

            self.assertEqual(2, exit_code)
            self.assertEqual(0, client.get_me_calls)
            self.assertEqual(0, client.get_updates_calls)

    def test_background_worker_starts_and_stops_cleanly(self) -> None:
        bundle = _bundle()
        fake = WaitingRecognitionWorker()
        background = RecognitionBackgroundWorker(
            worker=fake,
            bundle=bundle,
            idle_seconds=0.05,
        )

        background.start()
        self.assertTrue(fake.called.wait(timeout=1))
        self.assertTrue(background.is_alive)
        background.stop(timeout_seconds=1)

        self.assertFalse(background.is_alive)
        self.assertGreaterEqual(fake.call_count, 1)


class WaitingRecognitionWorker:
    def __init__(self) -> None:
        self.called = Event()
        self.call_count = 0

    def run_once(self, *, bundle: CharacterBundle) -> bool:
        self.call_count += 1
        self.called.set()
        return False


def _bundle() -> CharacterBundle:
    return load_character_bundle(Path(__file__).parent / "fixtures/personas/test-original/v1")


def _env(
    bundle: CharacterBundle,
    database_path: Path,
    *,
    mode: str,
) -> dict[str, str]:
    return {
        "TELEGRAM_BOT_TOKEN": "123456:test-token",
        "TELEGRAM_CHAT_ID": "-1001",
        "DATABASE_PATH": str(database_path),
        "BOT_MODE": mode,
        "PERSONA_BUNDLE_PATH": str(Path(__file__).parent / "fixtures/personas/test-original/v1"),
        "PERSONA_EXPECTED_SHA256": bundle.snapshot.persona_digest,
        "MODEL_PROVIDER": "openai_compatible",
        "MODEL_BASE_URL": "https://api.example.test/v1",
        "MODEL_API_KEY": "model-secret",
        "WRITER_MODEL": "writer-model",
        "MEMBER_MEMORY_CAPABILITY": "disabled",
    }


def _update(index: int, *, direct: bool = False) -> dict[str, object]:
    text = "/hello@agent" if direct else f"ordinary group message {index}"
    message: dict[str, object] = {
        "message_id": index,
        "date": 1785283200 + index,
        "chat": {"id": -1001, "type": "supergroup"},
        "from": {"id": 100 + index, "first_name": f"Member {index}"},
        "text": text,
    }
    if direct:
        message["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text)}]
    return {"update_id": index, "message": message}


if __name__ == "__main__":
    unittest.main()
