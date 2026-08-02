from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from group_llm_agent.expression import file_sha256, load_expression_catalog
from group_llm_agent.expression_manage import approve_expression_catalog
from group_llm_agent.sticker_publish import StickerPackPublisher, StickerPublishRequest

_SOURCE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3"
)


class _Multipart:
    def upload_sticker_file(
        self, *, owner_user_id: str, content: bytes, filename: str
    ) -> tuple[str, str]:
        self.owner = owner_user_id
        self.content = content
        self.filename = filename
        return "uploaded-file", "uploaded-unique"


class _Telegram:
    def create_new_sticker_set(self, **kwargs: object) -> None:
        self.create = kwargs

    def get_sticker_set(self, *, name: str) -> list[tuple[str, str]]:
        self.name = name
        return [("actual-file", "uploaded-unique")]


class StickerPackPublisherTests(unittest.TestCase):
    def test_publish_uses_only_approved_assets_and_readback_identity(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = _SOURCE_ROOT / "catalog.json"
            raw = json.loads(source.read_text(encoding="utf-8"))
            path = root / "catalog.json"
            path.write_bytes(source.read_bytes())
            for entry in raw["entries"]:
                for relative in (
                    entry["assets"]["master_path"],
                    entry["assets"]["telegram_path"],
                ):
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.link(_SOURCE_ROOT / relative, target)
            approved_sha = approve_expression_catalog(
                path,
                expected_candidate_sha256=file_sha256(path),
                approval_reference="user-confirmed:preview-1",
                approved_semantic_ids=frozenset({"lezhi.hello_wave.a01"}),
            )
            catalog = load_expression_catalog(
                path,
                expected_sha256=approved_sha,
                allowed_statuses=frozenset({"approved"}),
            )
            telegram = _Telegram()
            publisher = StickerPackPublisher(
                telegram=telegram,  # type: ignore[arg-type]
                multipart=_Multipart(),  # type: ignore[arg-type]
            )

            mappings = publisher.publish(
                catalog,
                request=StickerPublishRequest(
                    owner_user_id="42",
                    sticker_set_name="lezhi_test_by_bot",
                    sticker_set_title="Lezhi Test",
                    approved_catalog_sha256=approved_sha,
                ),
            )

            self.assertEqual(1, len(mappings))
            self.assertEqual("actual-file", mappings[0].file_id)
            self.assertEqual("lezhi.hello_wave.a01", mappings[0].semantic_id)
            self.assertEqual("lezhi_test_by_bot", telegram.name)


if __name__ == "__main__":
    unittest.main()
