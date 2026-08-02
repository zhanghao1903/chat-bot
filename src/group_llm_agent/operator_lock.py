from __future__ import annotations

import fcntl
import signal
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import FrameType
from typing import Any


class OperatorInterrupted(RuntimeError):
    def __init__(self, signal_number: int) -> None:
        self.signal_number = signal_number
        super().__init__(f"operator_interrupted_signal_{signal_number}")


@contextmanager
def operator_lock(path: Path) -> Iterator[None]:
    """Keep one operator mutation owner through verification or rollback."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("operator_lock_busy") from None
        watched = tuple(
            item for item in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM) if item is not None
        )
        previous = {item: signal.getsignal(item) for item in watched}

        def interrupt(signal_number: int, _frame: FrameType | None) -> Any:
            for item in watched:
                signal.signal(item, signal.SIG_IGN)
            raise OperatorInterrupted(signal_number)

        for item in watched:
            signal.signal(item, interrupt)
        try:
            yield
        finally:
            for item, handler in previous.items():
                signal.signal(item, handler)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
