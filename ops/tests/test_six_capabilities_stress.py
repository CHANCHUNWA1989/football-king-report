import sys
import unittest
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from six_capability_research import calibration,quota_health,provider_failover,live_stats,reconcile_settlement,ocr_adapter
NOW=datetime(2026,10,9,14,tzinfo=timezone.utc)

class CapabilityStressTests(unittest.TestCase):
    def test_calibration_large_batch(self):
        rows=[{"probability":0.5,"outcome":i%2} for i in range(50000)]
        result=calibration(rows)
        self.assertEqual(result["samples"],50000)
        self.assertEqual(result["brier"],0.25)
        self.assertFalse(result["calibration_verified"])

    def test_duplicate_settlement(self):
        p=[{"event_id":"a","market":"h2h","prediction_created_at_utc":"2026-10-09T08:00:00Z","kickoff_utc":"2026-10-09T10:00:00Z"}]
        s=[{"event_id":"a","market":"h2h","outcome":1,"settled_at_utc":"2026-10-09T12:00:00Z"}]
        self.assertEqual(reconcile_settlement(p,s+s)["matched_count"],0)

    def test_provider_failover_identity(self):
        rows=[{"event_id":"wrong","league":"epl","provider":"p","provider_authenticated":True,"observed_at_utc":"2026-10-09T13:59:00Z"}]
        self.assertEqual(provider_failover(rows,event_id="right",league="epl",now=NOW)["status"],"HOLD")

    def test_missing_stats_hold(self):
        self.assertEqual(live_stats([],event_id="a",now=NOW)["status"],"HOLD")

    def test_empty_ocr_rejected(self):
        with self.assertRaises(ValueError):
            ocr_adapter(b"",{},now=NOW)

    def test_missing_quota_holds(self):
        self.assertEqual(quota_health([],now=NOW)["status"],"HOLD")

if __name__=="__main__":
    unittest.main()
