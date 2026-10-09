import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from forward_settlement_audit import audit

NOW=datetime(2026,10,9,14,tzinfo=timezone.utc)
def record(event="e1",p=0.8,y=1,baseline=0.6):
    return {"event_id":event,"model_version":"v1","market":"h2h_home",
            "prediction_created_at_utc":"2026-10-09T09:00:00Z",
            "source_snapshot_at_utc":"2026-10-09T08:59:00Z",
            "kickoff_utc":"2026-10-09T10:00:00Z",
            "settled_at_utc":"2026-10-09T12:00:00Z",
            "immutable_prediction_record":True,
            "independent_settlement_verified":True,
            "historical_backfill":False,
            "predicted_probability":p,"settled_binary_outcome":y,
            "market_baseline_probability":baseline}

class ForwardSettlementTests(unittest.TestCase):
    def test_empty_data_is_hold(self):
        r=audit([],now=NOW)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["independent_forward_samples"],0)
        self.assertIsNone(r["brier_score"])

    def test_brier_compares_with_market_not_just_win_rate(self):
        r=audit([record()],now=NOW)
        self.assertEqual(r["brier_score"],0.04)
        self.assertEqual(r["market_baseline_brier_score"],0.16)
        self.assertEqual(r["brier_improvement_vs_market"],0.12)
        self.assertFalse(r["model_promotion_allowed"])

    def test_future_source_leakage_rejected(self):
        d=record()
        d["source_snapshot_at_utc"]="2026-10-09T09:10:00Z"
        self.assertEqual(audit([d],now=NOW)["independent_forward_samples"],0)

    def test_prediction_after_kickoff_rejected(self):
        d=record()
        d["prediction_created_at_utc"]="2026-10-09T11:00:00Z"
        self.assertEqual(audit([d],now=NOW)["reject_reasons"]["LOOKAHEAD_OR_INVALID_CHRONOLOGY"],1)

    def test_historical_backfill_rejected(self):
        d=record()
        d["historical_backfill"]=True
        self.assertEqual(audit([d],now=NOW)["reject_reasons"]["BACKFILL_NOT_FORWARD"],1)

    def test_no_independent_settlement_rejected(self):
        d=record()
        d["independent_settlement_verified"]=False
        self.assertEqual(audit([d],now=NOW)["reject_reasons"]["UNVERIFIED_SETTLEMENT"],1)

    def test_no_immutable_proof_rejected(self):
        d=record()
        d["immutable_prediction_record"]=False
        self.assertEqual(audit([d],now=NOW)["reject_reasons"]["NO_IMMUTABLE_FORWARD_PROOF"],1)

    def test_duplicate_event_model_market_rejected(self):
        r=audit([record(),record()],now=NOW)
        self.assertEqual(r["candidate_forward_samples"],1)
        self.assertEqual(r["reject_reasons"]["DUPLICATE_EVENT_MODEL_MARKET"],1)

    def test_invalid_bool_probability_rejected(self):
        r=audit([record(p=True)],now=NOW)
        self.assertEqual(r["reject_reasons"]["INVALID_PROBABILITY"],1)

    def test_invalid_bool_outcome_rejected(self):
        r=audit([record(y=True)],now=NOW)
        self.assertEqual(r["reject_reasons"]["INVALID_BINARY_SETTLEMENT"],1)

    def test_300_self_claimed_samples_still_cannot_promote(self):
        rows=[record(event=str(i)) for i in range(300)]
        r=audit(rows,now=NOW)
        self.assertTrue(r["candidate_sample_count_threshold_met"])
        self.assertFalse(r["model_promotion_allowed"])
        self.assertFalse(r["calibration_verified"])
        self.assertFalse(r["statistical_significance_verified"])

    def test_naive_timestamp_rejected(self):
        d=record()
        d["settled_at_utc"]="2026-10-09T12:00:00"
        self.assertEqual(audit([d],now=NOW)["independent_forward_samples"],0)

    def test_future_settlement_rejected(self):
        d=record()
        d["settled_at_utc"]="2026-10-10T12:00:00Z"
        self.assertEqual(audit([d],now=NOW)["independent_forward_samples"],0)

if __name__=="__main__":
    unittest.main()
