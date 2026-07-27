from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_CHAT_ID_RE = re.compile(r"^-?[0-9]+$")
_TELEGRAM_TOKEN_RE = re.compile(r"^[0-9]+:[A-Za-z0-9_-]+$")
_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


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
    telegram_bot_token: str
    telegram_chat_id: str
    database_path: Path
    telegram_polling_timeout_seconds: int
    telegram_retry_delay_seconds: int
    log_level: str

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
        )
