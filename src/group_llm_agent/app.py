from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable, Mapping
from datetime import timedelta
from time import sleep as default_sleep
from typing import Any

from group_llm_agent.config import ConfigError, Settings
from group_llm_agent.context import ContextAssembler
from group_llm_agent.control import MemoryControlService
from group_llm_agent.database import SQLiteDatabase
from group_llm_agent.delivery import SQLiteDeliveryLedger
from group_llm_agent.effector import EffectorBudgets, WriterEffector
from group_llm_agent.memory import MemoryRepository
from group_llm_agent.messages import MessageRepository
from group_llm_agent.model import (
    ModelRole,
    OpenAICompatibleStructuredModelClient,
    StructuredModelPort,
)
from group_llm_agent.persona import (
    CharacterBundle,
    CharacterBundleError,
    load_character_bundle,
)
from group_llm_agent.platforms.telegram import (
    TelegramAdapter,
    TelegramApiError,
    TelegramBotApiClient,
)
from group_llm_agent.recognition import RecognitionWorker
from group_llm_agent.recognition_jobs import RecognitionJobRepository
from group_llm_agent.runs import RunRepository
from group_llm_agent.runtime import (
    FixedReplyProcessor,
    MessageProcessor,
    PersonaMessageProcessor,
    RecognitionBackgroundWorker,
    TelegramPollingService,
)
from group_llm_agent.tools import ReadOnlyToolRegistry
from group_llm_agent.trigger import (
    PersonaTriggerDecider,
    PlatformTriggerGate,
    TriggerCoordinator,
)

logger = logging.getLogger(__name__)

ClientFactory = Callable[..., TelegramBotApiClient]
ModelFactory = Callable[[Settings], StructuredModelPort]


def run(
    environ: Mapping[str, str] | None = None,
    *,
    client_factory: ClientFactory = TelegramBotApiClient,
    model_factory: ModelFactory | None = None,
    sleep: Callable[[float], None] = default_sleep,
) -> int:
    try:
        settings = Settings.from_env(environ)
    except ConfigError as exc:
        logging.basicConfig(level=logging.INFO, format=_log_format(), force=True)
        logger.error("configuration_error setting=%s detail=%s", exc.setting, exc)
        return 2

    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format=_log_format(),
        force=True,
    )

    store: SQLiteDeliveryLedger | None = None
    background_worker: RecognitionBackgroundWorker | None = None
    try:
        bundle: CharacterBundle | None = None
        model: StructuredModelPort | None = None
        database: SQLiteDatabase | None = None
        if settings.bot_mode == "fixed":
            store = SQLiteDeliveryLedger(settings.database_path)
            store.initialize()
        else:
            assert settings.persona_bundle_path is not None
            assert settings.persona_expected_sha256 is not None
            bundle = load_character_bundle(
                settings.persona_bundle_path,
                expected_sha256=settings.persona_expected_sha256,
            )
            model = (
                model_factory(settings)
                if model_factory is not None
                else _configured_model(settings)
            )
            database = SQLiteDatabase(settings.database_path)
            database.initialize()

        client = client_factory(
            settings.telegram_bot_token,
            timeout_seconds=max(30, settings.telegram_polling_timeout_seconds + 5),
        )
        identity = client.get_me()
        bot_user_id, bot_username = _validated_identity(identity)

        adapter = TelegramAdapter(bot_username=bot_username)
        processor: MessageProcessor
        if settings.bot_mode == "fixed":
            assert store is not None
            processor = FixedReplyProcessor(
                allowed_chat_id=settings.telegram_chat_id,
                bot_user_id=bot_user_id,
                client=client,
                store=store,
            )
        else:
            assert bundle is not None
            assert model is not None
            assert database is not None
            processor, background_worker = _persona_runtime(
                settings=settings,
                client=client,
                bot_user_id=bot_user_id,
                bot_display_name=bot_username or f"bot-{bot_user_id}",
                bundle=bundle,
                model=model,
                database=database,
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
        if background_worker is not None:
            background_worker.start()
        logger.info("telegram_polling_started")
        service.run_forever()
    except KeyboardInterrupt:
        logger.info("shutdown_requested")
        return 0
    except TelegramApiError as exc:
        logger.error("telegram_startup_failed error=%s", exc)
        return 3
    except CharacterBundleError as exc:
        logger.error("persona_startup_failed category=%s", exc.category)
        return 2
    except ValueError as exc:
        logger.error("persona_startup_failed error_type=%s", type(exc).__name__)
        return 2
    except (OSError, sqlite3.Error) as exc:
        logger.error("local_startup_failed error_type=%s", type(exc).__name__)
        return 4
    finally:
        if background_worker is not None:
            background_worker.stop()
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


def _configured_model(settings: Settings) -> StructuredModelPort:
    if settings.model_provider != "openai_compatible":
        raise ValueError("Unsupported model provider")
    assert settings.model_base_url is not None
    assert settings.model_api_key is not None
    assert settings.writer_model is not None
    assert settings.trigger_model is not None
    assert settings.recognition_model is not None
    return OpenAICompatibleStructuredModelClient(
        base_url=settings.model_base_url,
        api_key=settings.model_api_key,
        models={
            ModelRole.WRITER: settings.writer_model,
            ModelRole.TRIGGER: settings.trigger_model,
            ModelRole.RECOGNITION: settings.recognition_model,
        },
        timeout_seconds=30,
    )


def _persona_runtime(
    *,
    settings: Settings,
    client: TelegramBotApiClient,
    bot_user_id: str,
    bot_display_name: str,
    bundle: CharacterBundle,
    model: StructuredModelPort,
    database: SQLiteDatabase,
) -> tuple[PersonaMessageProcessor, RecognitionBackgroundWorker | None]:
    messages = MessageRepository(database)
    messages.policies.ensure(
        chat_id=settings.telegram_chat_id,
        raw_retention_days=settings.raw_message_retention_days,
    )
    messages.policies.activate_persona(
        chat_id=settings.telegram_chat_id,
        persona=bundle.snapshot,
    )
    memory = MemoryRepository(database)
    runs = RunRepository(database)
    contexts = ContextAssembler(
        messages=messages,
        memory=memory,
        recognition_policy_version="recognition-v1",
    )
    tools = ReadOnlyToolRegistry(messages=messages, memory=memory, runs=runs)
    effector = WriterEffector(
        model=model,
        contexts=contexts,
        tools=tools,
        runs=runs,
        budgets=EffectorBudgets(
            maximum_model_calls=settings.effect_max_model_calls,
            maximum_tool_calls=settings.effect_max_tool_calls,
        ),
    )
    platform_gate = PlatformTriggerGate(
        allowed_chat_id=settings.telegram_chat_id,
        bot_user_id=bot_user_id,
        messages=messages,
        runs=runs,
    )
    trigger_decider = PersonaTriggerDecider(
        model=model,
        runs=runs,
        timeout_seconds=settings.trigger_decision_timeout_seconds,
    )
    triggers = TriggerCoordinator(
        platform_gate=platform_gate,
        persona_decider=trigger_decider,
        contexts=contexts,
        effect_deadline_seconds=settings.effect_deadline_seconds,
    )
    controls = MemoryControlService(
        allowed_chat_id=settings.telegram_chat_id,
        bot_user_id=bot_user_id,
        telegram=client,
        messages=messages,
        memory=memory,
        runs=runs,
        capability_available=settings.member_memory_capability == "available",
    )
    processor = PersonaMessageProcessor(
        mode=settings.bot_mode,
        allowed_chat_id=settings.telegram_chat_id,
        bot_user_id=bot_user_id,
        bot_display_name=bot_display_name,
        client=client,
        bundle=bundle,
        messages=messages,
        runs=runs,
        controls=controls,
        triggers=triggers,
        effector=effector,
    )
    if settings.member_memory_capability != "available":
        return processor, None
    jobs = RecognitionJobRepository(
        database,
        maximum_attempts=settings.recognition_max_attempts,
    )
    recognition = RecognitionWorker(
        database=database,
        model=model,
        messages=messages,
        jobs=jobs,
        model_timeout=timedelta(seconds=settings.recognition_timeout_seconds),
        lease_duration=timedelta(seconds=settings.recognition_timeout_seconds + 15),
    )
    return processor, RecognitionBackgroundWorker(worker=recognition, bundle=bundle)


def _log_format() -> str:
    return "%(asctime)s %(levelname)s %(name)s %(message)s"
