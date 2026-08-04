from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from helpers import temporary_database

from group_llm_agent.effect_bundle import (
    BundleStatus,
    ComponentStatus,
    EffectBundleRepository,
)
from group_llm_agent.events import (
    FinalEffect,
    FinalEffectKind,
    PersonaSnapshot,
    TelegramMessage,
)

_PERSONA = PersonaSnapshot("lezhi", "lezhi-v2.0", "p" * 64)
_CATALOG_VERSION = "lezhi-expression-v0.3"
_CATALOG_DIGEST = "c" * 64


def _event(index: int) -> TelegramMessage:
    return TelegramMessage(
        event_id=f"event-{index}",
        group_id="-1001",
        message_id=str(index),
        sender_id="member-1",
        sender_display_name="Member",
        text="你好呀",
        timestamp=datetime(2026, 8, 4, tzinfo=UTC),
    )


def _text_final() -> FinalEffect:
    return FinalEffect(
        kind=FinalEffectKind.REPLY,
        reason_code="ordinary_social_turn",
        persona=_PERSONA,
        text="我在呀。",
        catalog_version=_CATALOG_VERSION,
        catalog_digest=_CATALOG_DIGEST,
        sticker_eligible=True,
        sticker_eligibility_reason="light_interaction",
    )


def _composite_final() -> FinalEffect:
    return replace(
        _text_final(),
        kind=FinalEffectKind.REPLY_WITH_STICKER,
        sticker_id="lezhi.hello_wave.a01",
    )


class EffectBundleRepositoryTests(unittest.TestCase):
    def test_prepare_is_unique_and_never_persists_message_text(self) -> None:
        with temporary_database() as database:
            repository = EffectBundleRepository(database)
            first = repository.prepare(
                event=_event(1),
                final=_composite_final(),
                bot_user_id="bot-1",
            )
            duplicate = repository.prepare(
                event=_event(1),
                final=_composite_final(),
                bot_user_id="bot-1",
            )

            assert first is not None
            self.assertIsNone(duplicate)
            self.assertEqual("text_sticker", first.requested_form)
            self.assertEqual(
                (4, None), tuple(item.text_character_count for item in first.components)
            )
            connection = database.connect()
            try:
                columns = {
                    str(row[1])
                    for table in ("effect_bundles", "effect_bundle_components")
                    for row in connection.execute(f"PRAGMA table_info({table})")
                }
            finally:
                connection.close()
            self.assertNotIn("text", columns)
            self.assertNotIn("response_text", columns)

    def test_restart_after_text_send_never_sends_or_claims_late_sticker(self) -> None:
        with temporary_database() as database:
            repository = EffectBundleRepository(database)
            record = repository.prepare(
                event=_event(1),
                final=_composite_final(),
                bot_user_id="bot-1",
            )
            assert record is not None
            text_id = repository.claim_component(bundle_id=record.bundle_id, ordinal=1)
            assert text_id is not None
            self.assertTrue(repository.mark_sent(text_id, platform_message_id="901"))

            self.assertEqual(1, repository.reconcile_incomplete())
            reconciled = repository.get(chat_id="-1001", trigger_event_id="event-1")
            assert reconciled is not None
            self.assertEqual(BundleStatus.DEGRADED, reconciled.status)
            self.assertEqual(
                (ComponentStatus.SENT, ComponentStatus.SKIPPED),
                tuple(item.status for item in reconciled.components),
            )
            self.assertIsNone(repository.claim_component(bundle_id=record.bundle_id, ordinal=2))

    def test_restart_after_sticker_claim_is_uncertain_and_terminal(self) -> None:
        with temporary_database() as database:
            repository = EffectBundleRepository(database)
            record = repository.prepare(
                event=_event(1),
                final=replace(
                    _composite_final(),
                    kind=FinalEffectKind.STICKER,
                    text=None,
                ),
                bot_user_id="bot-1",
            )
            assert record is not None
            self.assertIsNotNone(repository.claim_component(bundle_id=record.bundle_id, ordinal=1))

            self.assertEqual(1, repository.reconcile_incomplete())
            reconciled = repository.get(chat_id="-1001", trigger_event_id="event-1")
            assert reconciled is not None
            self.assertEqual(BundleStatus.UNCERTAIN, reconciled.status)
            self.assertEqual(ComponentStatus.UNCERTAIN, reconciled.components[0].status)
            self.assertEqual(0, repository.reconcile_incomplete())

    def test_metrics_require_30_exact_snapshot_eligible_visible_bundles(self) -> None:
        with temporary_database() as database:
            repository = EffectBundleRepository(database)
            for index in range(1, 31):
                final = _composite_final() if index <= 12 else _text_final()
                record = repository.prepare(
                    event=_event(index),
                    final=final,
                    bot_user_id="bot-1",
                )
                assert record is not None
                for component in record.components:
                    component_id = repository.claim_component(
                        bundle_id=record.bundle_id,
                        ordinal=component.ordinal,
                    )
                    assert component_id is not None
                    repository.mark_sent(
                        component_id,
                        platform_message_id=f"sent-{index}-{component.ordinal}",
                    )
                repository.finalize(bundle_id=record.bundle_id)

            current = datetime.now(UTC) + timedelta(seconds=1)
            metrics = repository.metrics(
                bot_user_id="bot-1",
                persona_version=_PERSONA.persona_version,
                persona_digest=_PERSONA.persona_digest,
                catalog_version=_CATALOG_VERSION,
                catalog_digest=_CATALOG_DIGEST,
                now=current,
            )
            self.assertEqual("ready", metrics.status)
            self.assertEqual(
                (30, 12, 18),
                (
                    metrics.sample_count,
                    metrics.sticker_bearing_count,
                    metrics.text_only_count,
                ),
            )
            self.assertEqual(0.4, metrics.sticker_bearing_rate)


if __name__ == "__main__":
    unittest.main()
