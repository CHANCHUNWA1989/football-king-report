import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from six_capability_research import provider_failover, quota_health
from forward_settlement_audit import audit

NOW=datetime(2026,10,9,14,tzinfo=timezone.utc)
def observation(name="main",**changes):
    data={"event_id":"match-1","league":"epl","provider":name,
          "provider_authenticated":True,
          "observed_at_utc":"2026-10-09T13:59:40Z"}
    data.update(changes)
    return data

class ProviderFailureTests(unittest.TestCase):
    def select(self, rows):
        return provider_failover(rows,event_id="match-1",league="epl",now=NOW)

    def test_rate_limit_chooses_independent_backup(self):
        report=self.select([observation("main",http_status=429),
                            observation("backup",http_status=200)])
        self.assertEqual(report["selected_provider"],"backup")
        self.assertEqual(report["rejections"]["RATE_LIMITED"],1)
        self.assertFalse(report["real_network_failover_verified"])

    def test_all_transport_errors_hold(self):
        report=self.select([observation("main",transport_error="timeout"),
                            observation("backup",transport_error="connection")])
        self.assertEqual(report["status"],"HOLD")
        self.assertEqual(report["rejections"]["TRANSPORT_ERROR"],2)

    def test_server_failure_rejected(self):
        self.assertEqual(self.select([observation(http_status=500)])["status"],"HOLD")

    def test_depleted_quota_rejected(self):
        self.assertEqual(self.select([observation(quota_remaining=0)])["status"],"HOLD")

    def test_bad_quota_rejected(self):
        self.assertEqual(self.select([observation(quota_remaining=-1)])["status"],"HOLD")

    def test_missing_evidence_never_authenticated(self):
        report=self.select([observation()])
        self.assertTrue(report["provider_authentication_self_attested"])
        self.assertFalse(report["real_network_failover_verified"])

    def test_quota_empty_is_hold(self):
        self.assertEqual(quota_health([],now=NOW)["status"],"HOLD")

class ForwardClaimTests(unittest.TestCase):
    def test_large_claimed_batch_not_independently_counted(self):
        template=dict(model_version="v",market="h2h",
          prediction_created_at_utc="2026-10-09T09:00:00Z",
          source_snapshot_at_utc="2026-10-09T08:00:00Z",
          kickoff_utc="2026-10-09T10:00:00Z",
          settled_at_utc="2026-10-09T12:00:00Z",
          immutable_prediction_record=True,independent_settlement_verified=True,
          historical_backfill=False,predicted_probability=0.7,
          settled_binary_outcome=1,market_baseline_probability=0.6)
        claimed=[dict(template,event_id=str(i)) for i in range(300)]
        result=audit(claimed,now=NOW)
        self.assertEqual(result["candidate_forward_samples"],300)
        self.assertEqual(result["independent_forward_samples"],0)
        self.assertEqual(result["authenticated_forward_samples"],0)
        self.assertFalse(result["sample_count_threshold_met"])
        self.assertTrue(result["candidate_sample_count_threshold_met"])
        self.assertTrue(result["candidate_metrics_only"])
        self.assertFalse(result["model_promotion_allowed"])

if __name__=="__main__":
    unittest.main()
