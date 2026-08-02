from __future__ import annotations

import json
import os
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from group_llm_agent.expression import ExpressionCatalogError, file_sha256, load_expression_catalog
from group_llm_agent.expression_manage import (
    TelegramStickerMapping,
    approve_expression_catalog,
    attach_telegram_mapping,
    enable_expression_catalog,
)

_SOURCE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3"
)


@contextmanager
def _catalog_fixture() -> Iterator[Path]:
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        raw = json.loads((_SOURCE_ROOT / "catalog.json").read_text(encoding="utf-8"))
        path = root / "catalog.json"
        path.write_bytes((_SOURCE_ROOT / "catalog.json").read_bytes())
        for entry in raw["entries"]:
            for relative in (
                entry["assets"]["master_path"],
                entry["assets"]["telegram_path"],
            ):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                os.link(_SOURCE_ROOT / relative, target)
        yield path


class ExpressionPromotionTests(unittest.TestCase):
    def test_confirmation_mapping_and_enable_are_digest_bound(self) -> None:
        with _catalog_fixture() as path:
            candidate_sha = file_sha256(path)
            with self.assertRaisesRegex(
                ExpressionCatalogError, "explicit_user_confirmation_required"
            ):
                approve_expression_catalog(
                    path,
                    expected_candidate_sha256=candidate_sha,
                    approval_reference="not-confirmed",
                    approved_semantic_ids=frozenset({"lezhi.hello_wave.a01"}),
                )

            approved_sha = approve_expression_catalog(
                path,
                expected_candidate_sha256=candidate_sha,
                approval_reference="user-confirmed:preview-2026-08-02",
                approved_semantic_ids=frozenset({"lezhi.hello_wave.a01"}),
            )
            ready_sha = attach_telegram_mapping(
                path,
                expected_approved_sha256=approved_sha,
                sticker_set_name="lezhi_test_by_bot",
                owner_user_id="42",
                verification_reference="telegram-smoke:controlled-chat-1",
                mappings=(
                    TelegramStickerMapping(
                        semantic_id="lezhi.hello_wave.a01",
                        file_id="file-1",
                        file_unique_id="unique-1",
                    ),
                ),
            )
            with self.assertRaisesRegex(
                ExpressionCatalogError, "explicit_enable_confirmation_required"
            ):
                enable_expression_catalog(
                    path,
                    expected_telegram_ready_sha256=ready_sha,
                    activation_reference="automatic",
                )
            enabled_sha = enable_expression_catalog(
                path,
                expected_telegram_ready_sha256=ready_sha,
                activation_reference="user-confirmed-enable:production-subset-1",
            )
            catalog = load_expression_catalog(path, expected_sha256=enabled_sha)
            selected = catalog.entry("lezhi.hello_wave.a01")
            assert selected is not None
            self.assertEqual("enabled", selected.status)
            self.assertEqual("file-1", selected.telegram_file_id)
            other = catalog.entry("lezhi.acknowledged.a02")
            assert other is not None
            self.assertEqual("candidate", other.status)

    def test_mapping_requires_exact_approved_subset_and_smoke_proof(self) -> None:
        with _catalog_fixture() as path:
            approved_sha = approve_expression_catalog(
                path,
                expected_candidate_sha256=file_sha256(path),
                approval_reference="user-confirmed:preview",
                approved_semantic_ids=frozenset({"lezhi.hello_wave.a01"}),
            )
            with self.assertRaisesRegex(ExpressionCatalogError, "invalid_telegram_mapping_proof"):
                attach_telegram_mapping(
                    path,
                    expected_approved_sha256=approved_sha,
                    sticker_set_name="set",
                    owner_user_id="42",
                    verification_reference="not-a-smoke",
                    mappings=(),
                )


if __name__ == "__main__":
    unittest.main()
