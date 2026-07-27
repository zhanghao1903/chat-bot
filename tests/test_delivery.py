from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from group_llm_agent.delivery import SQLiteDeliveryLedger


class DeliveryLedgerTests(unittest.TestCase):
    def test_claim_is_unique_and_schema_contains_no_message_text(self) -> None:
        with TemporaryDirectory() as tmpdir:
            ledger = SQLiteDeliveryLedger(Path(tmpdir) / "ledger.sqlite3")
            ledger.initialize()

            first = ledger.claim(
                chat_id="-1001",
                message_id="10",
                action_kind="fixed_reply",
            )
            duplicate = ledger.claim(
                chat_id="-1001",
                message_id="10",
                action_kind="fixed_reply",
            )

            self.assertIsNotNone(first)
            self.assertIsNone(duplicate)
            columns = {
                row["name"]
                for row in ledger.connection.execute(
                    "PRAGMA table_info(delivery_ledger)"
                ).fetchall()
            }
            self.assertNotIn("text", columns)
            self.assertNotIn("payload", columns)
            ledger.close()


if __name__ == "__main__":
    unittest.main()
