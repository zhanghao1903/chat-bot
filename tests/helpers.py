from __future__ import annotations

import shutil
from collections import deque
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from group_llm_agent.database import SQLiteDatabase
from group_llm_agent.model import (
    ModelMessage,
    ModelRole,
    StructuredModelResult,
)


@contextmanager
def temporary_database() -> Iterator[SQLiteDatabase]:
    with TemporaryDirectory() as tmpdir:
        database = SQLiteDatabase(Path(tmpdir) / "runtime.sqlite3")
        database.initialize()
        yield database


@contextmanager
def copied_persona_fixture() -> Iterator[Path]:
    source = Path(__file__).parent / "fixtures/personas/test-original/v1"
    with TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "test-original-v1"
        shutil.copytree(source, target)
        yield target


class ScriptedModelClient:
    def __init__(self, *script: StructuredModelResult | Exception) -> None:
        self.script = deque(script)
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        *,
        model_role: ModelRole,
        messages: Sequence[ModelMessage],
        response_schema: Mapping[str, Any],
        deadline: datetime,
        max_output_tokens: int,
        temperature: float,
    ) -> StructuredModelResult:
        self.calls.append(
            {
                "model_role": model_role,
                "messages": tuple(messages),
                "response_schema": dict(response_schema),
                "deadline": deadline,
                "max_output_tokens": max_output_tokens,
                "temperature": temperature,
            }
        )
        if not self.script:
            raise AssertionError("No scripted model result remains")
        next_item = self.script.popleft()
        if isinstance(next_item, Exception):
            raise next_item
        return next_item
