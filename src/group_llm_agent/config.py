from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

_CHAT_ID_RE = re.compile(r"^-?[0-9]+$")
_TELEGRAM_TOKEN_RE = re.compile(r"^[0-9]+:[A-Za-z0-9_-]+$")
_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_BOT_MODES = {"fixed", "persona_direct", "persona_full"}
_MEMORY_CAPABILITIES = {"disabled", "available"}
_MODEL_PROVIDERS = {"openai_compatible"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ConfigError(ValueError):
    """A safe configuration error that never contains a secret value."""

    def __init__(self, setting: str, message: str) -> None:
        self.setting = setting
        super().__init__(f"{setting}: {message}")


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(name, "is required")
    return value


def _telegram_token(env: Mapping[str, str]) -> str:
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ConfigError("TELEGRAM_BOT_TOKEN", "is required")
    if not _TELEGRAM_TOKEN_RE.fullmatch(token):
        raise ConfigError("TELEGRAM_BOT_TOKEN", "has an invalid format")
    return token


def _secret(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "")
    if (
        not value
        or value != value.strip()
        or any(ord(character) < 33 or ord(character) == 127 for character in value)
    ):
        raise ConfigError(name, "has an invalid format")
    return value


def _choice(
    env: Mapping[str, str],
    name: str,
    *,
    default: str,
    choices: set[str],
) -> str:
    value = env.get(name, default).strip().lower()
    if value not in choices:
        raise ConfigError(name, f"must be one of {', '.join(sorted(choices))}")
    return value


def _integer(
    env: Mapping[str, str],
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(name, "must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigError(name, f"must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = field(repr=False)
    telegram_chat_id: str
    database_path: Path
    telegram_polling_timeout_seconds: int
    telegram_retry_delay_seconds: int
    log_level: str
    bot_mode: str
    persona_bundle_path: Path | None
    persona_expected_sha256: str | None
    model_provider: str | None
    model_base_url: str | None
    model_api_key: str | None = field(repr=False)
    writer_model: str | None
    trigger_model: str | None
    recognition_model: str | None
    member_memory_capability: str
    raw_message_retention_days: int
    effect_max_model_calls: int
    effect_max_tool_calls: int
    effect_deadline_seconds: int
    trigger_decision_timeout_seconds: int
    recognition_timeout_seconds: int
    recognition_max_attempts: int

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        token = _telegram_token(env)
        chat_id = _required(env, "TELEGRAM_CHAT_ID")
        if not _CHAT_ID_RE.fullmatch(chat_id) or int(chat_id) >= 0:
            raise ConfigError("TELEGRAM_CHAT_ID", "must be a negative group chat integer")

        database_path_value = env.get("DATABASE_PATH", "data/telegram_bot.sqlite3").strip()
        if not database_path_value:
            raise ConfigError("DATABASE_PATH", "must not be empty")

        log_level = env.get("LOG_LEVEL", "INFO").strip().upper()
        if log_level not in _LOG_LEVELS:
            raise ConfigError(
                "LOG_LEVEL",
                "must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL",
            )

        bot_mode = _choice(
            env,
            "BOT_MODE",
            default="fixed",
            choices=_BOT_MODES,
        )
        memory_capability = _choice(
            env,
            "MEMBER_MEMORY_CAPABILITY",
            default="disabled",
            choices=_MEMORY_CAPABILITIES,
        )
        persona_bundle_path: Path | None = None
        persona_expected_sha256: str | None = None
        model_provider: str | None = None
        model_base_url: str | None = None
        model_api_key: str | None = None
        writer_model: str | None = None
        trigger_model: str | None = None
        recognition_model: str | None = None
        if bot_mode != "fixed":
            persona_bundle_path = Path(_required(env, "PERSONA_BUNDLE_PATH"))
            persona_expected_sha256 = _required(env, "PERSONA_EXPECTED_SHA256").lower()
            if _SHA256_RE.fullmatch(persona_expected_sha256) is None:
                raise ConfigError(
                    "PERSONA_EXPECTED_SHA256",
                    "must be a lowercase SHA-256 digest",
                )
            model_provider = _choice(
                env,
                "MODEL_PROVIDER",
                default="",
                choices=_MODEL_PROVIDERS,
            )
            model_base_url = _required(env, "MODEL_BASE_URL")
            model_api_key = _secret(env, "MODEL_API_KEY")
            writer_model = _required(env, "WRITER_MODEL")
            trigger_model = env.get("TRIGGER_MODEL", "").strip() or writer_model
            recognition_model = env.get("RECOGNITION_MODEL", "").strip() or writer_model

        effect_max_model_calls = _integer(
            env,
            "EFFECT_MAX_MODEL_CALLS",
            default=3,
            minimum=1,
            maximum=3,
        )
        effect_max_tool_calls = _integer(
            env,
            "EFFECT_MAX_TOOL_CALLS",
            default=2,
            minimum=0,
            maximum=2,
        )
        if effect_max_tool_calls >= effect_max_model_calls:
            raise ConfigError(
                "EFFECT_MAX_TOOL_CALLS",
                "must be less than EFFECT_MAX_MODEL_CALLS",
            )

        return cls(
            telegram_bot_token=token,
            telegram_chat_id=chat_id,
            database_path=Path(database_path_value),
            telegram_polling_timeout_seconds=_integer(
                env,
                "TELEGRAM_POLLING_TIMEOUT_SECONDS",
                default=25,
                minimum=1,
                maximum=50,
            ),
            telegram_retry_delay_seconds=_integer(
                env,
                "TELEGRAM_RETRY_DELAY_SECONDS",
                default=2,
                minimum=1,
                maximum=60,
            ),
            log_level=log_level,
            bot_mode=bot_mode,
            persona_bundle_path=persona_bundle_path,
            persona_expected_sha256=persona_expected_sha256,
            model_provider=model_provider,
            model_base_url=model_base_url,
            model_api_key=model_api_key,
            writer_model=writer_model,
            trigger_model=trigger_model,
            recognition_model=recognition_model,
            member_memory_capability=memory_capability,
            raw_message_retention_days=_integer(
                env,
                "RAW_MESSAGE_RETENTION_DAYS",
                default=7,
                minimum=1,
                maximum=7,
            ),
            effect_max_model_calls=effect_max_model_calls,
            effect_max_tool_calls=effect_max_tool_calls,
            effect_deadline_seconds=_integer(
                env,
                "EFFECT_DEADLINE_SECONDS",
                default=20,
                minimum=5,
                maximum=30,
            ),
            trigger_decision_timeout_seconds=_integer(
                env,
                "TRIGGER_DECISION_TIMEOUT_SECONDS",
                default=5,
                minimum=2,
                maximum=10,
            ),
            recognition_timeout_seconds=_integer(
                env,
                "RECOGNITION_TIMEOUT_SECONDS",
                default=15,
                minimum=5,
                maximum=30,
            ),
            recognition_max_attempts=_integer(
                env,
                "RECOGNITION_MAX_ATTEMPTS",
                default=3,
                minimum=1,
                maximum=3,
            ),
        )
