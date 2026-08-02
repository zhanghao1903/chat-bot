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
    TelegramFile,
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
            for relative in (candidate["image_path"], candidate["circle_preview_path"]):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                os.link(_SOURCE_ROOT / relative, target)
        yield path


class _Telegram:
    def __init__(
        self,
        *,
        profiles: list[TelegramProfilePhoto | None] | None = None,
        downloads: dict[str, bytes] | None = None,
    ) -> None:
        self.profile_reads = 0
        self.removed = 0
        self.profiles = profiles or [None]
        self.downloads = downloads or {}

    def get_user_profile_photo(self, *, user_id: str) -> TelegramProfilePhoto | None:
        self.profile_reads += 1
        index = min(self.profile_reads - 1, len(self.profiles) - 1)
        return self.profiles[index]

    def get_file(self, *, file_id: str) -> TelegramFile:
        return TelegramFile(file_path=f"profiles/{file_id}.jpg", file_size=None)

    def download_file(
        self,
        *,
        file_path: str,
        maximum_bytes: int,
        timeout_seconds: int | None = None,
    ) -> bytes:
        content = self.downloads[file_path]
        if len(content) > maximum_bytes:
            raise AssertionError("test download exceeds bound")
        return content

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

    def test_stable_global_mood_requires_baseline_cross_chat_and_member_scope(self) -> None:
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
                for index, (hours, chat_id, member_user_id) in enumerate(
                    (
                        (3, "group-a", "member-a"),
                        (2, "group-b", "member-b"),
                        (0, "group-a", "member-b"),
                    )
                ):
                    connection.execute(
                        """
                        INSERT INTO persona_mood_observations (
                            bot_user_id, chat_id, member_user_id, trigger_event_id,
                            persona_version, persona_digest, mood_code,
                            bot_scope_count, created_at
                        ) VALUES ('bot-1', ?, ?, ?, 'lezhi-v2.0', ?, 'joyful', 2, ?)
                        """,
                        (
                            chat_id,
                            member_user_id,
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

            self.assertIsNone(controller.stable_mood_candidate(catalog, now=now))
            self._record_verified_default(database, catalog, now=now)
            candidate = controller.stable_mood_candidate(catalog, now=now)
            self.assertEqual("lezhi-joyful", candidate.avatar_id if candidate else None)

            with database.transaction() as connection:
                connection.execute(
                    "UPDATE persona_mood_observations SET member_user_id = 'member-a'"
                )
            self.assertIsNone(controller.stable_mood_candidate(catalog, now=now))

            with database.transaction() as connection:
                connection.execute(
                    "UPDATE persona_mood_observations "
                    "SET member_user_id = CASE WHEN trigger_event_id = 'event-0' "
                    "THEN 'member-a' ELSE 'member-b' END, chat_id = 'group-a'"
                )
            self.assertIsNone(controller.stable_mood_candidate(catalog, now=now))

            with database.transaction() as connection:
                connection.execute(
                    "UPDATE persona_mood_observations "
                    "SET chat_id = CASE WHEN trigger_event_id = 'event-1' "
                    "THEN 'group-b' ELSE 'group-a' END, bot_scope_count = 1"
                )
            self.assertIsNone(controller.stable_mood_candidate(catalog, now=now))

    def test_first_managed_avatar_must_be_exact_default_baseline(self) -> None:
        with _avatar_fixture() as path, temporary_database() as database:
            approved_sha = approve_avatar_catalog(
                path,
                expected_candidate_sha256=file_sha256(path),
                approval_reference="user-confirmed-avatar:preview-1",
                approved_avatar_ids=frozenset({"lezhi-default", "lezhi-joyful"}),
                approved_sticker_catalog_sha256="a" * 64,
            )
            catalog = load_avatar_catalog(path, expected_sha256=approved_sha)
            default = catalog.candidate("lezhi-default")
            joyful = catalog.candidate("lezhi-joyful")
            assert default is not None and joyful is not None

            blocked_transport = _Multipart()
            blocked = AvatarController(
                database=database,
                telegram=_Telegram(),  # type: ignore[arg-type]
                multipart=blocked_transport,  # type: ignore[arg-type]
                bot_user_id="bot-1",
                state_directory=path.parent / "state",
            )
            with self.assertRaisesRegex(ExpressionCatalogError, "default_avatar_baseline_required"):
                blocked.apply(
                    catalog,
                    avatar_id="lezhi-joyful",
                    requested_by="operator",
                    reason_code="manual_mood",
                )
            self.assertEqual(0, blocked_transport.uploads)

            default_profile = TelegramProfilePhoto("default-file", "default-unique", 512, 512)
            default_bytes = (path.parent / default.image_path).read_bytes()
            default_controller = AvatarController(
                database=database,
                telegram=_Telegram(
                    profiles=[None, default_profile],
                    downloads={"profiles/default-file.jpg": default_bytes},
                ),  # type: ignore[arg-type]
                multipart=_Multipart(),  # type: ignore[arg-type]
                bot_user_id="bot-1",
                state_directory=path.parent / "state",
            )
            self.assertEqual(
                "default-unique",
                default_controller.apply(
                    catalog,
                    avatar_id="lezhi-default",
                    requested_by="operator",
                    reason_code="initial_default",
                ),
            )

            joyful_profile = TelegramProfilePhoto("joyful-file", "joyful-unique", 512, 512)
            joyful_bytes = (path.parent / joyful.image_path).read_bytes()
            mood_controller = AvatarController(
                database=database,
                telegram=_Telegram(
                    profiles=[default_profile, joyful_profile],
                    downloads={
                        "profiles/default-file.jpg": default_bytes,
                        "profiles/joyful-file.jpg": joyful_bytes,
                    },
                ),  # type: ignore[arg-type]
                multipart=_Multipart(),  # type: ignore[arg-type]
                bot_user_id="bot-1",
                state_directory=path.parent / "state",
            )
            self.assertEqual(
                "joyful-unique",
                mood_controller.apply(
                    catalog,
                    avatar_id="lezhi-joyful",
                    requested_by="rotation",
                    reason_code="stable_global_mood",
                ),
            )

    def test_apply_verifies_readback_and_failure_rolls_back_none(self) -> None:
        with _avatar_fixture() as path, temporary_database() as database:
            approved_sha = approve_avatar_catalog(
                path,
                expected_candidate_sha256=file_sha256(path),
                approval_reference="user-confirmed-avatar:preview-1",
                approved_avatar_ids=frozenset({"lezhi-default"}),
            )
            catalog = load_avatar_catalog(path, expected_sha256=approved_sha)
            candidate = catalog.candidate("lezhi-default")
            assert candidate is not None
            candidate_bytes = (path.parent / candidate.image_path).read_bytes()
            profile = TelegramProfilePhoto("new-file", "new-unique", 512, 512)
            telegram = _Telegram(
                profiles=[None, profile],
                downloads={"profiles/new-file.jpg": candidate_bytes},
            )
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

            failing_telegram = _Telegram(profiles=[None])
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

    def test_unchanged_or_wrong_readback_never_records_verified(self) -> None:
        with _avatar_fixture() as path, temporary_database() as database:
            approved_sha = approve_avatar_catalog(
                path,
                expected_candidate_sha256=file_sha256(path),
                approval_reference="user-confirmed-avatar:preview-1",
                approved_avatar_ids=frozenset({"lezhi-default"}),
            )
            catalog = load_avatar_catalog(path, expected_sha256=approved_sha)
            old = TelegramProfilePhoto("old-file", "old-unique", 512, 512)
            telegram = _Telegram(
                profiles=[old, old],
                downloads={"profiles/old-file.jpg": b"unchanged-old-avatar"},
            )
            multipart = _Multipart()
            controller = AvatarController(
                database=database,
                telegram=telegram,  # type: ignore[arg-type]
                multipart=multipart,  # type: ignore[arg-type]
                bot_user_id="bot-1",
                state_directory=path.parent / "state",
            )

            with self.assertRaisesRegex(TelegramApiError, "verification_mismatch"):
                controller.apply(
                    catalog,
                    avatar_id="lezhi-default",
                    requested_by="operator",
                    reason_code="initial_default",
                )

            connection = database.connect()
            try:
                audit = connection.execute(
                    "SELECT platform_status, error_code, rollback_status "
                    "FROM avatar_change_audit WHERE bot_user_id = 'bot-1'"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(("failed", "verification_mismatch", "succeeded"), tuple(audit))
            self.assertEqual(2, multipart.uploads)

            wrong = TelegramProfilePhoto("wrong-file", "wrong-unique", 512, 512)
            wrong_telegram = _Telegram(
                profiles=[None, wrong],
                downloads={"profiles/wrong-file.jpg": b"different-avatar-content"},
            )
            wrong_controller = AvatarController(
                database=database,
                telegram=wrong_telegram,  # type: ignore[arg-type]
                multipart=_Multipart(),  # type: ignore[arg-type]
                bot_user_id="bot-2",
                state_directory=path.parent / "state",
            )
            with self.assertRaisesRegex(TelegramApiError, "verification_mismatch"):
                wrong_controller.apply(
                    catalog,
                    avatar_id="lezhi-default",
                    requested_by="operator",
                    reason_code="initial_default",
                )
            connection = database.connect()
            try:
                wrong_audit = connection.execute(
                    "SELECT platform_status, error_code, rollback_status "
                    "FROM avatar_change_audit WHERE bot_user_id = 'bot-2'"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(("failed", "verification_mismatch", "succeeded"), tuple(wrong_audit))
            self.assertEqual(1, wrong_telegram.removed)

    @staticmethod
    def _record_verified_default(database, catalog, *, now: datetime) -> None:
        previous = now - timedelta(days=4)
        with database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO avatar_change_audit (
                    bot_user_id, avatar_catalog_version, avatar_catalog_digest,
                    requested_avatar_id, requested_image_sha256, reason_code,
                    cooldown_status, requested_by,
                    platform_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'initial_default', 'eligible', 'operator',
                          'verified', ?, ?)
                """,
                (
                    "bot-1",
                    catalog.catalog_version,
                    catalog.digest,
                    catalog.default_avatar_id,
                    catalog.candidate(catalog.default_avatar_id).image_sha256,
                    previous.isoformat(),
                    previous.isoformat(),
                ),
            )


if __name__ == "__main__":
    unittest.main()
