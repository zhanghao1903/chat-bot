from __future__ import annotations

import json
import os
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from helpers import temporary_database

from group_llm_agent.avatar import (
    AvatarController,
    approve_avatar_catalog,
    enable_avatar_rotation,
    load_avatar_catalog,
)
from group_llm_agent.expression import ExpressionCatalogError, file_sha256
from group_llm_agent.platforms.telegram import (
    TelegramApiError,
    TelegramProfilePhoto,
)

_SOURCE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "src/group_llm_agent/expression_assets/lezhi/lezhi-expression-v0.3"
)


@contextmanager
def _avatar_fixture() -> Iterator[Path]:
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        source = _SOURCE_ROOT / "avatar-candidates.json"
        raw = json.loads(source.read_text(encoding="utf-8"))
        path = root / "avatar-candidates.json"
        path.write_bytes(source.read_bytes())
        for candidate in raw["candidates"]:
            for relative in (
                candidate["image_path"],
                candidate["circle_preview_path"],
            ):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                os.link(_SOURCE_ROOT / relative, target)
        yield path


class _Telegram:
    def __init__(self, *, fail_readback: bool = False) -> None:
        self.profile_reads = 0
        self.removed = 0
        self.fail_readback = fail_readback

    def get_user_profile_photo(self, *, user_id: str) -> TelegramProfilePhoto | None:
        self.profile_reads += 1
        if self.profile_reads == 1 or self.fail_readback:
            return None
        return TelegramProfilePhoto("new-file", "new-unique", 512, 512)

    def remove_my_profile_photo(self) -> None:
        self.removed += 1


class _Multipart:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.uploads = 0

    def set_static_profile_photo(self, *, jpeg: bytes) -> None:
        self.uploads += 1
        if self.fail:
            raise TelegramApiError("setMyProfilePhoto", "api_error", 400)
        if not jpeg:
            raise AssertionError("avatar bytes must be non-empty")


class AvatarControllerTests(unittest.TestCase):
    def test_confirmation_and_rotation_gates_are_digest_bound(self) -> None:
        with _avatar_fixture() as path:
            candidate_sha = file_sha256(path)
            with self.assertRaisesRegex(
                ExpressionCatalogError, "explicit_avatar_confirmation_required"
            ):
                approve_avatar_catalog(
                    path,
                    expected_candidate_sha256=candidate_sha,
                    approval_reference="automatic",
                    approved_avatar_ids=frozenset({"lezhi-default"}),
                )
            approved_sha = approve_avatar_catalog(
                path,
                expected_candidate_sha256=candidate_sha,
                approval_reference="user-confirmed-avatar:preview-1",
                approved_avatar_ids=frozenset({"lezhi-default", "lezhi-joyful"}),
                approved_sticker_catalog_sha256="a" * 64,
            )
            with self.assertRaisesRegex(
                ExpressionCatalogError, "explicit_rotation_confirmation_required"
            ):
                enable_avatar_rotation(
                    path,
                    expected_approved_sha256=approved_sha,
                    confirmation_reference="automatic",
                )
            enabled_sha = enable_avatar_rotation(
                path,
                expected_approved_sha256=approved_sha,
                confirmation_reference="user-confirmed-avatar-rotation:moods-v1",
            )
            enabled = load_avatar_catalog(path, expected_sha256=enabled_sha)
            self.assertTrue(enabled.automatic_rotation_enabled)

    def test_stable_global_mood_obeys_duration_scope_and_cooldown(self) -> None:
        with _avatar_fixture() as path, temporary_database() as database:
            approved_sha = approve_avatar_catalog(
                path,
                expected_candidate_sha256=file_sha256(path),
                approval_reference="user-confirmed-avatar:preview-1",
                approved_avatar_ids=frozenset({"lezhi-default", "lezhi-joyful"}),
                approved_sticker_catalog_sha256="a" * 64,
            )
            enabled_sha = enable_avatar_rotation(
                path,
                expected_approved_sha256=approved_sha,
                confirmation_reference="user-confirmed-avatar-rotation:moods-v1",
            )
            catalog = load_avatar_catalog(path, expected_sha256=enabled_sha)
            now = datetime(2026, 8, 2, 12, tzinfo=UTC)
            with database.transaction() as connection:
                for index, hours in enumerate((3, 2, 0)):
                    connection.execute(
                        """
                        INSERT INTO persona_mood_observations (
                            bot_user_id, trigger_event_id, persona_version,
                            persona_digest, mood_code, bot_scope_count, created_at
                        ) VALUES ('bot-1', ?, 'lezhi-v2.0', ?, 'joyful', 1, ?)
                        """,
                        (
                            f"event-{index}",
                            catalog.persona_digest,
                            (now - timedelta(hours=hours)).isoformat(),
                        ),
                    )
            controller = AvatarController(
                database=database,
                telegram=_Telegram(),  # type: ignore[arg-type]
                multipart=_Multipart(),  # type: ignore[arg-type]
                bot_user_id="bot-1",
                state_directory=path.parent / "state",
            )
            candidate = controller.stable_mood_candidate(catalog, now=now)
            self.assertEqual("lezhi-joyful", candidate.avatar_id if candidate else None)

            with database.transaction() as connection:
                connection.execute(
                    "UPDATE persona_mood_observations SET bot_scope_count = 2 WHERE bot_user_id = 'bot-1'"
                )
            self.assertIsNone(controller.stable_mood_candidate(catalog, now=now))

    def test_apply_verifies_readback_and_failure_rolls_back_none(self) -> None:
        with _avatar_fixture() as path, temporary_database() as database:
            approved_sha = approve_avatar_catalog(
                path,
                expected_candidate_sha256=file_sha256(path),
                approval_reference="user-confirmed-avatar:preview-1",
                approved_avatar_ids=frozenset({"lezhi-default"}),
            )
            catalog = load_avatar_catalog(path, expected_sha256=approved_sha)
            telegram = _Telegram()
            controller = AvatarController(
                database=database,
                telegram=telegram,  # type: ignore[arg-type]
                multipart=_Multipart(),  # type: ignore[arg-type]
                bot_user_id="bot-1",
                state_directory=path.parent / "state",
            )
            self.assertEqual(
                "new-unique",
                controller.apply(
                    catalog,
                    avatar_id="lezhi-default",
                    requested_by="operator",
                    reason_code="initial_default",
                ),
            )

            failing_telegram = _Telegram()
            failing = AvatarController(
                database=database,
                telegram=failing_telegram,  # type: ignore[arg-type]
                multipart=_Multipart(fail=True),  # type: ignore[arg-type]
                bot_user_id="bot-2",
                state_directory=path.parent / "state",
            )
            with self.assertRaises(TelegramApiError):
                failing.apply(
                    catalog,
                    avatar_id="lezhi-default",
                    requested_by="operator",
                    reason_code="initial_default",
                )
            self.assertEqual(1, failing_telegram.removed)
            connection = database.connect()
            try:
                audit = connection.execute(
                    "SELECT platform_status, rollback_status FROM avatar_change_audit "
                    "WHERE bot_user_id = 'bot-2'"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(("failed", "succeeded"), tuple(audit))


if __name__ == "__main__":
    unittest.main()
