from __future__ import annotations

import os
import signal
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from group_llm_agent.operator_lock import OperatorInterrupted, operator_lock


class OperatorLockTests(unittest.TestCase):
    def test_hup_int_and_term_exit_nonzero_path_before_releasing_lock(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "operator.lock"
            for selected in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
                with self.subTest(signal=selected):
                    with (
                        self.assertRaises(OperatorInterrupted) as captured,
                        operator_lock(path),
                    ):
                        os.kill(os.getpid(), selected)
                    self.assertEqual(selected, captured.exception.signal_number)
                    with operator_lock(path):
                        pass


if __name__ == "__main__":
    unittest.main()
