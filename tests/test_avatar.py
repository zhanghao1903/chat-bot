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
        bot_id: str = "bot-1",
        error: TelegramApiError | None = None,
    ) -> None:
        self.bot_id = bot_id
        self.error = error
        self.identity_reads = 0

    def get_me(self) -> dict[str, object]:
        self.identity_reads += 1
        if self.error is not None:
            raise self.error
        return {"id": self.bot_id, "is_bot": True, "username": "lezhi"}


class _Multipart:
    def __init__(self, *, error: TelegramApiError | None = None) -> None:
        self.error = error
        self.uploads = 0

    def set_static_profile_photo(self, *, jpeg: bytes) -> None:
        self.uploads += 1
        if self.error is not None:
            raise self.error
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

    def test_v031_apply_allows_only_exact_default_even_after_baseline(self) -> None:
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
                approved_catalog_digest=catalog.digest,
            )
            with self.assertRaisesRegex(ExpressionCatalogError, "only_default_avatar_authorized"):
                blocked.apply(
                    catalog,
                    avatar_id="lezhi-joyful",
                    requested_by="operator",
                    reason_code="manual_mood",
                    authorization_reference="user-confirmed-avatar-apply:test",
                )
            self.assertEqual(0, blocked_transport.uploads)

            default_controller = AvatarController(
                database=database,
                telegram=_Telegram(),  # type: ignore[arg-type]
                multipart=_Multipart(),  # type: ignore[arg-type]
                bot_user_id="bot-1",
                state_directory=path.parent / "state",
                approved_catalog_digest=catalog.digest,
            )
            self.assertEqual(
                "success",
                default_controller.apply(
                    catalog,
                    avatar_id="lezhi-default",
                    requested_by="operator",
                    reason_code="initial_default",
                    authorization_reference="user-confirmed-avatar-apply:test",
                ).status,
            )

            mood_controller = AvatarController(
                database=database,
                telegram=_Telegram(),  # type: ignore[arg-type]
                multipart=_Multipart(),  # type: ignore[arg-type]
                bot_user_id="bot-1",
                state_directory=path.parent / "state",
                approved_catalog_digest=catalog.digest,
            )
            with self.assertRaisesRegex(ExpressionCatalogError, "only_default_avatar_authorized"):
                mood_controller.apply(
                    catalog,
                    avatar_id="lezhi-joyful",
                    requested_by="rotation",
                    reason_code="stable_global_mood",
                    authorization_reference="user-confirmed-avatar-apply:test",
                )

    def test_apply_uses_one_write_and_records_api_success_without_readback(self) -> None:
        with _avatar_fixture() as path, temporary_database() as database:
            approved_sha = approve_avatar_catalog(
                path,
                expected_candidate_sha256=file_sha256(path),
                approval_reference="user-confirmed-avatar:preview-1",
                approved_avatar_ids=frozenset({"lezhi-default"}),
            )
            catalog = load_avatar_catalog(path, expected_sha256=approved_sha)
            telegram = _Telegram()
            multipart = _Multipart()
            controller = AvatarController(
                database=database,
                telegram=telegram,  # type: ignore[arg-type]
                multipart=multipart,  # type: ignore[arg-type]
                bot_user_id="bot-1",
                state_directory=path.parent / "state",
                approved_catalog_digest=catalog.digest,
            )
            result = controller.apply(
                catalog,
                avatar_id="lezhi-default",
                requested_by="operator",
                reason_code="initial_default",
                authorization_reference="user-confirmed-avatar-apply:req-034",
            )
            self.assertEqual("success", result.status)
            self.assertTrue(result.operation_id.startswith("avatar-"))
            self.assertEqual((1, 1), (telegram.identity_reads, multipart.uploads))
            connection = database.connect()
            try:
                audit = connection.execute(
                    "SELECT operation_id, api_method, authorization_reference, "
                    "platform_status, error_code, rollback_status "
                    "FROM avatar_change_audit WHERE bot_user_id = 'bot-1'"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(
                (
                    result.operation_id,
                    "setMyProfilePhoto",
                    "user-confirmed-avatar-apply:req-034",
                    "success",
                    None,
                    None,
                ),
                tuple(audit),
            )

    def test_apply_classifies_explicit_failure_and_uncertain_without_retry(self) -> None:
        with _avatar_fixture() as path, temporary_database() as database:
            approved_sha = approve_avatar_catalog(
                path,
                expected_candidate_sha256=file_sha256(path),
                approval_reference="user-confirmed-avatar:preview-1",
                approved_avatar_ids=frozenset({"lezhi-default"}),
            )
            catalog = load_avatar_catalog(path, expected_sha256=approved_sha)
            cases = (
                ("bot-failed", TelegramApiError("setMyProfilePhoto", "api_error", 400), "failed"),
                ("bot-timeout", TelegramApiError("setMyProfilePhoto", "timeout"), "uncertain"),
                (
                    "bot-transport",
                    TelegramApiError("setMyProfilePhoto", "transport_error"),
                    "uncertain",
                ),
                (
                    "bot-json",
                    TelegramApiError("setMyProfilePhoto", "invalid_json"),
                    "uncertain",
                ),
                (
                    "bot-response",
                    TelegramApiError("setMyProfilePhoto", "invalid_response"),
                    "uncertain",
                ),
                (
                    "bot-result",
                    TelegramApiError("setMyProfilePhoto", "invalid_result"),
                    "uncertain",
                ),
                (
                    "bot-http-5xx",
                    TelegramApiError("setMyProfilePhoto", "http_error", 503),
                    "uncertain",
                ),
                (
                    "bot-api-5xx",
                    TelegramApiError("setMyProfilePhoto", "api_error", 500),
                    "uncertain",
                ),
            )
            for bot_id, error, expected_status in cases:
                with self.subTest(expected_status=expected_status):
                    multipart = _Multipart(error=error)
                    controller = AvatarController(
                        database=database,
                        telegram=_Telegram(bot_id=bot_id),  # type: ignore[arg-type]
                        multipart=multipart,  # type: ignore[arg-type]
                        bot_user_id=bot_id,
                        state_directory=path.parent / "state",
                        approved_catalog_digest=catalog.digest,
                    )
                    with self.assertRaises(TelegramApiError):
                        controller.apply(
                            catalog,
                            avatar_id="lezhi-default",
                            requested_by="operator",
                            reason_code="initial_default",
                            authorization_reference="user-confirmed-avatar-apply:test",
                        )
                    self.assertEqual(1, multipart.uploads)

            connection = database.connect()
            try:
                audits = connection.execute(
                    "SELECT bot_user_id, platform_status, error_code, rollback_status "
                    "FROM avatar_change_audit ORDER BY id"
                ).fetchall()
            finally:
                connection.close()
            expected = [
                (
                    bot_id,
                    expected_status,
                    f"setMyProfilePhoto_{error.category}"
                    + (f"_{error.status_code}" if error.status_code is not None else ""),
                    None,
                )
                for bot_id, error, expected_status in cases
            ]
            self.assertEqual(expected, [tuple(item) for item in audits])

    def test_digest_authorization_and_identity_mismatch_stop_before_write(self) -> None:
        with _avatar_fixture() as path, temporary_database() as database:
            approved_sha = approve_avatar_catalog(
                path,
                expected_candidate_sha256=file_sha256(path),
                approval_reference="user-confirmed-avatar:preview-1",
                approved_avatar_ids=frozenset({"lezhi-default"}),
            )
            catalog = load_avatar_catalog(path, expected_sha256=approved_sha)
            multipart = _Multipart()
            wrong_digest = AvatarController(
                database=database,
                telegram=_Telegram(),  # type: ignore[arg-type]
                multipart=multipart,  # type: ignore[arg-type]
                bot_user_id="bot-1",
            )
            with self.assertRaisesRegex(ExpressionCatalogError, "avatar_catalog_digest_mismatch"):
                wrong_digest.apply(
                    catalog,
                    avatar_id="lezhi-default",
                    requested_by="operator",
                    reason_code="initial_default",
                    authorization_reference="user-confirmed-avatar-apply:test",
                )
            self.assertEqual(0, multipart.uploads)

            with self.assertRaisesRegex(
                ExpressionCatalogError, "explicit_avatar_apply_authorization_required"
            ):
                AvatarController(
                    database=database,
                    telegram=_Telegram(),  # type: ignore[arg-type]
                    multipart=multipart,  # type: ignore[arg-type]
                    bot_user_id="bot-1",
                    approved_catalog_digest=catalog.digest,
                ).apply(
                    catalog,
                    avatar_id="lezhi-default",
                    requested_by="operator",
                    reason_code="initial_default",
                    authorization_reference="automatic",
                )
            self.assertEqual(0, multipart.uploads)

            wrong_identity = AvatarController(
                database=database,
                telegram=_Telegram(bot_id="other-bot"),  # type: ignore[arg-type]
                multipart=multipart,  # type: ignore[arg-type]
                bot_user_id="bot-1",
                approved_catalog_digest=catalog.digest,
            )
            with self.assertRaisesRegex(TelegramApiError, "invalid_identity"):
                wrong_identity.apply(
                    catalog,
                    avatar_id="lezhi-default",
                    requested_by="operator",
                    reason_code="initial_default",
                    authorization_reference="user-confirmed-avatar-apply:test",
                )
            self.assertEqual(0, multipart.uploads)

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
