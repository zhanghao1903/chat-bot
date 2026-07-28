from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

from group_llm_agent.database import SQLiteDatabase


@contextmanager
def temporary_database() -> Iterator[SQLiteDatabase]:
    with TemporaryDirectory() as tmpdir:
        database = SQLiteDatabase(Path(tmpdir) / "runtime.sqlite3")
        database.initialize()
        yield database
