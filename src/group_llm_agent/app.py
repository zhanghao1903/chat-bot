from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable, Mapping
from time import sleep as default_sleep
from typing import Any

from group_llm_agent.config import ConfigError, Settings
from group_llm_agent.delivery import SQLiteDeliveryLedger
from group_llm_agent.platforms.telegram import (
    TelegramAdapter,
    TelegramApiError,
    TelegramBotApiClient,
)
from group_llm_agent.runtime import FixedReplyProcessor, TelegramPollingService

logger = logging.getLogger(__name__)

ClientFactory = Callable[..., TelegramBotApiClient]


def run(
    environ: Mapping[str, str] | None = None,
    *,
    client_factory: ClientFactory = TelegramBotApiClient,
    sleep: Callable[[float], None] = default_sleep,
) -> int:
    try:
        settings = Settings.from_env(environ)
    except ConfigError as exc:
        logging.basicConfig(level=logging.INFO, format=_log_format())
        logger.error("configuration_error setting=%s detail=%s", exc.setting, exc)
        return 2

    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format=_log_format(),
        force=True,
    )

    store: SQLiteDeliveryLedger | None = None
    try:
        store = SQLiteDeliveryLedger(settings.database_path)
        store.initialize()
        client = client_factory(
            settings.telegram_bot_token,
            timeout_seconds=max(30, settings.telegram_polling_timeout_seconds + 5),
        )
        identity = client.get_me()
        bot_user_id, bot_username = _validated_identity(identity)

        adapter = TelegramAdapter(bot_username=bot_username)
        processor = FixedReplyProcessor(
            allowed_chat_id=settings.telegram_chat_id,
            bot_user_id=bot_user_id,
            client=client,
            store=store,
        )
        service = TelegramPollingService(
            client=client,
            adapter=adapter,
            processor=processor,
            polling_timeout_seconds=settings.telegram_polling_timeout_seconds,
            retry_delay_seconds=settings.telegram_retry_delay_seconds,
            sleep=sleep,
        )

        logger.info(
            "telegram_identity_verified bot_id=%s username=%s chat_id=%s",
            bot_user_id,
            bot_username or "(none)",
            settings.telegram_chat_id,
        )
        logger.info("telegram_polling_started")
        service.run_forever()
    except KeyboardInterrupt:
        logger.info("shutdown_requested")
        return 0
    except TelegramApiError as exc:
        logger.error("telegram_startup_failed error=%s", exc)
        return 3
    except (OSError, sqlite3.Error) as exc:
        logger.error("local_startup_failed error_type=%s", type(exc).__name__)
        return 4
    finally:
        if store is not None:
            store.close()

    return 0


def _validated_identity(identity: dict[str, Any]) -> tuple[str, str | None]:
    bot_id = identity.get("id")
    if (
        isinstance(bot_id, bool)
        or not isinstance(bot_id, int)
        or identity.get("is_bot") is not True
    ):
        raise TelegramApiError("getMe", "invalid_identity")
    username_value = identity.get("username")
    username = str(username_value) if username_value else None
    return str(bot_id), username


def _log_format() -> str:
    return "%(asctime)s %(levelname)s %(name)s %(message)s"
