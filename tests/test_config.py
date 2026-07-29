from __future__ import annotations

import unittest
from pathlib import Path

from group_llm_agent.config import ConfigError, Settings


class SettingsTests(unittest.TestCase):
    def test_parses_required_and_default_settings(self) -> None:
        settings = Settings.from_env(
            {
                "TELEGRAM_BOT_TOKEN": "123456:test-token",
                "TELEGRAM_CHAT_ID": "-100123",
            }
        )

        self.assertEqual(settings.telegram_bot_token, "123456:test-token")
        self.assertEqual(settings.telegram_chat_id, "-100123")
        self.assertEqual(settings.database_path, Path("data/telegram_bot.sqlite3"))
        self.assertEqual(settings.telegram_polling_timeout_seconds, 25)
        self.assertEqual(settings.telegram_retry_delay_seconds, 2)
        self.assertEqual(settings.log_level, "INFO")
        self.assertEqual(settings.bot_mode, "fixed")
        self.assertIsNone(settings.model_api_key)
        self.assertEqual(settings.member_memory_capability, "disabled")
        self.assertNotIn("123456:test-token", repr(settings))

    def test_missing_token_is_safe_and_actionable(self) -> None:
        with self.assertRaises(ConfigError) as caught:
            Settings.from_env({"TELEGRAM_CHAT_ID": "-100123"})

        self.assertEqual(caught.exception.setting, "TELEGRAM_BOT_TOKEN")
        self.assertNotIn("-100123", str(caught.exception))

    def test_token_with_unsafe_characters_is_rejected_without_echoing_value(self) -> None:
        for token in ("123456:bad token", " 123456:test-token", "123456:test-token\n"):
            with self.subTest(token=repr(token)), self.assertRaises(ConfigError) as caught:
                Settings.from_env(
                    {
                        "TELEGRAM_BOT_TOKEN": token,
                        "TELEGRAM_CHAT_ID": "-100123",
                    }
                )

            self.assertEqual(caught.exception.setting, "TELEGRAM_BOT_TOKEN")
            self.assertNotIn(token, str(caught.exception))

    def test_chat_id_must_be_non_zero_signed_integer(self) -> None:
        for value in ("group", "42", "0", ""):
            with self.subTest(value=value), self.assertRaises(ConfigError) as caught:
                Settings.from_env(
                    {
                        "TELEGRAM_BOT_TOKEN": "123456:test-token",
                        "TELEGRAM_CHAT_ID": value,
                    }
                )
            self.assertEqual(caught.exception.setting, "TELEGRAM_CHAT_ID")

    def test_polling_and_retry_ranges_are_enforced(self) -> None:
        with self.assertRaises(ConfigError) as caught:
            Settings.from_env(
                {
                    "TELEGRAM_BOT_TOKEN": "123456:test-token",
                    "TELEGRAM_CHAT_ID": "-100123",
                    "TELEGRAM_POLLING_TIMEOUT_SECONDS": "51",
                }
            )

        self.assertEqual(caught.exception.setting, "TELEGRAM_POLLING_TIMEOUT_SECONDS")

    def test_persona_mode_parses_models_bundle_and_bounded_budgets(self) -> None:
        env = _persona_env()
        env.update(
            {
                "TRIGGER_MODEL": "trigger-model",
                "RECOGNITION_MODEL": "recognition-model",
                "MEMBER_MEMORY_CAPABILITY": "available",
                "RAW_MESSAGE_RETENTION_DAYS": "5",
                "EFFECT_MAX_MODEL_CALLS": "2",
                "EFFECT_MAX_TOOL_CALLS": "1",
                "EFFECT_DEADLINE_SECONDS": "18",
                "TRIGGER_DECISION_TIMEOUT_SECONDS": "4",
                "RECOGNITION_TIMEOUT_SECONDS": "20",
                "RECOGNITION_MAX_ATTEMPTS": "2",
            }
        )

        settings = Settings.from_env(env)

        self.assertEqual(settings.bot_mode, "persona_full")
        self.assertEqual(settings.persona_bundle_path, Path("/safe/persona"))
        self.assertEqual(settings.model_provider, "openai_compatible")
        self.assertEqual(settings.writer_model, "writer-model")
        self.assertEqual(settings.trigger_model, "trigger-model")
        self.assertEqual(settings.recognition_model, "recognition-model")
        self.assertEqual(settings.member_memory_capability, "available")
        self.assertEqual(
            (settings.effect_max_model_calls, settings.effect_max_tool_calls),
            (2, 1),
        )
        self.assertNotIn("model-secret", repr(settings))

    def test_persona_mode_rejects_missing_or_unsafe_secret_without_echo(self) -> None:
        for secret in ("", " model-secret", "model secret", "model-secret\n"):
            env = _persona_env()
            env["MODEL_API_KEY"] = secret
            with self.subTest(secret=repr(secret)), self.assertRaises(ConfigError) as caught:
                Settings.from_env(env)

            rendered = str(caught.exception)
            self.assertEqual(caught.exception.setting, "MODEL_API_KEY")
            if secret:
                self.assertNotIn(secret, rendered)

    def test_effect_tool_budget_must_leave_a_final_model_call(self) -> None:
        env = _persona_env()
        env["EFFECT_MAX_MODEL_CALLS"] = "2"
        env["EFFECT_MAX_TOOL_CALLS"] = "2"

        with self.assertRaises(ConfigError) as caught:
            Settings.from_env(env)

        self.assertEqual(caught.exception.setting, "EFFECT_MAX_TOOL_CALLS")


def _persona_env() -> dict[str, str]:
    return {
        "TELEGRAM_BOT_TOKEN": "123456:test-token",
        "TELEGRAM_CHAT_ID": "-1001",
        "BOT_MODE": "persona_full",
        "PERSONA_BUNDLE_PATH": "/safe/persona",
        "PERSONA_EXPECTED_SHA256": "1" * 64,
        "MODEL_PROVIDER": "openai_compatible",
        "MODEL_BASE_URL": "https://api.example.test/v1",
        "MODEL_API_KEY": "model-secret",
        "WRITER_MODEL": "writer-model",
    }


if __name__ == "__main__":
    unittest.main()
