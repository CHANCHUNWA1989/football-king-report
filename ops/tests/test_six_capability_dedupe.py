import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from six_capability_research import provider_failover, reconcile_settlement

NOW=datetime(2026,10,9,14,tzinfo=timezone.utc)

class DeduplicationTests(unittest.TestCase):
    def test_same_provider_is_not_fallback(self):
        base=dict(event_id="e",league="epl",provider="source_a",
                  provider_authenticated=True,observed_at_utc="2026-10-09T13:59:30Z")
        result=provider_failover([base,dict(base)],event_id="e",league="epl",now=NOW)
        self.assertEqual(result["distinct_provider_count"],1)
        self.assertEqual(result["fallback_count"],0)
        self.assertEqual(result["rejections"]["DUPLICATE_PROVIDER_OBSERVATION"],1)

    def test_distinct_provider_is_fallback(self):
        first=dict(event_id="e",league="epl",provider="source_a",
                   provider_authenticated=True,observed_at_utc="2026-10-09T13:59:30Z")
        other=dict(first,provider="source_b")
        result=provider_failover([first,other],event_id="e",league="epl",now=NOW)
        self.assertEqual(result["fallback_count"],1)

    def test_repeated_prediction_not_double_counted(self):
        prediction=dict(event_id="e",market="h2h",
                        prediction_created_at_utc="2026-10-09T09:00:00Z",
                        kickoff_utc="2026-10-09T10:00:00Z")
        result=dict(event_id="e",market="h2h",outcome=1,
                    settled_at_utc="2026-10-09T12:00:00Z")
        check=reconcile_settlement([prediction,dict(prediction)],[result])
        self.assertEqual(check["matched_count"],0)
        self.assertEqual(check["duplicate_prediction_keys"],1)
        self.assertFalse(check["independent_settlement_verified"])

    def test_single_prediction_still_reconciles(self):
        prediction=dict(event_id="e",market="h2h",
                        prediction_created_at_utc="2026-10-09T09:00:00Z",
                        kickoff_utc="2026-10-09T10:00:00Z")
        outcome=dict(event_id="e",market="h2h",outcome=1,
                     settled_at_utc="2026-10-09T12:00:00Z")
        check=reconcile_settlement([prediction],[outcome])
        self.assertEqual(check["matched_count"],1)
        self.assertEqual(check["duplicate_prediction_keys"],0)
        self.assertFalse(check["independent_settlement_verified"])

if __name__=="__main__":
    unittest.main()
