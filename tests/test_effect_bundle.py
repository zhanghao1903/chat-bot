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

    def test_metrics_enforce_sample_boundaries_and_latest_100_window(self) -> None:
        with temporary_database() as database:
            repository = EffectBundleRepository(database)
            for index in range(1, 30):
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
            insufficient = repository.metrics(
                bot_user_id="bot-1",
                persona_version=_PERSONA.persona_version,
                persona_digest=_PERSONA.persona_digest,
                catalog_version=_CATALOG_VERSION,
                catalog_digest=_CATALOG_DIGEST,
                now=current,
            )
            self.assertEqual("insufficient_data", insufficient.status)
            self.assertEqual(29, insufficient.sample_count)
            self.assertIsNone(insufficient.sticker_bearing_rate)

            self._record_visible_bundle(repository, index=30, final=_text_final())
            ready = repository.metrics(
                bot_user_id="bot-1",
                persona_version=_PERSONA.persona_version,
                persona_digest=_PERSONA.persona_digest,
                catalog_version=_CATALOG_VERSION,
                catalog_digest=_CATALOG_DIGEST,
                now=datetime.now(UTC) + timedelta(seconds=1),
            )
            self.assertEqual("ready", ready.status)
            self.assertEqual(
                (30, 12, 18),
                (
                    ready.sample_count,
                    ready.sticker_bearing_count,
                    ready.text_only_count,
                ),
            )
            self.assertEqual(0.4, ready.sticker_bearing_rate)

            for index in range(31, 101):
                self._record_visible_bundle(repository, index=index, final=_text_final())
            at_limit = repository.metrics(
                bot_user_id="bot-1",
                persona_version=_PERSONA.persona_version,
                persona_digest=_PERSONA.persona_digest,
                catalog_version=_CATALOG_VERSION,
                catalog_digest=_CATALOG_DIGEST,
                now=datetime.now(UTC) + timedelta(seconds=1),
            )
            self.assertEqual((100, 12), (at_limit.sample_count, at_limit.sticker_bearing_count))

            self._record_visible_bundle(repository, index=101, final=_text_final())
            limited = repository.metrics(
                bot_user_id="bot-1",
                persona_version=_PERSONA.persona_version,
                persona_digest=_PERSONA.persona_digest,
                catalog_version=_CATALOG_VERSION,
                catalog_digest=_CATALOG_DIGEST,
                now=datetime.now(UTC) + timedelta(seconds=1),
            )
            self.assertEqual((100, 11), (limited.sample_count, limited.sticker_bearing_count))

            self._record_visible_bundle(
                repository,
                index=102,
                final=replace(
                    _text_final(),
                    sticker_eligible=False,
                    sticker_eligibility_reason="necessary_text",
                ),
            )
            failed = repository.prepare(
                event=_event(103),
                final=_text_final(),
                bot_user_id="bot-1",
            )
            assert failed is not None
            component_id = repository.claim_component(bundle_id=failed.bundle_id, ordinal=1)
            assert component_id is not None
            repository.mark_failed(component_id, error_code="explicit_failure")
            repository.finalize(bundle_id=failed.bundle_id)
            excluded = repository.metrics(
                bot_user_id="bot-1",
                persona_version=_PERSONA.persona_version,
                persona_digest=_PERSONA.persona_digest,
                catalog_version=_CATALOG_VERSION,
                catalog_digest=_CATALOG_DIGEST,
                now=datetime.now(UTC) + timedelta(seconds=1),
            )
            self.assertEqual(
                (100, 11),
                (excluded.sample_count, excluded.sticker_bearing_count),
            )

    def test_metrics_isolate_snapshot_time_and_mixed_component_failure(self) -> None:
        with temporary_database() as database:
            repository = EffectBundleRepository(database)
            for index in range(1, 31):
                self._record_visible_bundle(
                    repository,
                    index=index,
                    final=_composite_final() if index <= 12 else _text_final(),
                )

            wrong_snapshot = replace(_text_final(), catalog_digest="d" * 64)
            self._record_visible_bundle(repository, index=31, final=wrong_snapshot)

            old = repository.prepare(
                event=_event(32),
                final=_text_final(),
                bot_user_id="bot-1",
            )
            assert old is not None
            old_component = repository.claim_component(bundle_id=old.bundle_id, ordinal=1)
            assert old_component is not None
            repository.mark_sent(old_component, platform_message_id="old")
            repository.finalize(bundle_id=old.bundle_id)

            boundary = repository.prepare(
                event=_event(33),
                final=_text_final(),
                bot_user_id="bot-1",
            )
            assert boundary is not None
            boundary_component = repository.claim_component(
                bundle_id=boundary.bundle_id,
                ordinal=1,
            )
            assert boundary_component is not None
            repository.mark_sent(boundary_component, platform_message_id="boundary")
            repository.finalize(bundle_id=boundary.bundle_id)

            mixed = repository.prepare(
                event=_event(34),
                final=_composite_final(),
                bot_user_id="bot-1",
            )
            assert mixed is not None
            text_component = repository.claim_component(bundle_id=mixed.bundle_id, ordinal=1)
            assert text_component is not None
            repository.mark_sent(text_component, platform_message_id="mixed-text")
            sticker_component = repository.claim_component(
                bundle_id=mixed.bundle_id,
                ordinal=2,
            )
            assert sticker_component is not None
            repository.mark_failed(sticker_component, error_code="explicit_failure")
            repository.finalize(bundle_id=mixed.bundle_id)

            current = datetime.now(UTC) + timedelta(seconds=2)
            with database.transaction() as connection:
                connection.execute(
                    "UPDATE effect_bundles SET completed_at = ? WHERE bundle_id = ?",
                    ((current - timedelta(days=7, microseconds=1)).isoformat(), old.bundle_id),
                )
                connection.execute(
                    "UPDATE effect_bundles SET completed_at = ? WHERE bundle_id = ?",
                    ((current - timedelta(days=7)).isoformat(), boundary.bundle_id),
                )

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
                (32, 12, 20),
                (
                    metrics.sample_count,
                    metrics.sticker_bearing_count,
                    metrics.text_only_count,
                ),
            )

    @staticmethod
    def _record_visible_bundle(
        repository: EffectBundleRepository,
        *,
        index: int,
        final: FinalEffect,
    ) -> None:
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


if __name__ == "__main__":
    unittest.main()
