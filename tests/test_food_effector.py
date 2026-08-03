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
            self.assertEqual("dish:noodles", final.primary_key)
            self.assertEqual((), final.source_urls)
            self.assertIn("主推：热汤面", final.text or "")
            scene = fixture.model.calls[0]["messages"][1].content
            self.assertIn('"source_kind":"scheduled"', scene)
            self.assertIn('"meal_slot":"lunch"', scene)
            self.assertNotIn("sender_user_id", scene)
            self.assertNotIn("current_message", scene)

    def test_food_final_validator_rejects_recent_primary_and_generic_current_claims(self) -> None:
        cases = (
            (
                "recent_primary",
                _food_result(),
                ("dish:noodles",),
                "food_primary_recently_used",
            ),
            (
                "generic_current_fact",
                _food_result(primary_description="附近这家现在营业，人均 35 元。"),
                (),
                "food_generic_current_fact",
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
                primary_key="merchant:noodle-house",
                primary_label="浦东面馆",
                primary_description="可以先把它当作热乎的主推。",
                source_ids=["web:1"],
                freshness_note="营业与价格可能变化，出发前再确认。",
            ),
            web_client=web,
        ) as fixture:
            final = fixture.effector.execute(request=fixture.request, bundle=fixture.bundle)

            self.assertEqual(FinalEffectKind.REPLY, final.kind, final.reason_code)
            self.assertEqual(("https://example.com/result-1",), final.source_urls)
            self.assertIn("来源：https://example.com/result-1", final.text or "")
            self.assertEqual(1, web.search_calls)
            self.assertEqual([("web", 1)], fixture.tool_budget_rows())

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
            clock=lambda: now,
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
    def __init__(self) -> None:
        self.search_calls = 0

    def search(self, *, query: str, deadline: datetime) -> TavilySearchResponse:
        del query, deadline
        self.search_calls += 1
        return TavilySearchResponse(
            results=(
                TavilySearchResult(
                    title=f"Result {self.search_calls}",
                    url=f"https://example.com/result-{self.search_calls}",
                    content="Bounded current restaurant evidence.",
                    score=0.9,
                ),
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
    primary_key: str = "dish:noodles",
    primary_label: str = "热汤面",
    primary_description: str = "暖和、好选，先用它做主推。",
    source_ids: list[str] | None = None,
    freshness_note: str | None = None,
) -> StructuredModelResult:
    return StructuredModelResult(
        {
            "kind": "food_recommendation",
            "reason_code": "weekday_food_choice",
            "mode": mode,
            "primary": {
                "canonical_key": primary_key,
                "label": primary_label,
                "description": primary_description,
            },
            "alternatives": [
                {
                    "canonical_key": "dish:rice-bowl",
                    "label": "杂粮盖饭",
                    "description": "更扎实，适合想吃饱一点。",
                },
                {
                    "canonical_key": "dish:dumplings",
                    "label": "煎饺配小菜",
                    "description": "换个脆香方向，也方便分享。",
                },
            ],
            "source_result_ids": source_ids or [],
            "cautious_freshness_note": freshness_note,
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
