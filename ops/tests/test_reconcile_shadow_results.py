import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reconcile_shadow_results import reconcile

FORECAST = {
    "event_id": "e1",
    "forecast_utc": "2026-10-14T12:00:00Z",
    "kickoff_utc": "2026-10-14T15:00:00Z",
    "p_home": 0.6, "p_draw": 0.25, "p_away": 0.15,
}
RESULT = {
    "event_id": "e1",
    "kickoff_utc": "2026-10-14T15:00:00Z",
    "settled_utc": "2026-10-14T18:00:00Z",
    "result": "H", "source": "independent-source",
    "independently_verified": True,
}


class ReconcileTests(unittest.TestCase):
    def test_valid_pair_remains_research_only(self):
        r = reconcile([FORECAST], [RESULT])
        self.assertEqual(r["accepted"], 1)
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertEqual(r["independent_result_proof"], "DECLARED_NOT_AUDITED")

    def test_unverified_result_excluded(self):
        r = reconcile([FORECAST], [{**RESULT, "independently_verified": False}])
        self.assertEqual(r["accepted"], 0)
        self.assertEqual(r["reconciliation_reject_reasons"]["UNVERIFIED_RESULT"], 1)

    def test_duplicate_forecasts_all_excluded(self):
        r = reconcile([FORECAST, FORECAST], [RESULT])
        self.assertEqual(r["accepted"], 0)
        self.assertEqual(r["reconciliation_reject_reasons"]["DUPLICATE_FORECAST"], 2)

    def test_duplicate_results_excluded(self):
        r = reconcile([FORECAST], [RESULT, RESULT])
        self.assertEqual(r["accepted"], 0)
        self.assertEqual(r["reconciliation_reject_reasons"]["DUPLICATE_RESULT"], 1)

    def test_kickoff_mismatch_excluded(self):
        r = reconcile([FORECAST], [{**RESULT, "kickoff_utc": "2026-10-14T16:00:00Z"}])
        self.assertEqual(r["accepted"], 0)


if __name__ == "__main__":
    unittest.main()
