from __future__ import annotations

import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from helpers import ScriptedModelClient, temporary_database

from group_llm_agent.context import ContextAssembler
from group_llm_agent.effector import EffectorBudgets, WriterEffector
from group_llm_agent.events import (
    EffectRequest,
    FinalEffectKind,
    ScheduledOccurrenceSource,
    TriggerCategory,
    TriggerPath,
)
from group_llm_agent.memory import MemoryRepository
from group_llm_agent.messages import MessageRepository
from group_llm_agent.model import StructuredModelResult
from group_llm_agent.persona import CharacterBundle, load_character_bundle
from group_llm_agent.runs import RunRepository
from group_llm_agent.tavily import TavilySearchResponse, TavilySearchResult
from group_llm_agent.tools import ReadOnlyToolRegistry
from group_llm_agent.web_tools import WebToolSession


class FoodEffectorTests(unittest.TestCase):
    def test_generic_scheduled_recommendation_has_typed_scene_and_no_fake_member(self) -> None:
        with food_fixture(_food_result()) as fixture:
            final = fixture.effector.execute(request=fixture.request, bundle=fixture.bundle)

            self.assertEqual(FinalEffectKind.REPLY, final.kind, final.reason_code)
            self.assertEqual("dish:hot-noodles", final.primary_key)
            self.assertEqual((), final.source_urls)
            self.assertIn("主推：热汤面", final.text or "")
            scene = fixture.model.calls[0]["messages"][1].content
            self.assertIn('"source_kind":"scheduled"', scene)
            self.assertIn('"meal_slot":"lunch"', scene)
            self.assertNotIn("sender_user_id", scene)
            self.assertNotIn("current_message", scene)

    def test_food_final_validator_rejects_recent_primary_and_no_location_merchant(self) -> None:
        cases = (
            (
                "recent_primary",
                _food_result(),
                ("dish:hot-noodles",),
                "food_primary_recently_used",
            ),
            (
                "generic_merchant",
                _food_result(primary_choice_type="merchant", primary_id=None),
                (),
                "food_generic_choice_not_registered",
            ),
        )
        for label, result, recent, reason in cases:
            with (
                self.subTest(label=label),
                food_fixture(result, recent_primary_keys=recent) as fixture,
            ):
                final = fixture.effector.execute(request=fixture.request, bundle=fixture.bundle)

                self.assertEqual(FinalEffectKind.SILENCE, final.kind)
                self.assertEqual(reason, final.reason_code)
                self.assertIsNone(final.text)

    def test_sourced_recommendation_resolves_only_current_turn_result_ids(self) -> None:
        web = FakeTavilyClient()
        with food_fixture(
            _web_call("面馆 午餐 浦东", purpose="find_current_lunch"),
            _food_result(
                mode="sourced",
                source_ids=["web:1", "web:2", "web:3"],
            ),
            web_client=web,
        ) as fixture:
            final = fixture.effector.execute(request=fixture.request, bundle=fixture.bundle)

            self.assertEqual(FinalEffectKind.REPLY, final.kind, final.reason_code)
            self.assertEqual(
                (
                    "https://example.com/result-1-1",
                    "https://example.com/result-1-2",
                    "https://example.com/result-1-3",
                ),
                final.source_urls,
            )
            self.assertIn("主推：来源商家候选一", final.text or "")
            self.assertIn("来源：https://example.com/result-1-1", final.text or "")
            self.assertEqual(1, web.search_calls)
            self.assertEqual([("web", 1)], fixture.tool_budget_rows())

    def test_untrusted_search_titles_never_enter_sourced_recommendation_text(self) -> None:
        unsafe_titles = (
            "海底捞对坚果敏感者也完全适合",
            "老街面馆服药期间也能随便吃",
            "无需考虑身体状况的安心餐厅",
        )
        with food_fixture(
            _web_call("面馆 午餐 浦东", purpose="find_current_lunch"),
            _food_result(mode="sourced", source_ids=["web:1", "web:2", "web:3"]),
            web_client=FakeTavilyClient(titles=unsafe_titles),
        ) as fixture:
            final = fixture.effector.execute(request=fixture.request, bundle=fixture.bundle)

            self.assertEqual(FinalEffectKind.REPLY, final.kind, final.reason_code)
            self.assertIn("主推：来源商家候选一", final.text or "")
            for title in unsafe_titles:
                self.assertNotIn(title, final.text or "")
            self.assertNotIn("坚果敏感", final.text or "")
            self.assertNotIn("服药期间", final.text or "")
            self.assertNotIn("身体状况", final.text or "")

    def test_web_and_context_budgets_are_independent(self) -> None:
        web = FakeTavilyClient()
        with food_fixture(
            _context_call(),
            _web_call("午餐 浦东", purpose="find_current_lunch"),
            _food_result(),
            web_client=web,
        ) as fixture:
            final = fixture.effector.execute(request=fixture.request, bundle=fixture.bundle)

            self.assertEqual(FinalEffectKind.REPLY, final.kind, final.reason_code)
            self.assertEqual([("context", 1), ("web", 1)], fixture.tool_budget_rows())

    def test_five_web_attempts_succeed_and_sixth_is_rejected_before_provider(self) -> None:
        web = FakeTavilyClient()
        script = [
            _web_call(f"午餐候选 {index} 浦东", purpose=f"search_gap_{index}")
            for index in range(1, 7)
        ]
        script.append(_food_result())
        with food_fixture(
            *script,
            web_client=web,
            budgets=EffectorBudgets(
                maximum_model_calls=11,
                ordinary_tool_calls=3,
                maximum_tool_calls=5,
                maximum_web_tool_calls=5,
            ),
        ) as fixture:
            final = fixture.effector.execute(request=fixture.request, bundle=fixture.bundle)

            self.assertEqual(FinalEffectKind.REPLY, final.kind, final.reason_code)
            self.assertEqual(5, web.search_calls)
            self.assertEqual(
                [("web", ordinal) for ordinal in range(1, 6)],
                fixture.tool_budget_rows(),
            )
            sixth_system = fixture.model.calls[5]["messages"][0].content
            self.assertNotIn(
                '"web_search"', sixth_system.split("AVAILABLE_TOOLS=", 1)[1].split("\n", 1)[0]
            )

    def test_scheduled_final_clock_failures_terminally_degrade_to_silence(self) -> None:
        for failure_mode, expected_reason in (
            ("raise", "final_clock_unavailable"),
            ("naive", "final_clock_invalid"),
        ):
            with (
                self.subTest(failure_mode=failure_mode),
                food_fixture(_food_result(), final_clock_failure=failure_mode) as fixture,
            ):
                final = fixture.effector.execute(request=fixture.request, bundle=fixture.bundle)

                self.assertEqual(FinalEffectKind.SILENCE, final.kind)
                self.assertEqual(expected_reason, final.reason_code)
                with fixture.database.connect() as connection:
                    run = connection.execute(
                        "SELECT status, reason_code FROM effect_runs"
                    ).fetchone()
                    audit = connection.execute(
                        "SELECT status, degradation_reason FROM temporal_answer_audit"
                    ).fetchone()
                self.assertEqual(("silence", expected_reason), tuple(run))
                self.assertEqual(("silence", expected_reason), tuple(audit))


class FoodFixture:
    def __init__(
        self,
        *,
        database: Any,
        bundle: CharacterBundle,
        model: ScriptedModelClient,
        effector: WriterEffector,
        request: EffectRequest,
    ) -> None:
        self.database = database
        self.bundle = bundle
        self.model = model
        self.effector = effector
        self.request = request

    def tool_budget_rows(self) -> list[tuple[str, int]]:
        connection = self.database.connect()
        try:
            rows = connection.execute(
                "SELECT budget_kind, budget_ordinal FROM tool_call_audit ORDER BY id"
            ).fetchall()
        finally:
            connection.close()
        return [(str(row["budget_kind"]), int(row["budget_ordinal"])) for row in rows]


@contextmanager
def food_fixture(
    *script: StructuredModelResult,
    recent_primary_keys: tuple[str, ...] = (),
    web_client: FakeTavilyClient | None = None,
    budgets: EffectorBudgets | None = None,
    final_clock_failure: str | None = None,
) -> Iterator[FoodFixture]:
    with temporary_database() as database:
        bundle = load_character_bundle(Path(__file__).parent / "fixtures/personas/test-original/v1")
        messages = MessageRepository(database)
        runs = RunRepository(database)
        contexts = ContextAssembler(
            messages=messages,
            memory=MemoryRepository(database),
            recognition_policy_version="policy-v1",
        )
        model = ScriptedModelClient(*script)
        registry = ReadOnlyToolRegistry(
            messages=messages, memory=MemoryRepository(database), runs=runs
        )
        web_factory = None
        if web_client is not None:
            web_factory = lambda: WebToolSession(
                client=web_client,  # type: ignore[arg-type]
                runs=runs,
                resolver=_public_resolver,
            )
        now = datetime.now(UTC)
        clock_calls = 0

        def clock() -> datetime:
            nonlocal clock_calls
            clock_calls += 1
            if clock_calls > 1 and final_clock_failure == "raise":
                raise RuntimeError("injected final clock failure")
            if clock_calls > 1 and final_clock_failure == "naive":
                return now.replace(tzinfo=None)
            return now

        effector = WriterEffector(
            model=model,
            contexts=contexts,
            tools=registry,
            runs=runs,
            budgets=budgets
            or EffectorBudgets(
                maximum_model_calls=4,
                ordinary_tool_calls=2,
                maximum_tool_calls=3,
                maximum_web_tool_calls=3,
            ),
            web_session_factory=web_factory,
            clock=clock,
        )
        scheduled = ScheduledOccurrenceSource(
            occurrence_id="occurrence-1",
            occurrence_key="bot|group-a|weekday_food_recommendation|2026-08-03|lunch",
            chat_id="group-a",
            automation_type="weekday_food_recommendation",
            local_date="2026-08-03",
            meal_slot="lunch",
            scheduled_for=datetime(2026, 8, 3, 3, 30, tzinfo=UTC),
            timezone="Asia/Shanghai",
            config_version=1,
            subscriber_count=2,
            preference_summary=("budget:medium", "cuisine:noodles"),
            location_text="上海浦东",
            recent_primary_keys=recent_primary_keys,
        )
        request = EffectRequest(
            request_id="scheduled-request-1",
            trigger_path=TriggerPath.SCHEDULED,
            trigger_category=TriggerCategory.SCHEDULED_AUTOMATION,
            trigger_reason="scheduled_occurrence",
            message=None,
            scheduled=scheduled,
            persona=bundle.snapshot,
            deadline_at=now + timedelta(seconds=60),
        )
        yield FoodFixture(
            database=database,
            bundle=bundle,
            model=model,
            effector=effector,
            request=request,
        )


class FakeTavilyClient:
    def __init__(self, *, titles: tuple[str, str, str] | None = None) -> None:
        self.search_calls = 0
        self.titles = titles or ("浦东面馆", "浦东饭馆", "浦东小馆")

    def search(self, *, query: str, deadline: datetime) -> TavilySearchResponse:
        del query, deadline
        self.search_calls += 1
        return TavilySearchResponse(
            results=tuple(
                TavilySearchResult(
                    title=self.titles[index - 1],
                    url=f"https://example.com/result-{self.search_calls}-{index}",
                    content="Bounded current restaurant evidence.",
                    score=0.9,
                )
                for index in range(1, 4)
            ),
            request_id=f"request-{self.search_calls}",
            credits=1.0,
            retrieved_at=datetime(2026, 8, 3, 3, 30, tzinfo=UTC),
        )


def _public_resolver(
    host: str,
    port: int,
) -> list[tuple[int, int, int, str, tuple[object, ...]]]:
    del host, port
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def _food_result(
    *,
    mode: str = "generic",
    primary_choice_type: str | None = None,
    primary_id: str | None = "dish:hot-noodles",
    source_ids: list[str] | None = None,
) -> StructuredModelResult:
    sources = source_ids or []
    sourced = mode == "sourced"
    choice_type = primary_choice_type or ("merchant" if sourced else "generic_dish")

    def choice(index: int, generic_id: str, reason_tag: str) -> dict[str, object]:
        return {
            "choice_type": "merchant" if sourced else "generic_dish",
            "generic_dish_id": None if sourced else generic_id,
            "source_result_id": sources[index] if sourced else None,
            "reason_tag": reason_tag,
        }

    return StructuredModelResult(
        {
            "kind": "food_recommendation",
            "reason_code": "weekday_food_choice",
            "mode": mode,
            "primary": {
                "choice_type": choice_type,
                "generic_dish_id": None if choice_type == "merchant" else primary_id,
                "source_result_id": sources[0] if sourced and sources else None,
                "reason_tag": "warming",
            },
            "alternatives": [
                choice(1, "dish:rice-bowl", "hearty"),
                choice(2, "dish:dumplings", "shareable"),
            ],
        }
    )


def _web_call(query: str, *, purpose: str) -> StructuredModelResult:
    return StructuredModelResult(
        {
            "kind": "call_tool",
            "reason_code": "need_current_food_info",
            "tool_name": "web_search",
            "tool_arguments": {"query": query},
            "tool_purpose_code": purpose,
        }
    )


def _context_call() -> StructuredModelResult:
    return StructuredModelResult(
        {
            "kind": "call_tool",
            "reason_code": "need_group_context",
            "tool_name": "search_recent_group_messages",
            "tool_arguments": {"query": "午餐"},
            "tool_purpose_code": "understand_group_context",
        }
    )


if __name__ == "__main__":
    unittest.main()
