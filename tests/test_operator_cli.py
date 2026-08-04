from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from helpers import temporary_database

from group_llm_agent.operator_cli import main


class OperatorCliTests(unittest.TestCase):
    def test_expression_metrics_is_aggregate_only_and_reports_insufficient_data(self) -> None:
        with temporary_database() as database:
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "expression-metrics",
                        "--database",
                        str(database.path),
                        "--bot-user-id",
                        "bot-1",
                        "--persona-version",
                        "lezhi-v2.0",
                        "--persona-digest",
                        "p" * 64,
                        "--catalog-version",
                        "lezhi-expression-v0.3",
                        "--catalog-digest",
                        "c" * 64,
                    ]
                )
            rendered = output.getvalue()
            self.assertEqual(0, exit_code)
            self.assertIn("metrics_status=insufficient_data", rendered)
            self.assertIn("sample_count=0", rendered)
            self.assertIn("sticker_bearing_rate=unavailable", rendered)
            self.assertNotIn("message", rendered)
            self.assertNotIn("member", rendered)


if __name__ == "__main__":
    unittest.main()
