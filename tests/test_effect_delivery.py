from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from helpers import temporary_database

from group_llm_agent.effect_delivery import ExternalEffectDelivery
from group_llm_agent.events import (
    ExternalEffectStatus,
    FinalEffect,
    FinalEffectKind,
    PersonaSnapshot,
    TelegramMessage,
)
from group_llm_agent.expression import file_sha256, load_expression_catalog
from group_llm_agent.messages import MessageRepository
from group_llm_agent.platforms.telegram import SentMessage, TelegramApiError
from group_llm_agent.runs import RunRepository

_CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3/catalog.json"
)


class _Telegram:
    def __init__(
        self,
        *,
        sticker_error: TelegramApiError | None = None,
        unique_id: str = "unique-1",
    ) -> None:
        self.sticker_error = sticker_error
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
            record = RunRepository(database).get_external_effect(
                chat_id="-1001", trigger_event_id="event-1"
            )
            assert record is not None
            self.assertEqual(ExternalEffectStatus.SENT, record.status)
            self.assertEqual(1, client.stickers)

    def test_uncertain_failure_and_identity_mismatch_never_fallback(self) -> None:
        catalog = _enabled_catalog()
        final = _final(catalog)
        for client in (
            _Telegram(sticker_error=TelegramApiError("sendSticker", "timeout")),
            _Telegram(unique_id="wrong-unique"),
        ):
            with self.subTest(client=client), temporary_database() as database:
                delivery = self._delivery(database, client, catalog)
                self.assertEqual(
                    "send_uncertain",
                    delivery.deliver(event=_event(), final=final, active_persona=final.persona),
                )
                self.assertEqual(0, client.messages)

    def test_confirmed_failure_uses_one_text_fallback_under_same_claim(self) -> None:
        catalog = _enabled_catalog()
        final = _final(catalog)
        with temporary_database() as database:
            client = _Telegram(sticker_error=TelegramApiError("sendSticker", "api_error", 400))
            delivery = self._delivery(database, client, catalog)
            self.assertEqual(
                "fallback_sent",
                delivery.deliver(event=_event(), final=final, active_persona=final.persona),
            )
            record = RunRepository(database).get_external_effect(
                chat_id="-1001", trigger_event_id="event-1"
            )
            assert record is not None
            self.assertEqual(ExternalEffectStatus.SENT, record.status)
            self.assertEqual("failure_reply", record.delivered_effect_kind.value)  # type: ignore[union-attr]
            self.assertEqual((1, 1), (client.stickers, client.messages))


if __name__ == "__main__":
    unittest.main()
