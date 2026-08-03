from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from group_llm_agent.expression import (
    ExpressionCatalogError,
    canonical_json_bytes,
    file_sha256,
    load_expression_catalog,
    validate_runtime_selection,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_PATH = (
    _REPOSITORY_ROOT
    / "src"
    / "group_llm_agent"
    / "expression_assets"
    / "lezhi"
    / "lezhi-expression-v0.3"
    / "catalog.json"
)


class ExpressionCatalogTests(unittest.TestCase):
    def test_candidate_catalog_is_not_runtime_loadable(self) -> None:
        with self.assertRaisesRegex(ExpressionCatalogError, "catalog_status_not_allowed"):
            load_expression_catalog(
                _CATALOG_PATH,
                expected_sha256=file_sha256(_CATALOG_PATH),
                verify_assets=False,
            )

    def test_digest_and_canonical_json_are_fail_closed(self) -> None:
        with self.assertRaisesRegex(ExpressionCatalogError, "catalog_digest_mismatch"):
            load_expression_catalog(
                _CATALOG_PATH,
                expected_sha256="0" * 64,
                allowed_statuses=frozenset({"candidate"}),
                verify_assets=False,
            )
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "catalog.json"
            raw = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
            path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            with self.assertRaisesRegex(ExpressionCatalogError, "catalog_not_canonical"):
                load_expression_catalog(
                    path,
                    expected_sha256=file_sha256(path),
                    allowed_statuses=frozenset({"candidate"}),
                    verify_assets=False,
                )

    def test_enabled_selection_rechecks_catalog_persona_entry_and_mapping(self) -> None:
        raw = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        raw["status"] = "enabled"
        raw["approval"] = {"confirmed_by": "test", "confirmation_id": "approval-1"}
        raw["telegram_mapping"] = {"set_name": "test_set"}
        for entry in raw["entries"]:
            entry["status"] = "enabled"
            entry["approval"] = {"confirmation_id": "approval-1"}
            entry["telegram_mapping"] = {
                "file_id": f"file-{entry['semantic_id']}",
                "file_unique_id": f"unique-{entry['semantic_id']}",
            }
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "catalog.json"
            path.write_bytes(canonical_json_bytes(raw))
            digest = file_sha256(path)
            catalog = load_expression_catalog(
                path,
                expected_sha256=digest,
                allowed_statuses=frozenset({"enabled"}),
                verify_assets=False,
            )
            entry = validate_runtime_selection(
                catalog,
                semantic_id=raw["entries"][0]["semantic_id"],
                persona_version=raw["persona_version"],
                persona_digest=raw["persona_digest"],
                expected_catalog_version=raw["catalog_version"],
                expected_catalog_digest=digest,
            )
            self.assertEqual(raw["entries"][0]["semantic_id"], entry.semantic_id)

            for kwargs, error in (
                ({"semantic_id": "unknown"}, "expression_not_enabled"),
                ({"persona_digest": "0" * 64}, "persona_snapshot_mismatch"),
                ({"expected_catalog_digest": "0" * 64}, "catalog_snapshot_mismatch"),
            ):
                arguments = {
                    "semantic_id": entry.semantic_id,
                    "persona_version": raw["persona_version"],
                    "persona_digest": raw["persona_digest"],
                    "expected_catalog_version": raw["catalog_version"],
                    "expected_catalog_digest": digest,
                }
                arguments.update(kwargs)
                with self.assertRaisesRegex(ExpressionCatalogError, error):
                    validate_runtime_selection(catalog, **arguments)


if __name__ == "__main__":
    unittest.main()
