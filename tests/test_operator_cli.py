from __future__ import annotations

import contextlib
import io
import unittest

from group_llm_agent.operator_cli import main


class OperatorCliTests(unittest.TestCase):
    def test_online_expression_metrics_command_is_not_available(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            main(["expression-metrics"])

        self.assertEqual(2, raised.exception.code)
        self.assertIn("invalid choice", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
