from __future__ import annotations

import unittest
from pathlib import Path

from group_llm_agent.config import ConfigError, Settings


class SettingsTests(unittest.TestCase):
    def test_parses_required_and_default_settings(self) -> None:
        settings = Settings.from_env(
            {
                "TELEGRAM_BOT_TOKEN": "secret-token",
                "TELEGRAM_CHAT_ID": "-100123",
            }
        )

        self.assertEqual(settings.telegram_bot_token, "secret-token")
        self.assertEqual(settings.telegram_chat_id, "-100123")
        self.assertEqual(settings.database_path, Path("data/telegram_bot.sqlite3"))
        self.assertEqual(settings.telegram_polling_timeout_seconds, 25)
        self.assertEqual(settings.telegram_retry_delay_seconds, 2)
        self.assertEqual(settings.log_level, "INFO")

    def test_missing_token_is_safe_and_actionable(self) -> None:
        with self.assertRaises(ConfigError) as caught:
            Settings.from_env({"TELEGRAM_CHAT_ID": "-100123"})

        self.assertEqual(caught.exception.setting, "TELEGRAM_BOT_TOKEN")
        self.assertNotIn("-100123", str(caught.exception))

    def test_chat_id_must_be_non_zero_signed_integer(self) -> None:
        for value in ("group", "42", "0", ""):
            with self.subTest(value=value), self.assertRaises(ConfigError) as caught:
                Settings.from_env(
                    {
                        "TELEGRAM_BOT_TOKEN": "secret-token",
                        "TELEGRAM_CHAT_ID": value,
                    }
                )
            self.assertEqual(caught.exception.setting, "TELEGRAM_CHAT_ID")

    def test_polling_and_retry_ranges_are_enforced(self) -> None:
        with self.assertRaises(ConfigError) as caught:
            Settings.from_env(
                {
                    "TELEGRAM_BOT_TOKEN": "secret-token",
                    "TELEGRAM_CHAT_ID": "-100123",
                    "TELEGRAM_POLLING_TIMEOUT_SECONDS": "51",
                }
            )

        self.assertEqual(caught.exception.setting, "TELEGRAM_POLLING_TIMEOUT_SECONDS")


if __name__ == "__main__":
    unittest.main()
