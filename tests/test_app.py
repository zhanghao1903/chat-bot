from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory

from group_llm_agent.app import run
from group_llm_agent.platforms.telegram import TelegramApiError


class _StopAfterIdentityClient:
    def __init__(self, _token: str, *, timeout_seconds: int) -> None:
        self.timeout_seconds = timeout_seconds

    def get_me(self) -> dict:
        return {"id": 7, "is_bot": True, "username": "agent"}

    def get_updates(self, *, offset: int | None, timeout_seconds: int) -> list[dict]:
        raise KeyboardInterrupt

    def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        reply_to_message_id: str | None = None,
    ) -> None:
        raise AssertionError("No message should be sent in this startup test")


class _InvalidTokenClient(_StopAfterIdentityClient):
    def get_me(self) -> dict:
        raise TelegramApiError("getMe", "api_error", 401)


class AppTests(unittest.TestCase):
    def test_missing_configuration_returns_non_zero(self) -> None:
        self.assertEqual(run({}), 2)

    def test_unsafe_token_startup_output_never_exposes_token(self) -> None:
        token = "123456:bad token"
        environment = {
            "TELEGRAM_BOT_TOKEN": token,
            "TELEGRAM_CHAT_ID": "-1001",
        }
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            result = run(environment)

        self.assertEqual(result, 2)
        self.assertIn("TELEGRAM_BOT_TOKEN", stderr.getvalue())
        self.assertNotIn(token, stderr.getvalue())

    def test_verified_identity_can_start_and_shutdown_cleanly(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result = run(
                _environment(Path(tmpdir) / "ledger.sqlite3"),
                client_factory=_StopAfterIdentityClient,
            )

        self.assertEqual(result, 0)

    def test_invalid_identity_never_reports_started(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result = run(
                _environment(Path(tmpdir) / "ledger.sqlite3"),
                client_factory=_InvalidTokenClient,
            )

        self.assertEqual(result, 3)

    def test_non_bot_identity_never_reports_started(self) -> None:
        class NonBotClient(_StopAfterIdentityClient):
            def get_me(self) -> dict:
                return {"id": 7, "is_bot": False, "username": "agent"}

        with TemporaryDirectory() as tmpdir:
            result = run(
                _environment(Path(tmpdir) / "ledger.sqlite3"),
                client_factory=NonBotClient,
            )

        self.assertEqual(result, 3)


def _environment(database_path: Path) -> dict[str, str]:
    return {
        "TELEGRAM_BOT_TOKEN": "123456:test-token",
        "TELEGRAM_CHAT_ID": "-1001",
        "DATABASE_PATH": str(database_path),
    }


if __name__ == "__main__":
    unittest.main()
