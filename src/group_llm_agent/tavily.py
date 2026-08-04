from __future__ import annotations

import http.client
import json
import socket
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_BASE_URL = "https://api.tavily.com"
_MAX_RESPONSE_BYTES = 512_000
_MAX_RESULT_CONTENT = 2_000
_MAX_EXTRACT_CONTENT = 8_000
_MAX_TOTAL_CONTENT = 16_000


class TavilyApiError(RuntimeError):
    """A redacted provider failure safe for logs and bounded tool results."""

    def __init__(self, operation: str, category: str, status_code: int | None = None) -> None:
        self.operation = operation
        self.category = category
        self.status_code = status_code
        suffix = f" http_status={status_code}" if status_code is not None else ""
        super().__init__(f"tavily_operation={operation} category={category}{suffix}")


@dataclass(frozen=True)
class TavilySearchResult:
    title: str
    url: str
    content: str
    score: float


@dataclass(frozen=True)
class TavilySearchResponse:
    results: tuple[TavilySearchResult, ...]
    request_id: str | None
    credits: float | None
    retrieved_at: datetime


@dataclass(frozen=True)
class TavilyExtractResult:
    url: str
    content: str


@dataclass(frozen=True)
class TavilyExtractResponse:
    result: TavilyExtractResult
    request_id: str | None
    credits: float | None
    retrieved_at: datetime


UrlOpener = Callable[[urllib.request.Request, float], Any]


class TavilyClient:
    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 8.0,
        project_id: str | None = None,
        opener: UrlOpener | None = None,
    ) -> None:
        self._api_key = _secret(api_key)
        if not 3 <= timeout_seconds <= 10:
            raise ValueError("timeout_seconds must be in [3, 10]")
        if project_id is not None and (
            not project_id or len(project_id) > 128 or any(ord(char) < 33 for char in project_id)
        ):
            raise ValueError("invalid Tavily project id")
        self.timeout_seconds = timeout_seconds
        self.project_id = project_id
        self._opener = opener or _urlopen

    def __repr__(self) -> str:
        return "TavilyClient(api_key=<redacted>, base_url=<fixed>)"

    def search(
        self,
        *,
        query: str,
        deadline: datetime,
        max_results: int = 5,
    ) -> TavilySearchResponse:
        if not query.strip() or len(query) > 400 or any(ord(char) < 32 for char in query):
            raise ValueError("invalid search query")
        if not 1 <= max_results <= 5:
            raise ValueError("max_results must be in [1, 5]")
        envelope = self._request(
            operation="search",
            deadline=deadline,
            payload={
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                "chunks_per_source": 1,
                "include_answer": False,
                "include_raw_content": False,
                "include_images": False,
                "include_usage": True,
                "safe_search": True,
            },
        )
        raw_results = envelope.get("results")
        if not isinstance(raw_results, list) or len(raw_results) > max_results:
            raise TavilyApiError("search", "invalid_response")
        results: list[TavilySearchResult] = []
        total = 0
        for raw in raw_results:
            if not isinstance(raw, dict):
                raise TavilyApiError("search", "invalid_response")
            title = _bounded_text(raw.get("title"), maximum=300)
            url = _bounded_text(raw.get("url"), maximum=2_048)
            content = _bounded_text(raw.get("content"), maximum=_MAX_RESULT_CONTENT)
            score = raw.get("score")
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                raise TavilyApiError("search", "invalid_response")
            total += len(title) + len(url) + len(content)
            if total > _MAX_TOTAL_CONTENT:
                raise TavilyApiError("search", "result_too_large")
            results.append(
                TavilySearchResult(
                    title=title,
                    url=url,
                    content=content,
                    score=float(score),
                )
            )
        return TavilySearchResponse(
            results=tuple(results),
            request_id=_optional_text(envelope.get("request_id"), maximum=256),
            credits=_credits(envelope),
            retrieved_at=datetime.now(UTC),
        )

    def extract(
        self,
        *,
        url: str,
        deadline: datetime,
        query: str | None = None,
    ) -> TavilyExtractResponse:
        if not url or len(url) > 2_048:
            raise ValueError("invalid extract URL")
        if query is not None and (not query.strip() or len(query) > 400):
            raise ValueError("invalid extract query")
        payload: dict[str, object] = {
            "urls": [url],
            "extract_depth": "basic",
            "format": "markdown",
            "chunks_per_source": 1,
            "include_images": False,
            "include_usage": True,
            "timeout": min(10, max(1, int(self.timeout_seconds))),
        }
        if query is not None:
            payload["query"] = query
        envelope = self._request(operation="extract", deadline=deadline, payload=payload)
        raw_results = envelope.get("results")
        failed = envelope.get("failed_results", [])
        if (
            not isinstance(raw_results, list)
            or len(raw_results) != 1
            or not isinstance(failed, list)
            or failed
        ):
            raise TavilyApiError("extract", "empty_result")
        raw = raw_results[0]
        if not isinstance(raw, dict):
            raise TavilyApiError("extract", "invalid_response")
        result_url = _bounded_text(raw.get("url"), maximum=2_048)
        content_value = raw.get("raw_content", raw.get("content"))
        content = _bounded_text(content_value, maximum=_MAX_EXTRACT_CONTENT)
        if not content.strip():
            raise TavilyApiError("extract", "empty_result")
        return TavilyExtractResponse(
            result=TavilyExtractResult(url=result_url, content=content),
            request_id=_optional_text(envelope.get("request_id"), maximum=256),
            credits=_credits(envelope),
            retrieved_at=datetime.now(UTC),
        )

    def _request(
        self,
        *,
        operation: str,
        deadline: datetime,
        payload: dict[str, object],
    ) -> dict[str, Any]:
        timeout = _remaining_timeout(deadline, maximum=self.timeout_seconds)
        if timeout <= 0:
            raise TavilyApiError(operation, "timeout")
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self.project_id is not None:
            headers["X-Project-ID"] = self.project_id
        request = urllib.request.Request(
            f"{_BASE_URL}/{operation}",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with self._opener(request, timeout) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            raise TavilyApiError(operation, _http_category(error.code), error.code) from None
        except urllib.error.URLError as error:
            category = (
                "timeout"
                if isinstance(error.reason, (TimeoutError, socket.timeout))
                else "transport"
            )
            raise TavilyApiError(operation, category) from None
        except TimeoutError:
            raise TavilyApiError(operation, "timeout") from None
        except (http.client.InvalidURL, ValueError):
            raise TavilyApiError(operation, "transport") from None
        except (http.client.HTTPException, OSError):
            raise TavilyApiError(operation, "transport") from None
        if not isinstance(raw, bytes) or len(raw) > _MAX_RESPONSE_BYTES:
            raise TavilyApiError(operation, "result_too_large")
        try:
            parsed = json.loads(raw.decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise TavilyApiError(operation, "invalid_response") from None
        if not isinstance(parsed, dict):
            raise TavilyApiError(operation, "invalid_response")
        return parsed


def _secret(value: str) -> str:
    if (
        not value
        or value != value.strip()
        or len(value) > 512
        or any(ord(char) < 33 or ord(char) == 127 for char in value)
    ):
        raise ValueError("invalid Tavily API key")
    return value


def _remaining_timeout(deadline: datetime, *, maximum: float) -> float:
    if deadline.tzinfo is None:
        raise ValueError("deadline must be timezone-aware")
    return min(maximum, max(0.0, (deadline - datetime.now(UTC)).total_seconds()))


def _bounded_text(value: object, *, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise TavilyApiError("response", "invalid_response")
    return value


def _optional_text(value: object, *, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise TavilyApiError("response", "invalid_response")
    return value


def _credits(envelope: dict[str, Any]) -> float | None:
    usage = envelope.get("usage")
    if usage is None:
        return None
    if not isinstance(usage, dict):
        raise TavilyApiError("response", "invalid_response")
    value = usage.get("credits")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise TavilyApiError("response", "invalid_response")
    return float(value)


def _http_category(status: int) -> str:
    return {
        400: "invalid_request",
        401: "authentication",
        429: "rate_limited",
        432: "plan_limit",
        433: "spend_limit",
    }.get(status, "provider" if status >= 500 else "invalid_request")


def _urlopen(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)
