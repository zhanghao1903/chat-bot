from __future__ import annotations

import unittest
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from helpers import ScriptedModelClient, temporary_database

from group_llm_agent.database import SQLiteDatabase
from group_llm_agent.events import (
    ModelErrorCode,
    PersonaSnapshot,
    TelegramTextMessage,
)
from group_llm_agent.memory import MemoryRepository
from group_llm_agent.messages import MessageRepository
from group_llm_agent.model import (
    ModelApiError,
    ModelRole,
    RecognitionProposal,
    StructuredModelResult,
)
from group_llm_agent.persona import CharacterBundle, load_character_bundle
from group_llm_agent.recognition import RecognitionWorker
from group_llm_agent.recognition_jobs import (
    RecognitionConflict,
    RecognitionEnvelope,
    RecognitionJobRepository,
)

_BASE_TIME = datetime(2026, 7, 29, 3, tzinfo=UTC)


class RecognitionWorkerTests(unittest.TestCase):
    def test_one_call_applies_neutral_fact_and_persona_bound_impression(self) -> None:
        bundle = _bundle()
        with temporary_database() as database:
            messages = MessageRepository(database)
            _enable(messages, bundle, chat_id="group-a")
            _ingest(messages, bundle, chat_id="group-a", message_id="1")
            model = ScriptedModelClient(
                _proposals(
                    _proposal(
                        operation="add",
                        category="fact",
                        statement="The member publicly said they enjoy puzzle games.",
                    ),
                    _proposal(
                        operation="add",
                        category="impression",
                        statement="The member currently welcomes playful follow-up questions.",
                        confidence=0.72,
                    ),
                )
            )

            processed = RecognitionWorker(
                database=database,
                model=model,
                messages=messages,
            ).run_once(bundle=bundle, now=_BASE_TIME)

            self.assertTrue(processed)
            self.assertEqual(1, len(model.calls))
            self.assertEqual(ModelRole.RECOGNITION, model.calls[0]["model_role"])
            system = model.calls[0]["messages"][0].content
            self.assertIn("relationship_stance", system)
            self.assertIn("No tools or external actions", system)
            connection = database.connect()
            try:
                rows = connection.execute(
                    """
                    SELECT category, persona_version, persona_digest
                    FROM member_memory_items ORDER BY category
                    """
                ).fetchall()
                job = connection.execute(
                    "SELECT status, attempt_count FROM recognition_jobs"
                ).fetchone()
                audits = connection.execute(
                    "SELECT count(*) FROM recognition_change_audit"
                ).fetchone()[0]
            finally:
                connection.close()
            by_category = {str(row["category"]): row for row in rows}
            self.assertIsNone(by_category["fact"]["persona_version"])
            self.assertEqual(
                bundle.snapshot.persona_version,
                by_category["impression"]["persona_version"],
            )
            self.assertEqual(
                bundle.snapshot.persona_digest,
                by_category["impression"]["persona_digest"],
            )
            self.assertEqual(("completed", 1), (job["status"], job["attempt_count"]))
            self.assertEqual(2, audits)

    def test_invalid_subject_source_and_sensitive_inference_are_rejected(self) -> None:
        bundle = _bundle()
        with temporary_database() as database:
            messages = MessageRepository(database)
            for chat_id in ("group-a", "group-b"):
                _enable(messages, bundle, chat_id=chat_id)
            _ingest(messages, bundle, chat_id="group-a", message_id="1")
            _ingest(messages, bundle, chat_id="group-b", message_id="99")
            model = ScriptedModelClient(
                _proposals(
                    _proposal(
                        operation="add",
                        category="fact",
                        statement="The member has a specific political affiliation.",
                    ),
                    _proposal(
                        operation="add",
                        category="observation",
                        statement="Unsupported other-group observation.",
                        source_message_ids=["99"],
                    ),
                    _proposal(
                        operation="add",
                        category="observation",
                        statement="Wrong subject observation.",
                        subject_user_id="member-b",
                    ),
                    _proposal(
                        operation="add",
                        category="observation",
                        statement="The member asked a public follow-up question.",
                    ),
                )
            )

            RecognitionWorker(
                database=database,
                model=model,
                messages=messages,
            ).run_once(bundle=bundle, now=_BASE_TIME)

            connection = database.connect()
            try:
                statements = [
                    str(row["statement"])
                    for row in connection.execute(
                        "SELECT statement FROM member_memory_items"
                    ).fetchall()
                ]
                job_status = connection.execute(
                    """
                    SELECT status FROM recognition_jobs
                    WHERE chat_id = 'group-a' ORDER BY id LIMIT 1
                    """
                ).fetchone()["status"]
            finally:
                connection.close()
            self.assertEqual(
                ["The member asked a public follow-up question."],
                statements,
            )
            self.assertEqual("completed", job_status)

    def test_provider_failure_retries_with_backoff_then_becomes_dead(self) -> None:
        bundle = _bundle()
        with temporary_database() as database:
            messages = MessageRepository(database)
            _enable(messages, bundle, chat_id="group-a")
            _ingest(messages, bundle, chat_id="group-a", message_id="1")
            model = ScriptedModelClient(
                ModelApiError(ModelRole.RECOGNITION, ModelErrorCode.TIMEOUT),
                ModelApiError(ModelRole.RECOGNITION, ModelErrorCode.RATE_LIMITED),
                ModelApiError(ModelRole.RECOGNITION, ModelErrorCode.PROVIDER_ERROR),
            )
            worker = RecognitionWorker(
                database=database,
                model=model,
                messages=messages,
            )

            worker.run_once(bundle=bundle, now=_BASE_TIME)
            worker.run_once(bundle=bundle, now=_BASE_TIME + timedelta(seconds=3))
            worker.run_once(bundle=bundle, now=_BASE_TIME + timedelta(seconds=8))

            connection = database.connect()
            try:
                job = connection.execute(
                    """
                    SELECT status, attempt_count, next_attempt_at, error_code
                    FROM recognition_jobs
                    """
                ).fetchone()
                memory_count = connection.execute(
                    "SELECT count(*) FROM member_memory_items"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(3, len(model.calls))
            self.assertEqual("dead", job["status"])
            self.assertEqual(3, job["attempt_count"])
            self.assertIsNone(job["next_attempt_at"])
            self.assertEqual("provider_error", job["error_code"])
            self.assertEqual(0, memory_count)

    def test_reset_racing_leased_job_prevents_stale_commit(self) -> None:
        bundle = _bundle()
        with temporary_database() as database:
            messages = MessageRepository(database)
            _enable(messages, bundle, chat_id="group-a")
            _ingest(messages, bundle, chat_id="group-a", message_id="1")
            memory = MemoryRepository(database)
            model = ResetDuringRecognitionModel(memory)

            RecognitionWorker(
                database=database,
                model=model,
                messages=messages,
            ).run_once(bundle=bundle, now=_BASE_TIME)

            connection = database.connect()
            try:
                job_status = connection.execute("SELECT status FROM recognition_jobs").fetchone()[
                    "status"
                ]
                memory_count = connection.execute(
                    "SELECT count(*) FROM member_memory_items"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(1, model.call_count)
            self.assertEqual("superseded", job_status)
            self.assertEqual(0, memory_count)

    def test_expired_lease_is_recovered_and_processed(self) -> None:
        bundle = _bundle()
        with temporary_database() as database:
            messages = MessageRepository(database)
            _enable(messages, bundle, chat_id="group-a")
            _ingest(messages, bundle, chat_id="group-a", message_id="1")
            with database.transaction() as connection:
                connection.execute(
                    """
                    UPDATE recognition_jobs
                    SET status = 'leased', lease_token = 'abandoned',
                        leased_until = ?, attempt_count = 0
                    """,
                    ((_BASE_TIME - timedelta(seconds=1)).isoformat(),),
                )
            model = ScriptedModelClient(_proposals())

            RecognitionWorker(
                database=database,
                model=model,
                messages=messages,
            ).run_once(bundle=bundle, now=_BASE_TIME)

            connection = database.connect()
            try:
                row = connection.execute(
                    """
                    SELECT status, attempt_count, lease_token
                    FROM recognition_jobs
                    """
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(("completed", 1, None), tuple(row))
            self.assertEqual(1, len(model.calls))

    def test_old_persona_job_is_superseded_without_model_call(self) -> None:
        bundle = _bundle()
        new_snapshot = PersonaSnapshot(
            bundle.snapshot.persona_id,
            "v2",
            "2" * 64,
        )
        new_bundle = replace(bundle, snapshot=new_snapshot)
        with temporary_database() as database:
            messages = MessageRepository(database)
            _enable(messages, bundle, chat_id="group-a")
            _ingest(messages, bundle, chat_id="group-a", message_id="1")
            messages.policies.set_memory_status(
                chat_id="group-a",
                status="enabled",
                persona=new_snapshot,
                notice_message_id="notice-v2",
                enabled_by_user_id="admin",
            )
            model = ScriptedModelClient()

            processed = RecognitionWorker(
                database=database,
                model=model,
                messages=messages,
            ).run_once(bundle=new_bundle, now=_BASE_TIME)

            connection = database.connect()
            try:
                status = connection.execute("SELECT status FROM recognition_jobs").fetchone()[
                    "status"
                ]
            finally:
                connection.close()
            self.assertFalse(processed)
            self.assertEqual("superseded", status)
            self.assertEqual(0, len(model.calls))

    def test_database_conflict_reloads_once_without_second_model_call(self) -> None:
        bundle = _bundle()
        with temporary_database() as database:
            messages = MessageRepository(database)
            _enable(messages, bundle, chat_id="group-a")
            _ingest(messages, bundle, chat_id="group-a", message_id="1")
            model = ScriptedModelClient(
                _proposals(
                    _proposal(
                        operation="add",
                        category="observation",
                        statement="The member asked a concrete question.",
                    )
                )
            )
            jobs = ConflictOnceRepository(database)

            RecognitionWorker(
                database=database,
                model=model,
                messages=messages,
                jobs=jobs,
            ).run_once(bundle=bundle, now=_BASE_TIME)

            connection = database.connect()
            try:
                status = connection.execute("SELECT status FROM recognition_jobs").fetchone()[
                    "status"
                ]
                memory_count = connection.execute(
                    "SELECT count(*) FROM member_memory_items"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(2, jobs.apply_count)
            self.assertEqual(1, len(model.calls))
            self.assertEqual("completed", status)
            self.assertEqual(1, memory_count)


class ResetDuringRecognitionModel:
    def __init__(self, memory: MemoryRepository) -> None:
        self.memory = memory
        self.call_count = 0

    def complete(self, **_: object) -> StructuredModelResult:
        self.call_count += 1
        self.memory.reset_member(
            chat_id="group-a",
            member_user_id="member-a",
            reset_by_user_id="member-a",
            at=_BASE_TIME,
        )
        return _proposals(
            _proposal(
                operation="add",
                category="fact",
                statement="This stale proposal must not be committed.",
            )
        )


class ConflictOnceRepository(RecognitionJobRepository):
    def __init__(self, database: SQLiteDatabase) -> None:
        super().__init__(database)
        self.apply_count = 0

    def apply(
        self,
        *,
        envelope: RecognitionEnvelope,
        proposals: Sequence[RecognitionProposal],
        now: datetime,
    ) -> int:
        self.apply_count += 1
        if self.apply_count == 1:
            raise RecognitionConflict("simulated")
        return super().apply(envelope=envelope, proposals=proposals, now=now)


def _bundle() -> CharacterBundle:
    return load_character_bundle(Path(__file__).parent / "fixtures/personas/test-original/v1")


def _enable(
    messages: MessageRepository,
    bundle: CharacterBundle,
    *,
    chat_id: str,
) -> None:
    messages.policies.set_memory_status(
        chat_id=chat_id,
        status="enabled",
        persona=bundle.snapshot,
        notice_message_id=f"notice-{chat_id}",
        enabled_by_user_id="admin",
    )


def _ingest(
    messages: MessageRepository,
    bundle: CharacterBundle,
    *,
    chat_id: str,
    message_id: str,
) -> None:
    result = messages.ingest_inbound(
        TelegramTextMessage(
            event_id=f"event-{chat_id}-{message_id}",
            group_id=chat_id,
            message_id=message_id,
            sender_id="member-a",
            sender_display_name="Member A",
            text=f"public source {message_id}",
            timestamp=_BASE_TIME,
        ),
        persona=bundle.snapshot,
        recognition_policy_version="policy-v1",
    )
    assert result.recognition_job_id is not None


def _proposals(*items: dict[str, object]) -> StructuredModelResult:
    return StructuredModelResult({"proposals": list(items)})


def _proposal(
    *,
    operation: str,
    category: str,
    statement: str,
    confidence: float = 0.7,
    source_message_ids: list[str] | None = None,
    subject_user_id: str = "member-a",
    supersedes_memory_id: str | None = None,
) -> dict[str, object]:
    return {
        "subject_user_id": subject_user_id,
        "operation": operation,
        "category": category,
        "statement": statement,
        "confidence": confidence,
        "source_message_ids": source_message_ids or ["1"],
        "supersedes_memory_id": supersedes_memory_id,
    }


if __name__ == "__main__":
    unittest.main()
