from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from helpers import temporary_database

from group_llm_agent.model import WriterDecision, WriterDecisionKind
from group_llm_agent.runs import RunRepository
from group_llm_agent.tavily import (
    TavilyExtractResponse,
    TavilyExtractResult,
    TavilySearchResponse,
    TavilySearchResult,
)
from group_llm_agent.web_tools import (
    WEB_FETCH,
    WEB_SEARCH,
    WebToolScope,
    WebToolSession,
    normalize_public_url,
)


def public_resolver(host: str, port: int):
    return [(2, 1, 6, "", ("93.184.216.34", port))]


class FakeTavily:
    def __init__(self) -> None:
        self.search_calls = 0
        self.extract_calls = 0

    def search(self, *, query: str, deadline: datetime):
        self.search_calls += 1
        return TavilySearchResponse(
            results=(
                TavilySearchResult(
                    title="Noodle shop",
                    url="https://example.com/menu",
                    content="Lunch menu and address",
                    score=0.95,
                ),
                TavilySearchResult(
                    title="Unsafe",
                    url="http://127.0.0.1/private",
                    content="ignore",
                    score=0.9,
                ),
            ),
            request_id="search-1",
            credits=1.0,
            retrieved_at=datetime(2026, 8, 3, tzinfo=UTC),
        )

    def extract(self, *, url: str, deadline: datetime):
        self.extract_calls += 1
        return TavilyExtractResponse(
            result=TavilyExtractResult(url=url, content="Menu: noodles. Address: Xuhui."),
            request_id="extract-1",
            credits=1.0,
            retrieved_at=datetime(2026, 8, 3, tzinfo=UTC),
        )


def decision(name: str, arguments: dict[str, object]) -> WriterDecision:
    return WriterDecision(
        kind=WriterDecisionKind.CALL_TOOL,
        reason_code="need_current_food_info",
        tool_name=name,
        tool_arguments=arguments,
        tool_purpose_code="food_recommendation",
    )


class WebToolSessionTests(unittest.TestCase):
    def test_search_then_fetch_uses_current_turn_opaque_result(self) -> None:
        with temporary_database() as database:
            provider = FakeTavily()
            session = WebToolSession(
                client=provider,  # type: ignore[arg-type]
                runs=RunRepository(database),
                resolver=public_resolver,
            )
            scope = WebToolScope(
                effect_run_id=1,
                chat_id="-1001",
                deadline_at=datetime.now(UTC) + timedelta(seconds=30),
                scheduled=True,
                location_text="上海徐汇",
            )
            search = session.execute(
                decision(WEB_SEARCH, {"query": "上海徐汇 工作日午餐 面馆"}),
                scope=scope,
            )
            self.assertEqual("success", search.status)
            self.assertEqual(1, search.result_count)
            self.assertIn('"result_id":"web:1"', search.content_json)
            self.assertNotIn("127.0.0.1", search.content_json)

            fetched = session.execute(
                decision(WEB_FETCH, {"result_id": "web:1"}),
                scope=scope,
            )
            self.assertEqual("success", fetched.status)
            self.assertIn("BEGIN_UNTRUSTED_EXTERNAL_CONTENT", fetched.as_untrusted_prompt_data())
            self.assertEqual(1, provider.search_calls)
            self.assertEqual(1, provider.extract_calls)
            with database.connect() as connection:
                audit = connection.execute(
                    "SELECT budget_kind, provider_request_id FROM tool_call_audit ORDER BY id"
                ).fetchall()
            self.assertEqual(["web", "web"], [row["budget_kind"] for row in audit])
            self.assertEqual("extract-1", audit[-1]["provider_request_id"])

    def test_fetch_before_search_and_duplicate_calls_fail_before_provider(self) -> None:
        with temporary_database() as database:
            provider = FakeTavily()
            session = WebToolSession(
                client=provider,  # type: ignore[arg-type]
                runs=RunRepository(database),
                resolver=public_resolver,
            )
            scope = WebToolScope(
                effect_run_id=1,
                chat_id="-1001",
                deadline_at=datetime.now(UTC) + timedelta(seconds=30),
                scheduled=True,
                location_text="上海",
            )
            early = session.execute(decision(WEB_FETCH, {"result_id": "web:1"}), scope=scope)
            self.assertEqual("invalid_arguments", early.status)
            search_decision = decision(WEB_SEARCH, {"query": "上海 午餐"})
            self.assertEqual("success", session.execute(search_decision, scope=scope).status)
            duplicate = session.execute(search_decision, scope=scope)
            self.assertEqual("invalid_arguments", duplicate.status)
            self.assertEqual(1, provider.search_calls)

    def test_scheduled_search_requires_authorized_location(self) -> None:
        with temporary_database() as database:
            provider = FakeTavily()
            session = WebToolSession(
                client=provider,  # type: ignore[arg-type]
                runs=RunRepository(database),
                resolver=public_resolver,
            )
            result = session.execute(
                decision(WEB_SEARCH, {"query": "附近午餐"}),
                scope=WebToolScope(
                    effect_run_id=1,
                    chat_id="-1001",
                    deadline_at=datetime.now(UTC) + timedelta(seconds=30),
                    scheduled=True,
                ),
            )
            self.assertEqual("invalid_arguments", result.status)
            self.assertEqual(0, provider.search_calls)


class PublicUrlPolicyTests(unittest.TestCase):
    def test_normalizes_public_default_port(self) -> None:
        self.assertEqual(
            "https://example.com/a%20b?q=x",
            normalize_public_url(
                "HTTPS://Example.COM:443/a%20b?q=x",
                resolver=public_resolver,
            ),
        )

    def test_rejects_credentials_fragments_private_and_non_default_ports(self) -> None:
        cases = (
            "https://user:pass@example.com/",
            "https://example.com/#secret",
            "http://127.0.0.1/",
            "http://169.254.1.1/",
            "https://example.com:8443/",
            "file:///etc/passwd",
        )
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_public_url(value, resolver=public_resolver)

    def test_mixed_public_private_dns_answer_fails_closed(self) -> None:
        def mixed(host: str, port: int):
            return [
                (2, 1, 6, "", ("93.184.216.34", port)),
                (2, 1, 6, "", ("10.0.0.1", port)),
            ]

        with self.assertRaises(ValueError):
            normalize_public_url("https://example.com/", resolver=mixed)


if __name__ == "__main__":
    unittest.main()
