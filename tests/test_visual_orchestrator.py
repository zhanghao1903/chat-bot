from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from helpers import temporary_database

from group_llm_agent.events import InboundMedia, MediaKind, PersonaSnapshot, TelegramMessage
from group_llm_agent.expression import file_sha256, load_expression_catalog
from group_llm_agent.messages import MessageRepository
from group_llm_agent.runs import RunRepository
from group_llm_agent.visual_orchestrator import VisualEvidenceService

_CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3/catalog.json"
)


class _NeverMediaLoader:
    def load(self, _media: InboundMedia) -> None:
        raise AssertionError("known sticker must not be downloaded")


class _NeverVision:
    def analyze(self, **_kwargs: object) -> None:
        raise AssertionError("known sticker must not call vision")


class VisualEvidenceServiceTests(unittest.TestCase):
    def test_known_enabled_sticker_uses_catalog_without_download_or_vision(self) -> None:
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
        catalog = replace(candidate, status="enabled", entries=entries)
        persona = PersonaSnapshot(
            persona_id=catalog.persona_id,
            persona_version=catalog.persona_version,
            persona_digest=catalog.persona_digest,
        )
        event = TelegramMessage(
            event_id="event-1",
            group_id="-1001",
            message_id="10",
            sender_id="user-1",
            sender_display_name="Member",
            text="",
            timestamp=datetime(2026, 8, 2, tzinfo=UTC),
            media=InboundMedia(
                kind=MediaKind.STATIC_STICKER,
                file_id="transient-file",
                file_unique_id="unique-1",
                mime_type="image/webp",
            ),
        )
        with temporary_database() as database:
            service = VisualEvidenceService(
                messages=MessageRepository(database),
                runs=RunRepository(database),
                media_loader=_NeverMediaLoader(),  # type: ignore[arg-type]
                vision=_NeverVision(),  # type: ignore[arg-type]
                persona=persona,
                expression_catalog_provider=lambda: catalog,
            )

            resolved = service.resolve(
                event=event,
                deadline=datetime.now(UTC) + timedelta(seconds=5),
            )

            assert resolved.evidence is not None
            self.assertEqual(entries[0].content_summary, resolved.evidence.summary)
            self.assertEqual(("known_enabled_sticker",), resolved.evidence.safety_flags)
            connection = database.connect()
            try:
                audit = connection.execute(
                    "SELECT result_status, model_id FROM media_effect_audit"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(
                ("catalog_match", f"catalog:{catalog.catalog_version}"),
                tuple(audit),
            )


if __name__ == "__main__":
    unittest.main()
