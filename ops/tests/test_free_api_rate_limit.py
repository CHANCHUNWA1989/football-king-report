"""The global league directory and fixture collector share one quota window."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from free_api_rate_limit import reserve


class FreeQuotaTests(unittest.TestCase):
    def test_shared_budget_waits_for_oldest_call_without_exceeding_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sportsdb-budget.json"
            now = [1000.0]
            def clock():
                return now[0]
            def sleeper(seconds):
                self.assertGreater(seconds, 0)
                now[0] += seconds
            for _ in range(3):
                self.assertTrue(reserve(target, clock=clock, sleeper=sleeper,
                                        limit=3, window=62))
            early = json.loads(target.read_text())
            self.assertEqual(len(early), 3)
            reserve(target, clock=clock, sleeper=sleeper,
                    limit=3, window=62)
            after = json.loads(target.read_text())
            self.assertLessEqual(len(after), 3)
            self.assertGreaterEqual(now[0], 1062.0)

    def test_invalid_or_corrupt_ledger_is_recreated_without_inventing_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "budget.json"
            target.write_text("corrupt-json", encoding="utf-8")
            reserve(target, clock=lambda: 2000.0)
            data = json.loads(target.read_text())
            self.assertEqual(data, [2000.0])

    def test_unsafe_limits_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                reserve(Path(tmp)/"bad.json", limit=40)
            with self.assertRaises(ValueError):
                reserve(Path(tmp)/"bad.json", limit=0)

    def test_absent_ledger_is_explicit_unmetered_test_mode(self):
        self.assertFalse(reserve(None))


if __name__ == "__main__":
    unittest.main()
