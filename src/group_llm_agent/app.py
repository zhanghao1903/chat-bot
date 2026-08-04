from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable, Mapping
from datetime import timedelta
from time import sleep as default_sleep
from typing import Any, Protocol

from group_llm_agent.automation import AutomationRepository
from group_llm_agent.automation_control import AutomationControlService
from group_llm_agent.automation_delivery import AutomationDeliveryRepository
from group_llm_agent.automation_runtime import AutomationBackgroundWorker, AutomationScheduler
from group_llm_agent.config import ConfigError, Settings
from group_llm_agent.context import ContextAssembler
from group_llm_agent.continuity import ConversationContinuityDecider
from group_llm_agent.control import MemoryControlService
from group_llm_agent.database import SQLiteDatabase
from group_llm_agent.delivery import SQLiteDeliveryLedger
from group_llm_agent.effect_bundle import EffectBundleRepository
from group_llm_agent.effector import EffectorBudgets, WriterEffector
from group_llm_agent.expression import ExpressionCatalog, load_expression_catalog
from group_llm_agent.media import MediaLimits, TelegramMediaLoader
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
from group_llm_agent.scheduled_food import ScheduledFoodProcessor
from group_llm_agent.tavily import TavilyClient
from group_llm_agent.tools import ReadOnlyToolRegistry
from group_llm_agent.trigger import (
    PersonaTriggerDecider,
    PlatformTriggerGate,
    TriggerCoordinator,
)
from group_llm_agent.vision import OpenAICompatibleVisionClient, VisionModelPort
from group_llm_agent.web_tools import WebToolSession

logger = logging.getLogger(__name__)

ClientFactory = Callable[..., TelegramBotApiClient]
ModelFactory = Callable[[Settings], StructuredModelPort]
VisionFactory = Callable[[Settings], VisionModelPort]


class BackgroundWorker(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


class BackgroundWorkerGroup:
    def __init__(self, workers: tuple[BackgroundWorker, ...]) -> None:
        self.workers = workers

    def start(self) -> None:
        started: list[BackgroundWorker] = []
        try:
            for worker in self.workers:
                worker.start()
                started.append(worker)
        except Exception:
            for worker in reversed(started):
                worker.stop()
            raise

    def stop(self) -> None:
        for worker in reversed(self.workers):
            worker.stop()


def run(
    environ: Mapping[str, str] | None = None,
    *,
    client_factory: ClientFactory = TelegramBotApiClient,
    model_factory: ModelFactory | None = None,
    vision_factory: VisionFactory | None = None,
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
    background_worker: BackgroundWorker | None = None
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
            logger.info(
                "persona_bundle_loaded persona_id=%s persona_version=%s persona_digest=%s",
                bundle.snapshot.persona_id,
                bundle.snapshot.persona_version,
                bundle.snapshot.persona_digest,
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
                bot_username=bot_username,
                bot_display_name=bot_username or f"bot-{bot_user_id}",
                bundle=bundle,
                model=model,
                database=database,
                vision_factory=vision_factory,
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
    bot_username: str | None,
    bot_display_name: str,
    bundle: CharacterBundle,
    model: StructuredModelPort,
    database: SQLiteDatabase,
    vision_factory: VisionFactory | None = None,
) -> tuple[PersonaMessageProcessor, BackgroundWorker | None]:
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
    bundles = EffectBundleRepository(database)
    contexts = ContextAssembler(
        messages=messages,
        memory=memory,
        recognition_policy_version="recognition-v1",
    )
    tools = ReadOnlyToolRegistry(messages=messages, memory=memory, runs=runs)
    web_session_factory: Callable[[], WebToolSession] | None = None
    if settings.tavily_web_capability == "available" and settings.tavily_api_key is not None:
        tavily_client = TavilyClient(
            api_key=settings.tavily_api_key,
            timeout_seconds=settings.tavily_timeout_seconds,
            project_id=settings.tavily_project_id,
        )

        def _web_session() -> WebToolSession:
            return WebToolSession(client=tavily_client, runs=runs)

        web_session_factory = _web_session
    catalog_provider: Callable[[], ExpressionCatalog] | None = None
    if settings.expression_capability == "enabled":
        assert settings.expression_catalog_path is not None
        assert settings.expression_catalog_sha256 is not None
        catalog_path = settings.expression_catalog_path
        catalog_sha256 = settings.expression_catalog_sha256

        def _load_runtime_catalog() -> ExpressionCatalog:
            return load_expression_catalog(
                catalog_path,
                expected_sha256=catalog_sha256,
                allowed_statuses=frozenset({"enabled"}),
            )

        _load_runtime_catalog()
        catalog_provider = _load_runtime_catalog
    effector = WriterEffector(
        model=model,
        contexts=contexts,
        tools=tools,
        runs=runs,
        budgets=EffectorBudgets(
            maximum_model_calls=settings.effect_max_model_calls,
            ordinary_tool_calls=settings.effect_ordinary_tool_calls,
            maximum_tool_calls=settings.effect_max_tool_calls,
            maximum_web_tool_calls=settings.web_tool_limit,
            maximum_result_characters=settings.tool_result_total_chars,
        ),
        expression_catalog_provider=catalog_provider,
        web_session_factory=web_session_factory,
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
    continuity_decider = ConversationContinuityDecider(
        model=model,
        runs=runs,
        timeout_seconds=settings.trigger_decision_timeout_seconds,
    )
    triggers = TriggerCoordinator(
        platform_gate=platform_gate,
        persona_decider=trigger_decider,
        continuity_decider=continuity_decider,
        contexts=contexts,
        effect_deadline_seconds=settings.effect_deadline_seconds,
    )
    controls = MemoryControlService(
        allowed_chat_id=settings.telegram_chat_id,
        bot_user_id=bot_user_id,
        bot_username=bot_username,
        telegram=client,
        messages=messages,
        memory=memory,
        runs=runs,
        capability_available=settings.member_memory_capability == "available",
    )
    automation_repository = AutomationRepository(database)
    automation_controls = AutomationControlService(
        allowed_chat_id=settings.telegram_chat_id,
        bot_user_id=bot_user_id,
        bot_username=bot_username,
        telegram=client,
        repository=automation_repository,
        runs=runs,
        capability_available=settings.automation_capability == "available",
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
        bundles=bundles,
        controls=controls,
        triggers=triggers,
        effector=effector,
        automation_controls=automation_controls,
        media_loader=(
            TelegramMediaLoader(
                client=client,
                limits=MediaLimits(
                    maximum_download_bytes=settings.media_max_download_bytes,
                    maximum_pixels=settings.media_max_pixels,
                ),
                timeout_seconds=settings.vision_timeout_seconds,
            )
            if settings.vision_capability == "available"
            else None
        ),
        vision=(
            (
                vision_factory(settings)
                if vision_factory is not None
                else OpenAICompatibleVisionClient(
                    base_url=str(settings.model_base_url),
                    api_key=str(settings.model_api_key),
                    model=str(settings.vision_model),
                    timeout_seconds=settings.vision_timeout_seconds,
                )
            )
            if settings.vision_capability == "available"
            else None
        ),
        expression_catalog_provider=catalog_provider,
    )
    workers: list[BackgroundWorker] = []
    if settings.member_memory_capability == "available":
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
        workers.append(RecognitionBackgroundWorker(worker=recognition, bundle=bundle))
    if settings.automation_capability == "available":
        scheduled_food = ScheduledFoodProcessor(
            repository=automation_repository,
            delivery_repository=AutomationDeliveryRepository(database),
            effector=effector,
            telegram=client,
            messages=messages,
            runs=runs,
            bundle=bundle,
            allowed_chat_id=settings.telegram_chat_id,
            bot_user_id=bot_user_id,
            bot_display_name=bot_display_name,
            deadline_seconds=settings.scheduled_effect_deadline_seconds,
        )
        recovered = scheduled_food.recover_inflight()
        if recovered:
            logger.warning("scheduled_effects_recovered_uncertain count=%s", recovered)
        workers.append(
            AutomationBackgroundWorker(
                scheduler=AutomationScheduler(
                    repository=automation_repository,
                    processor=scheduled_food,
                    bot_user_id=bot_user_id,
                    persona=bundle.snapshot,
                ),
                worker_id=f"automation-{bot_user_id}",
                idle_seconds=float(settings.automation_tick_seconds),
            )
        )
    return processor, BackgroundWorkerGroup(tuple(workers)) if workers else None


def _log_format() -> str:
    return "%(asctime)s %(levelname)s %(name)s %(message)s"
