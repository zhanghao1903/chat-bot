from __future__ import annotations

import ipaddress
import json
import re
import socket
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import cast

from group_llm_agent.model import WriterDecision, WriterDecisionKind
from group_llm_agent.runs import RunRepository
from group_llm_agent.tavily import TavilyApiError, TavilyClient

WEB_SEARCH = "web_search"
WEB_FETCH = "web_fetch"
WEB_TOOLS = frozenset({WEB_SEARCH, WEB_FETCH})
_URL_IN_QUERY = re.compile(r"(?:https?://|\bwww\.)", re.IGNORECASE)

Resolver = Callable[[str, int], list[tuple[int, int, int, str, tuple[object, ...]]]]


@dataclass(frozen=True)
class WebToolScope:
    effect_run_id: int
    chat_id: str
    deadline_at: datetime
    scheduled: bool
    location_text: str | None = None
    explicit_message_urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class WebToolExecutionResult:
    audit_id: int
    capability: str
    status: str
    content_json: str
    result_count: int
    result_char_count: int

    def as_untrusted_prompt_data(self) -> str:
        return (
            f"BEGIN_UNTRUSTED_EXTERNAL_CONTENT\n{self.content_json}\nEND_UNTRUSTED_EXTERNAL_CONTENT"
        )


class WebToolSession:
    def __init__(
        self,
        *,
        client: TavilyClient,
        runs: RunRepository,
        resolver: Resolver | None = None,
    ) -> None:
        self.client = client
        self.runs = runs
        self.resolver = resolver or _resolve
        self.allowed_tools = WEB_TOOLS
        self._urls: dict[str, str] = {}
        self._searched_queries: set[str] = set()
        self._fetched_urls: set[str] = set()
        self._next_result_id = 1

    @property
    def citation_urls(self) -> dict[str, str]:
        return dict(self._urls)

    def execute(
        self,
        decision: WriterDecision,
        *,
        scope: WebToolScope,
    ) -> WebToolExecutionResult:
        if (
            decision.kind is not WriterDecisionKind.CALL_TOOL
            or decision.tool_name not in WEB_TOOLS
            or decision.tool_arguments is None
            or decision.tool_purpose_code is None
        ):
            raise ValueError("Web tool session requires a complete Web call")
        started = monotonic()
        if datetime.now(UTC) >= scope.deadline_at:
            return self._result(
                scope=scope,
                capability=decision.tool_name,
                purpose_code=decision.tool_purpose_code,
                status="timeout",
                payload={"error": "deadline_exhausted"},
                result_count=0,
                started=started,
                error_code="timeout",
            )
        try:
            if decision.tool_name == WEB_SEARCH:
                return self._search(decision, scope=scope, started=started)
            return self._fetch(decision, scope=scope, started=started)
        except (ValueError, TypeError):
            return self._result(
                scope=scope,
                capability=decision.tool_name,
                purpose_code=decision.tool_purpose_code,
                status="invalid_arguments",
                payload={"error": "invalid_arguments"},
                result_count=0,
                started=started,
                error_code="invalid_arguments",
            )
        except TavilyApiError as error:
            return self._result(
                scope=scope,
                capability=decision.tool_name,
                purpose_code=decision.tool_purpose_code,
                status="unavailable",
                payload={"error": "web_unavailable", "category": error.category},
                result_count=0,
                started=started,
                error_code=error.category,
            )
        except (OSError, socket.gaierror):
            return self._result(
                scope=scope,
                capability=decision.tool_name,
                purpose_code=decision.tool_purpose_code,
                status="unavailable",
                payload={"error": "web_unavailable"},
                result_count=0,
                started=started,
                error_code="transport",
            )

    def record_rejected_attempt(
        self,
        *,
        scope: WebToolScope,
        capability: str,
        purpose_code: str,
        status: str,
    ) -> WebToolExecutionResult:
        return self._result(
            scope=scope,
            capability=capability[:128] or "invalid",
            purpose_code=purpose_code[:64] or "invalid",
            status=status,
            payload={"error": status},
            result_count=0,
            started=monotonic(),
            error_code=status,
        )

    def _search(
        self,
        decision: WriterDecision,
        *,
        scope: WebToolScope,
        started: float,
    ) -> WebToolExecutionResult:
        arguments = decision.tool_arguments
        assert arguments is not None
        if set(arguments) != {"query"}:
            raise ValueError("unexpected search arguments")
        query = arguments["query"]
        if (
            not isinstance(query, str)
            or not query.strip()
            or len(query) > 400
            or _URL_IN_QUERY.search(query)
            or any(ord(char) < 32 for char in query)
        ):
            raise ValueError("invalid search query")
        normalized_query = " ".join(query.casefold().split())
        if normalized_query in self._searched_queries:
            raise ValueError("duplicate search query")
        if scope.scheduled and not scope.location_text:
            raise ValueError("scheduled merchant search requires group location")
        self._searched_queries.add(normalized_query)
        response = self.client.search(query=query, deadline=scope.deadline_at)
        items: list[dict[str, object]] = []
        domains: set[str] = set()
        for result in response.results:
            try:
                normalized = normalize_public_url(result.url, resolver=self.resolver)
            except (ValueError, OSError, socket.gaierror):
                continue
            if normalized in self._urls.values():
                continue
            result_id = f"web:{self._next_result_id}"
            self._next_result_id += 1
            self._urls[result_id] = normalized
            host = urllib.parse.urlsplit(normalized).hostname
            assert host is not None
            domains.add(host)
            items.append(
                {
                    "result_id": result_id,
                    "title": result.title,
                    "url": normalized,
                    "snippet": result.content,
                    "score": round(result.score, 6),
                }
            )
        return self._result(
            scope=scope,
            capability=WEB_SEARCH,
            purpose_code=decision.tool_purpose_code or "unspecified",
            status="success" if items else "empty",
            payload={
                "capability": WEB_SEARCH,
                "retrieved_at": response.retrieved_at.isoformat(),
                "items": items,
            },
            result_count=len(items),
            started=started,
            request_id=response.request_id,
            credits=response.credits,
            domains=domains,
            retrieved_at=response.retrieved_at,
        )

    def _fetch(
        self,
        decision: WriterDecision,
        *,
        scope: WebToolScope,
        started: float,
    ) -> WebToolExecutionResult:
        arguments = decision.tool_arguments
        assert arguments is not None
        if set(arguments) != {"result_id"}:
            raise ValueError("unexpected fetch arguments")
        result_id = arguments["result_id"]
        if not isinstance(result_id, str) or result_id not in self._urls:
            raise ValueError("fetch result is not authorized in current turn")
        url = self._urls[result_id]
        if url in self._fetched_urls:
            raise ValueError("duplicate fetch")
        normalize_public_url(url, resolver=self.resolver)
        self._fetched_urls.add(url)
        response = self.client.extract(url=url, deadline=scope.deadline_at)
        response_url = normalize_public_url(response.result.url, resolver=self.resolver)
        if response_url != url:
            raise ValueError("extract URL drift")
        host = urllib.parse.urlsplit(url).hostname
        assert host is not None
        return self._result(
            scope=scope,
            capability=WEB_FETCH,
            purpose_code=decision.tool_purpose_code or "unspecified",
            status="success",
            payload={
                "capability": WEB_FETCH,
                "result_id": result_id,
                "url": url,
                "retrieved_at": response.retrieved_at.isoformat(),
                "content": response.result.content,
            },
            result_count=1,
            started=started,
            request_id=response.request_id,
            credits=response.credits,
            domains={host},
            retrieved_at=response.retrieved_at,
        )

    def _result(
        self,
        *,
        scope: WebToolScope,
        capability: str,
        purpose_code: str,
        status: str,
        payload: dict[str, object],
        result_count: int,
        started: float,
        request_id: str | None = None,
        credits: float | None = None,
        domains: set[str] | None = None,
        retrieved_at: datetime | None = None,
        error_code: str | None = None,
    ) -> WebToolExecutionResult:
        content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(content) > 10_000:
            content = json.dumps({"capability": capability, "error": "result_too_large"})
            status = "result_too_large"
            result_count = 0
            error_code = "result_too_large"
        audit_id = self.runs.record_tool_call(
            owner_kind="effect",
            owner_id=scope.effect_run_id,
            chat_id=scope.chat_id,
            capability=capability,
            purpose_code=purpose_code,
            source_scope="current_turn_web",
            status=status,
            latency_ms=max(0, int((monotonic() - started) * 1_000)),
            result_count=result_count,
            result_char_count=len(content),
            budget_kind="web",
            provider_request_id=request_id,
            provider_credits=credits,
            source_domains_json=(
                json.dumps(sorted(domains), separators=(",", ":")) if domains else None
            ),
            retrieved_at=retrieved_at,
            provider_error_code=error_code,
        )
        return WebToolExecutionResult(
            audit_id=audit_id,
            capability=capability,
            status=status,
            content_json=content,
            result_count=result_count,
            result_char_count=len(content),
        )


def normalize_public_url(url: str, *, resolver: Resolver | None = None) -> str:
    if not isinstance(url, str) or not url or len(url) > 2_048:
        raise ValueError("invalid URL")
    split = urllib.parse.urlsplit(url)
    scheme = split.scheme.casefold()
    if scheme not in {"http", "https"} or not split.hostname:
        raise ValueError("URL must use HTTP(S)")
    if split.username is not None or split.password is not None or split.fragment:
        raise ValueError("URL credentials and fragments are forbidden")
    try:
        port = split.port
    except ValueError:
        raise ValueError("invalid URL port") from None
    expected_port = 443 if scheme == "https" else 80
    if port not in {None, expected_port}:
        raise ValueError("non-default URL port is forbidden")
    host = split.hostname.casefold().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local")):
        raise ValueError("local URL is forbidden")
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise ValueError("invalid URL host") from None
    addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    try:
        addresses.add(ipaddress.ip_address(ascii_host))
    except ValueError:
        lookup = (resolver or _resolve)(ascii_host, expected_port)
        for item in lookup:
            sockaddr = item[4]
            if not sockaddr:
                continue
            addresses.add(ipaddress.ip_address(str(sockaddr[0])))
    if not addresses or not all(address.is_global for address in addresses):
        raise ValueError("URL host is not globally routable")
    path = urllib.parse.quote(urllib.parse.unquote(split.path or "/"), safe="/%:@!$&'()*+,;=-._~")
    query = urllib.parse.quote(urllib.parse.unquote(split.query), safe="=&;%:@!$'()*+,-._~/?")
    netloc = f"[{ascii_host}]" if ":" in ascii_host else ascii_host
    return urllib.parse.urlunsplit((scheme, netloc, path, query, ""))


def _resolve(host: str, port: int) -> list[tuple[int, int, int, str, tuple[object, ...]]]:
    return cast(
        list[tuple[int, int, int, str, tuple[object, ...]]],
        socket.getaddrinfo(host, port, type=socket.SOCK_STREAM),
    )
