from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from group_llm_agent.asset_pipeline import CELL_SPECS, LOCKED_SOURCES, build_expression_assets
from group_llm_agent.expression import file_sha256, load_expression_catalog

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_ASSET_ROOT = (
    _REPOSITORY_ROOT
    / "src"
    / "group_llm_agent"
    / "expression_assets"
    / "lezhi"
    / "lezhi-expression-v0.3"
)


class AssetPipelineTests(unittest.TestCase):
    def test_committed_candidate_set_matches_locked_sources_and_grid(self) -> None:
        manifest = json.loads((_ASSET_ROOT / "manifest.json").read_text(encoding="utf-8"))
        catalog_path = _ASSET_ROOT / "catalog.json"
        catalog = load_expression_catalog(
            catalog_path,
            expected_sha256=file_sha256(catalog_path),
            allowed_statuses=frozenset({"candidate"}),
        )

        self.assertEqual("candidate", manifest["status"])
        self.assertIsNone(manifest["approval"])
        self.assertEqual(48, manifest["candidate_count"])
        self.assertEqual(48, len(catalog.entries))
        self.assertEqual(48, len({entry.content_summary for entry in catalog.entries}))
        self.assertEqual(
            [source.sha256 for source in LOCKED_SOURCES],
            [source["sha256"] for source in manifest["source_assets"]],
        )
        self.assertEqual(
            [spec.coordinate for spec in CELL_SPECS],
            [
                f"{entry.source_sheet}{(entry.source_row - 1) * 4 + entry.source_column:02d}"
                for entry in catalog.entries
            ],
        )

    def test_every_candidate_is_transparent_512_and_webp_reopens(self) -> None:
        catalog_path = _ASSET_ROOT / "catalog.json"
        catalog = load_expression_catalog(
            catalog_path,
            expected_sha256=file_sha256(catalog_path),
            allowed_statuses=frozenset({"candidate"}),
        )
        master_digests: set[str] = set()
        telegram_digests: set[str] = set()
        for entry in catalog.entries:
            with Image.open(_ASSET_ROOT / entry.master_path) as master:
                self.assertEqual((512, 512), master.size)
                self.assertEqual("RGBA", master.mode)
                alpha = master.getchannel("A")
                self.assertIsNotNone(alpha.getbbox())
                self.assertTrue(
                    all(
                        alpha.getpixel(point) == 0
                        for point in ((0, 0), (511, 0), (0, 511), (511, 511))
                    )
                )
                opaque_white = sum(
                    1
                    for red, green, blue, value in master.getdata()
                    if value >= 220 and min(red, green, blue) >= 238
                )
                self.assertGreater(opaque_white, 30, entry.semantic_id)
            with Image.open(_ASSET_ROOT / entry.telegram_path) as telegram:
                self.assertEqual((512, 512), telegram.size)
                self.assertEqual("WEBP", telegram.format)
            master_digests.add(entry.master_sha256)
            telegram_digests.add(entry.telegram_sha256)
        self.assertEqual(48, len(master_digests))
        self.assertEqual(48, len(telegram_digests))

    def test_duplicate_visible_text_has_distinct_semantics(self) -> None:
        catalog_path = _ASSET_ROOT / "catalog.json"
        catalog = load_expression_catalog(
            catalog_path,
            expected_sha256=file_sha256(catalog_path),
            allowed_statuses=frozenset({"candidate"}),
        )
        for visible_text in ("好耶", "贴贴"):
            entries = [entry for entry in catalog.entries if entry.visible_text == visible_text]
            self.assertEqual(2, len(entries))
            self.assertEqual(2, len({entry.semantic_id for entry in entries}))
            self.assertEqual(2, len({entry.action for entry in entries}))

    def test_two_clean_builds_are_byte_identical(self) -> None:
        with TemporaryDirectory() as first_tmp, TemporaryDirectory() as second_tmp:
            first = Path(first_tmp) / "lezhi-expression-v0.3"
            second = Path(second_tmp) / "lezhi-expression-v0.3"
            build_expression_assets(_ASSET_ROOT / "sources", first)
            build_expression_assets(_ASSET_ROOT / "sources", second)
            first_files = {
                path.relative_to(first).as_posix(): file_sha256(path)
                for path in first.rglob("*")
                if path.is_file()
            }
            second_files = {
                path.relative_to(second).as_posix(): file_sha256(path)
                for path in second.rglob("*")
                if path.is_file()
            }
            self.assertEqual(first_files, second_files)


if __name__ == "__main__":
    unittest.main()
