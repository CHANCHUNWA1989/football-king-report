import copy
import unittest
from test_production_gate import research_evidence
from archived_error_attribution import build,inventory,summary
class ErrorAttributionTests(unittest.TestCase):
    def test_partitions_conserve_and_leave_inputs_unchanged(self):
        doc=research_evidence()
        original=copy.deepcopy(doc)
        r=build(doc)
        self.assertEqual(doc,original)
        for group in r["partitions"].values():
            self.assertEqual(sum(v["n"] for v in group.values()),300)
            self.assertAlmostEqual(sum(v["model_minus_market_log_loss_sum"] for v in group.values()),r["pooled"]["model_minus_market_log_loss_sum"])
        self.assertEqual(r["new_forward_credit"],0)
        self.assertIsNone(r["selected_model"])
    def test_identity_presence_is_not_admission(self):
        rows=[{"forecast_event_id":"x","source_fixture_identity":{"provider":"test","match_id":"123"},"source_fixture_identity_status":"UNAUTHENTICATED","eligible_for_model_scoring":False},{}]
        r=inventory(rows)
        self.assertEqual(r["metadata_counts"]["both_identity_fields_present"],1)
        self.assertEqual(r["overlapping_missing_requirements"]["FORECAST_EVENT_ID_MISSING"],1)
        self.assertEqual(r["authenticated_forward_samples"],0)
        self.assertFalse(r["authenticated_admission_implemented"])
    def test_empty_group_and_maturity(self):
        self.assertIsNone(summary([])["model_log_loss"])
        doc=research_evidence();doc["checked_utc"]=doc["samples"][-1]["kickoff_utc"]
        with self.assertRaises(ValueError):build(doc)
    def test_duplicate_rejected(self):
        doc=research_evidence()
        doc["samples"][1]["key"]=doc["samples"][0]["key"]
        with self.assertRaises(ValueError):build(doc)
