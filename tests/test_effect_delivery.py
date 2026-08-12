from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from helpers import temporary_database

from group_llm_agent.database import SQLiteDatabase
from group_llm_agent.effect_bundle import BundleStatus, EffectBundleRepository
from group_llm_agent.effect_delivery import ExternalEffectDelivery
from group_llm_agent.events import (
    EffectRequest,
    FinalEffect,
    FinalEffectKind,
    PersonaSnapshot,
    TelegramMessage,
    TriggerCategory,
    TriggerPath,
)
from group_llm_agent.expression import file_sha256, load_expression_catalog
from group_llm_agent.messages import MessageRepository
from group_llm_agent.platforms.telegram import SentMessage, TelegramApiError
from group_llm_agent.runs import RunRepository
from group_llm_agent.temporal import TemporalContextFactory
from group_llm_agent.temporal_audit import TemporalAuditRepository

_CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3/catalog.json"
)


class _Telegram:
    def __init__(
        self,
        *,
        sticker_error: TelegramApiError | None = None,
        message_error: TelegramApiError | None = None,
        unique_id: str = "unique-1",
    ) -> None:
        self.sticker_error = sticker_error
        self.message_error = message_error
        self.unique_id = unique_id
        self.stickers = 0
        self.messages = 0

    def send_sticker(self, **_kwargs: object) -> SentMessage:
        self.stickers += 1
        if self.sticker_error is not None:
            raise self.sticker_error
        return SentMessage("900", self.unique_id)

    def send_message(self, **_kwargs: object) -> SentMessage:
        self.messages += 1
        if self.message_error is not None:
            raise self.message_error
        return SentMessage("901")


def _enabled_catalog():
    candidate = load_expression_catalog(
        _CATALOG_PATH,
        expected_sha256=file_sha256(_CATALOG_PATH),
        allowed_statuses=frozenset({"candidate"}),
        verify_assets=False,
    )
    entries = tuple(
        replace(
            item,
            status="enabled" if index == 0 else "candidate",
            telegram_file_id="file-1" if index == 0 else None,
            telegram_file_unique_id="unique-1" if index == 0 else None,
        )
        for index, item in enumerate(candidate.entries)
    )
    return replace(candidate, status="enabled", entries=entries)


def _event() -> TelegramMessage:
    return TelegramMessage(
        event_id="event-1",
        group_id="-1001",
        message_id="10",
        sender_id="user-1",
        sender_display_name="Member",
        text="你好呀",
        timestamp=datetime(2026, 8, 2, tzinfo=UTC),
    )


def _final(catalog) -> FinalEffect:
    persona = PersonaSnapshot(
        persona_id=catalog.persona_id,
        persona_version=catalog.persona_version,
        persona_digest=catalog.persona_digest,
    )
    return FinalEffect(
        kind=FinalEffectKind.STICKER,
        reason_code="greeting",
        persona=persona,
        sticker_id=catalog.entries[0].semantic_id,
        catalog_version=catalog.catalog_version,
        catalog_digest=catalog.digest,
        fallback_text="我在呀。",
        sticker_eligible=True,
        sticker_eligibility_reason="ordinary_social_turn",
    )


def _composite(catalog) -> FinalEffect:
    return replace(
        _final(catalog),
        kind=FinalEffectKind.REPLY_WITH_STICKER,
        text="我在呀。",
    )


class ExternalEffectDeliveryTests(unittest.TestCase):
    def _delivery(self, database, client: _Telegram, catalog):
        return ExternalEffectDelivery(
            client=client,  # type: ignore[arg-type]
            messages=MessageRepository(database),
            runs=RunRepository(database),
            bot_user_id="bot-1",
            bot_display_name="Lezhi",
            expression_catalog_provider=lambda: catalog,
        )

    def test_sticker_success_claims_once_and_rechecks_returned_identity(self) -> None:
        catalog = _enabled_catalog()
        final = _final(catalog)
        with temporary_database() as database:
            client = _Telegram()
            delivery = self._delivery(database, client, catalog)
            self.assertEqual(
                "sticker_sent",
                delivery.deliver(event=_event(), final=final, active_persona=final.persona),
            )
            self.assertEqual(
                "duplicate",
                delivery.deliver(event=_event(), final=final, active_persona=final.persona),
            )
            record = EffectBundleRepository(database).get(
                chat_id="-1001", trigger_event_id="event-1"
            )
            assert record is not None
            self.assertEqual(BundleStatus.COMPLETED, record.status)
            self.assertEqual("sticker", record.requested_form)
            self.assertEqual("sent", record.components[0].status.value)
            self.assertEqual(1, client.stickers)

    def test_uncertain_failure_and_identity_mismatch_never_fallback(self) -> None:
        catalog = _enabled_catalog()
        final = _final(catalog)
        for client in (
            _Telegram(sticker_error=TelegramApiError("sendSticker", "timeout")),
            _Telegram(sticker_error=TelegramApiError("sendSticker", "http_error", 503)),
            _Telegram(unique_id="wrong-unique"),
        ):
            with self.subTest(client=client), temporary_database() as database:
                delivery = self._delivery(database, client, catalog)
                self.assertEqual(
                    "send_uncertain",
                    delivery.deliver(event=_event(), final=final, active_persona=final.persona),
                )
                self.assertEqual(0, client.messages)

    def test_confirmed_sticker_failure_does_not_send_fallback_text(self) -> None:
        catalog = _enabled_catalog()
        final = _final(catalog)
        with temporary_database() as database:
            client = _Telegram(sticker_error=TelegramApiError("sendSticker", "api_error", 400))
            delivery = self._delivery(database, client, catalog)
            self.assertEqual(
                "send_failed",
                delivery.deliver(event=_event(), final=final, active_persona=final.persona),
            )
            record = EffectBundleRepository(database).get(
                chat_id="-1001", trigger_event_id="event-1"
            )
            assert record is not None
            self.assertEqual(BundleStatus.FAILED, record.status)
            self.assertEqual((1, 0), (client.stickers, client.messages))

    def test_composite_is_text_then_sticker_and_each_component_is_claimed_once(self) -> None:
        catalog = _enabled_catalog()
        final = _composite(catalog)
        with temporary_database() as database:
            client = _Telegram()
            delivery = self._delivery(database, client, catalog)

            self.assertEqual(
                "composite_sent",
                delivery.deliver(event=_event(), final=final, active_persona=final.persona),
            )
            record = EffectBundleRepository(database).get(
                chat_id="-1001", trigger_event_id="event-1"
            )
            assert record is not None
            self.assertEqual(BundleStatus.COMPLETED, record.status)
            self.assertEqual(
                ["text", "sticker"], [item.component_kind for item in record.components]
            )
            self.assertEqual(["sent", "sent"], [item.status.value for item in record.components])
            self.assertEqual((1, 1), (client.stickers, client.messages))
            self.assertEqual(
                "duplicate",
                delivery.deliver(event=_event(), final=final, active_persona=final.persona),
            )
            self.assertEqual((1, 1), (client.stickers, client.messages))

    def test_composite_text_failure_skips_sticker_and_uncertain_text_is_not_retried(self) -> None:
        catalog = _enabled_catalog()
        final = _composite(catalog)
        for error, expected in (
            (TelegramApiError("sendMessage", "api_error", 400), "send_failed"),
            (TelegramApiError("sendMessage", "timeout"), "send_uncertain"),
        ):
            with self.subTest(error=error.category), temporary_database() as database:
                client = _Telegram(message_error=error)
                delivery = self._delivery(database, client, catalog)
                self.assertEqual(
                    expected,
                    delivery.deliver(event=_event(), final=final, active_persona=final.persona),
                )
                record = EffectBundleRepository(database).get(
                    chat_id="-1001", trigger_event_id="event-1"
                )
                assert record is not None
                self.assertEqual("skipped", record.components[1].status.value)
                self.assertEqual((0, 1), (client.stickers, client.messages))

    def test_composite_sticker_failure_is_terminal_text_only_degradation(self) -> None:
        catalog = _enabled_catalog()
        final = _composite(catalog)
        with temporary_database() as database:
            client = _Telegram(sticker_error=TelegramApiError("sendSticker", "api_error", 400))
            delivery = self._delivery(database, client, catalog)
            self.assertEqual(
                "text_sent_sticker_failed",
                delivery.deliver(event=_event(), final=final, active_persona=final.persona),
            )
            record = EffectBundleRepository(database).get(
                chat_id="-1001", trigger_event_id="event-1"
            )
            assert record is not None
            self.assertEqual(BundleStatus.DEGRADED, record.status)
            self.assertEqual(["sent", "failed"], [item.status.value for item in record.components])
            self.assertEqual((1, 1), (client.stickers, client.messages))

    def test_stale_attempt_cannot_claim_bundle_before_current_attempt(self) -> None:
        catalog = _enabled_catalog()
        event = _event()
        request = EffectRequest(
            request_id="effect:attempt-race",
            trigger_path=TriggerPath.DIRECT,
            trigger_category=TriggerCategory.DIRECT_PLATFORM,
            trigger_reason="direct",
            message=event,
            persona=_final(catalog).persona,
            deadline_at=event.timestamp + timedelta(seconds=30),
        )
        with temporary_database() as database:
            stale = _complete_attempt(
                database,
                request=request,
                final=replace(_final(catalog), reason_code="attempt_one"),
                captured_at=datetime(2026, 8, 2, 0, 0, 1, tzinfo=UTC),
            )
            current = _complete_attempt(
                database,
                request=request,
                final=replace(_final(catalog), reason_code="attempt_two"),
                captured_at=datetime(2026, 8, 2, 0, 0, 2, tzinfo=UTC),
            )
            client = _Telegram()
            delivery = self._delivery(database, client, catalog)

            self.assertEqual(
                "duplicate",
                delivery.deliver(event=event, final=stale, active_persona=stale.persona),
            )
            self.assertEqual(0, client.stickers)
            self.assertEqual(
                "sticker_sent",
                delivery.deliver(event=event, final=current, active_persona=current.persona),
            )
            self.assertEqual(1, client.stickers)

            record = EffectBundleRepository(database).get(
                chat_id=event.group_id,
                trigger_event_id=event.event_id,
            )
            assert record is not None
            self.assertEqual(current.effect_run_id, record.effect_run_id)
            self.assertEqual(current.execution_attempt, record.execution_attempt)
            self.assertEqual("attempt_two", record.reason_code)
            with database.connect() as connection:
                run = connection.execute(
                    "SELECT id, execution_attempt, status, reason_code FROM effect_runs"
                ).fetchone()
                audit = connection.execute(
                    "SELECT effect_run_id, execution_attempt, status FROM temporal_answer_audit"
                ).fetchone()
            self.assertEqual(
                (current.effect_run_id, current.execution_attempt, "sticker", "attempt_two"),
                tuple(run),
            )
            self.assertEqual(
                (current.effect_run_id, current.execution_attempt, "completed"),
                tuple(audit),
            )
            with self.assertRaisesRegex(ValueError, "already claimed"):
                RunRepository(database).start_effect_attempt(request)


def _complete_attempt(
    database: SQLiteDatabase,
    *,
    request: EffectRequest,
    final: FinalEffect,
    captured_at: datetime,
) -> FinalEffect:
    runs = RunRepository(database)
    attempt = runs.start_effect_attempt(request)
    context = TemporalContextFactory(clock=lambda: captured_at).sample(
        group_timezone="Asia/Shanghai"
    )
    audit = TemporalAuditRepository(database)
    audit.record_sample(
        effect_run_id=attempt.effect_run_id,
        execution_attempt=attempt.execution_attempt,
        model_call_ordinal=1,
        context=context,
    )
    bound = replace(
        final,
        effect_run_id=attempt.effect_run_id,
        execution_attempt=attempt.execution_attempt,
    )
    audit.finalize(
        effect_run_id=attempt.effect_run_id,
        execution_attempt=attempt.execution_attempt,
        chat_id=request.chat_id,
        trigger_event_id=request.trigger_event_id,
        source_kind="inbound",
        context=context,
        freshness_mode=None,
        web_requested=False,
        status="completed",
    )
    runs.complete_effect_run(
        effect_run_id=attempt.effect_run_id,
        effect=bound,
        model_call_count=1,
        tool_call_count=0,
        execution_attempt=attempt.execution_attempt,
    )
    return bound


if __name__ == "__main__":
    unittest.main()
