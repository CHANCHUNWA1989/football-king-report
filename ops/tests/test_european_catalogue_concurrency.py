"""Concurrency stress tests for European catalogue reconciliation.

Offline-only: never sends provider requests or spends API credits.
"""
import unittest
from concurrent.futures import ThreadPoolExecutor

from ops.european_sports_catalogue import reconcile


class TestEuropeanCatalogueConcurrency(unittest.TestCase):
    def test_parallel_catalogue_reconciliation_is_deterministic_and_safe(self):
        sports = [{"key": "noise_" + str(i), "active": bool(i % 2)}
                  for i in range(2000)]
        sports.append({"key": "soccer_epl", "active": True})

        def run(_):
            result = reconcile(sports)
            epl = next(row for row in result["results"]
                       if row["competition"] == "premier-league")
            return (result["status"], result["production_recommendations"],
                    epl["catalogue_status"], len(result["results"]))

        with ThreadPoolExecutor(max_workers=32) as pool:
            results = list(pool.map(run, range(1000)))
        self.assertEqual(len(results), 1000)
        self.assertEqual(set(results), {("HOLD", "DISABLED", "ACTIVE_CANDIDATE", 8)})

    def test_parallel_duplicate_and_valid_requests_do_not_cross_contaminate(self):
        valid = [{"key": "soccer_epl", "active": True}]
        duplicate = [{"key": "soccer_epl", "active": True}] * 3

        def run(i):
            rows = valid if i % 2 == 0 else duplicate
            report = reconcile(rows)
            epl = next(x for x in report["results"]
                       if x["competition"] == "premier-league")
            return report["status"], epl["catalogue_status"]

        with ThreadPoolExecutor(max_workers=32) as pool:
            results = list(pool.map(run, range(1000)))
        for i, result in enumerate(results):
            self.assertEqual(result, ("HOLD", "ACTIVE_CANDIDATE" if i % 2 == 0
                                      else "NOT_VERIFIED"))


if __name__ == "__main__":
    unittest.main()
