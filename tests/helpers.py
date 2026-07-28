from __future__ import annotations

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from group_llm_agent.database import SQLiteDatabase


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
