import unittest
from ops.research_external_evidence_gate_v1 import inspect_external_evidence

def source(name,upstream):
    return {"url":"https://example.org/"+name,"publisher":name,"upstream":upstream}

def candidate():
    return {"fixture_key":"league|home|away|2026-11-28",
            "forecast_sha256":"a"*64,"recorded_forecast_at":"2026-11-28T12:00:00+00:00",
            "forecast_archive":{**source("forecast-archive","archive-provider"),"sha256":"a"*64,"captured_at":"2026-11-28T11:59:00Z","artifact_kind":"immutable_object","receipt_locator":"archive://sample/receipt"},
            "kickoff_observations":[
                {**source("kickoff-a","feed-a"),"observed_at":"2026-11-28T11:00:00Z","claimed_kickoff_at":"2026-11-28T15:00:00Z"},
                {**source("kickoff-b","feed-b"),"observed_at":"2026-11-28T11:05:00Z","claimed_kickoff_at":"2026-11-28T15:00:00Z"}],
            "publisher_provenance":[
                {**source("forecast-a","feed-a"),"captured_at":"2026-11-28T11:00:00Z"},
                {**source("forecast-b","feed-b"),"captured_at":"2026-11-28T11:05:00Z"}],
            "market_snapshot":{**source("market","feed-market"),"captured_at":"2026-11-28T11:50:00Z"}}

class ExternalEvidenceGateTests(unittest.TestCase):
    def test_complete_inventory_still_hold(self):
        result=inspect_external_evidence(candidate())
        self.assertTrue(result["inventory_complete"])
        self.assertTrue(result["distinct_upstream_claims"])
        self.assertFalse(result["independence_authenticated"])
        self.assertEqual(result["authenticated_samples"],0)
        self.assertFalse(result["model_promotion_allowed"])
    def test_mirrored_upstream_never_authenticated(self):
        item=candidate()
        item["publisher_provenance"][1]["upstream"]="feed-a"
        result=inspect_external_evidence(item)
        self.assertFalse(result["distinct_upstream_claims"])
        self.assertEqual(result["status"],"HOLD")
    def test_market_after_forecast_rejected(self):
        item=candidate()
        item["market_snapshot"]["captured_at"]="2026-11-28T12:01:00Z"
        with self.assertRaises(ValueError):inspect_external_evidence(item)
    def test_naive_timestamp_rejected(self):
        item=candidate()
        item["recorded_forecast_at"]="2026-11-28T12:00:00"
        with self.assertRaises(ValueError):inspect_external_evidence(item)
    def test_forecast_after_claimed_kickoff_rejected(self):
        item=candidate()
        item["kickoff_observations"][0]["claimed_kickoff_at"]="2026-11-28T11:59:00Z"
        with self.assertRaises(ValueError):inspect_external_evidence(item)
    def test_missing_observation_rejected(self):
        item=candidate()
        item["kickoff_observations"].pop()
        with self.assertRaises(ValueError):inspect_external_evidence(item)
    def test_kickoff_observation_after_forecast_rejected(self):
        item=candidate()
        item["kickoff_observations"][0]["observed_at"]="2026-11-28T12:01:00Z"
        with self.assertRaises(ValueError):inspect_external_evidence(item)
    def test_provenance_after_forecast_rejected(self):
        item=candidate()
        item["publisher_provenance"][1]["captured_at"]="2026-11-28T12:01:00Z"
        with self.assertRaises(ValueError):inspect_external_evidence(item)
    def test_conflicting_kickoff_observations_rejected(self):
        item=candidate()
        item["kickoff_observations"][1]["claimed_kickoff_at"]="2026-11-28T16:00:00Z"
        with self.assertRaises(ValueError):inspect_external_evidence(item)
    def test_cross_group_upstream_overlap_is_reported_not_authenticated(self):
        result=inspect_external_evidence(candidate())
        self.assertEqual(result["cross_group_upstream_overlap"],["feed-a","feed-b"])
        self.assertEqual(result["kickoff_upstream_count"],2)
        self.assertEqual(result["provenance_upstream_count"],2)
        self.assertFalse(result["independence_authenticated"])
        self.assertFalse(result["model_promotion_allowed"])
    def test_distinct_groups_without_overlap_still_not_authenticated(self):
        item=candidate()
        item["publisher_provenance"][0]["upstream"]="other-a"
        item["publisher_provenance"][1]["upstream"]="other-b"
        result=inspect_external_evidence(item)
        self.assertEqual(result["cross_group_upstream_overlap"],[])
        self.assertTrue(result["distinct_upstream_claims"])
        self.assertFalse(result["independence_authenticated"])
    def test_upstream_case_and_whitespace_aliases_collapsed(self):
        item=candidate()
        item["kickoff_observations"][1]["upstream"]=" FEED- A "
        item["publisher_provenance"][1]["upstream"]="  Feed- A  "
        item["kickoff_observations"][0]["upstream"]="feed- a"
        item["publisher_provenance"][0]["upstream"]="feed- a"
        result=inspect_external_evidence(item)
        self.assertEqual(result["kickoff_upstream_count"],1)
        self.assertEqual(result["provenance_upstream_count"],1)
        self.assertFalse(result["distinct_upstream_claims"])
        self.assertFalse(result["independence_authenticated"])
    def test_empty_normalized_upstream_rejected(self):
        item=candidate()
        item["market_snapshot"]["upstream"]="   "
        with self.assertRaises(ValueError):inspect_external_evidence(item)
    def test_forecast_archive_missing_rejected(self):
        item=candidate()
        del item["forecast_archive"]
        with self.assertRaises(ValueError):inspect_external_evidence(item)
    def test_forecast_archive_digest_mismatch_rejected(self):
        item=candidate()
        item["forecast_archive"]["sha256"]="b"*64
        with self.assertRaises(ValueError):inspect_external_evidence(item)
    def test_forecast_archive_late_capture_rejected(self):
        item=candidate()
        item["forecast_archive"]["captured_at"]="2026-11-28T12:00:01Z"
        with self.assertRaises(ValueError):inspect_external_evidence(item)
    def test_forecast_archive_claim_not_authenticated(self):
        result=inspect_external_evidence(candidate())
        self.assertTrue(result["forecast_archive_claim_present"])
        self.assertFalse(result["forecast_archive_authenticated"])
        self.assertEqual(result["authenticated_samples"],0)
    def test_archive_receipt_locator_required(self):
        item=candidate()
        del item["forecast_archive"]["receipt_locator"]
        with self.assertRaises(ValueError):inspect_external_evidence(item)
    def test_archive_artifact_kind_required(self):
        item=candidate()
        item["forecast_archive"]["artifact_kind"]="unverified_link"
        with self.assertRaises(ValueError):inspect_external_evidence(item)
    def test_receipt_claim_does_not_authenticate(self):
        result=inspect_external_evidence(candidate())
        self.assertTrue(result["archive_receipt_claim_present"])
        self.assertFalse(result["forecast_archive_authenticated"])
    def test_http_source_rejected(self):
        item=candidate()
        item["market_snapshot"]["url"]="http://example.org/market"
        with self.assertRaises(ValueError):inspect_external_evidence(item)

if __name__=="__main__":unittest.main()
