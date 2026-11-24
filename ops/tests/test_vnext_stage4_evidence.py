"""Safety-first tests. All vendor records are synthetic, no external source API."""
import copy
import hashlib
import json
import unittest
from ops.vnext_stage4_evidence import (
    audit_result_overlap, audit_private_bundle, strict_json_bytes)

NOW = "2026-11-22T14:00:00Z"


def scores():
    left = {"source_id": "public-A", "captured_utc": "2026-11-20T08:00:00Z",
            "upstream_declared": "lineage-unknown-a", "rows": [
        {"date": "2026-11-08", "home": "FC Internazionale Milano",
         "away": "AC Monza", "home_goals": 2, "away_goals": 0, "period": "FT90"}]}
    right = {"source_id": "public-B", "captured_utc": "2026-11-20T08:00:00Z",
             "upstream_declared": "lineage-unknown-b", "rows": [
        {"date": "2026-11-08", "home": "Internazionale",
         "away": "Monza", "home_goals": 2, "away_goals": 0, "period": "FT90"}]}
    return left, right


def private():
    fx = {"fixture_id": "match-1", "kickoff_utc": "2026-11-23T03:00:00Z", "league": "seriea"}
    xg = {"provider": "test", "matches": [{"provider_match_id": "old-1",
        "kickoff_utc": "2026-10-20T12:00:00Z",
        "published_utc": "2026-10-21T12:00:00Z", "home_xg": 1.5, "away_xg": 0.8}]}
    data = {"xg": json.dumps(xg).encode(), "forecast": b'{"model":"test"}',
            "odds": b'{"markets":[]}'}
    times = {"xg": "2026-11-22T22:00:00Z",
             "forecast": "2026-11-22T23:00:00Z", "odds": "2026-11-22T23:02:00Z"}
    receipts = {k: {"kind": k, "fixture_id": "match-1",
        "observed_utc": times[k], "captured_utc": times[k],
        "source_id": "provider-"+k, "provider_native_id": "native-"+k,
        "sha256": hashlib.sha256(data[k]).hexdigest(),
        "license_reference": "private-review-pending"} for k in data}
    return fx, receipts, data


class ResultTests(unittest.TestCase):
    def test_match_is_not_independence(self):
        a, b = scores(); result = audit_result_overlap(a,b,as_of_utc=NOW)
        self.assertEqual(result["identical_scores"],1)
        self.assertEqual(result["independently_verified_results"],0)
        self.assertEqual(result["status"],"HOLD")

    def test_wrong_score(self):
        a,b=scores();b["rows"][0]["away_goals"]=2
        result=audit_result_overlap(a,b,as_of_utc=NOW)
        self.assertEqual(result["conflicting_scores"],1)
        self.assertIn("CONFLICTING_FT90_RESULTS",result["blockers"])

    def test_upstream_claim_is_not_verified(self):
        a,b=scores();b["upstream_declared"]=a["upstream_declared"]
        result=audit_result_overlap(a,b,as_of_utc=NOW)
        self.assertIn("SHARED_UPSTREAM_DECLARED",result["blockers"])
        self.assertFalse(result["independent_upstreams_proven"])

    def test_duplicate_match_rejected(self):
        a,b=scores();a["rows"].append(copy.deepcopy(a["rows"][0]))
        result=audit_result_overlap(a,b,as_of_utc=NOW)
        self.assertIn("INVALID_OR_UNTRUSTED_RESULT_SOURCE",result["blockers"])

    def test_no_future_or_same_day_results(self):
        a,b=scores();a["rows"][0]["date"]="2026-11-22"
        result=audit_result_overlap(a,b,as_of_utc=NOW)
        self.assertIn("INVALID_OR_UNTRUSTED_RESULT_SOURCE",result["blockers"])

    def test_reject_fake_ft(self):
        a,b=scores();a["rows"][0]["period"]="AET"
        result=audit_result_overlap(a,b,as_of_utc=NOW)
        self.assertIn("INVALID_OR_UNTRUSTED_RESULT_SOURCE",result["blockers"])

    def test_result_before_capture_date_only(self):
        a,b=scores();a["captured_utc"]="2026-11-07T23:00:00Z"
        result=audit_result_overlap(a,b,as_of_utc=NOW)
        self.assertIn("INVALID_OR_UNTRUSTED_RESULT_SOURCE",result["blockers"])

    def test_does_not_echo_team_names(self):
        a,b=scores();result=audit_result_overlap(a,b,as_of_utc=NOW)
        self.assertNotIn("Internazionale",json.dumps(result))

    def test_bad_capture_future(self):
        a,b=scores();a["captured_utc"]="2026-11-23T00:00:00Z"
        result=audit_result_overlap(a,b,as_of_utc=NOW)
        self.assertIn("INVALID_OR_UNTRUSTED_RESULT_SOURCE",result["blockers"])


class PrivateTests(unittest.TestCase):
    def test_all_locally_valid_never_ready(self):
        fx,r,d=private();v=audit_private_bundle(fx,r,d)
        self.assertEqual(v["artifacts_locally_valid"],3)
        self.assertEqual(v["xg_matches_validated"],1)
        self.assertEqual(v["status"],"HOLD")
        self.assertFalse(v["verified_positive_ev"])
        self.assertIsNone(v["recommended_stakes"])

    def test_bad_digest_blocks(self):
        fx,r,d=private();d["xg"]=b'{"bad":true}'
        self.assertIn("PRIVATE_ARTIFACT_VALIDATION_FAILED",audit_private_bundle(fx,r,d)["blockers"])

    def test_stale_odds_blocks(self):
        fx,r,d=private();r["odds"]["observed_utc"]="2026-11-22T22:50:00Z"
        self.assertIn("PRIVATE_ARTIFACT_VALIDATION_FAILED",audit_private_bundle(fx,r,d)["blockers"])

    def test_future_odds_blocks(self):
        fx,r,d=private();r["odds"]["captured_utc"]="2026-11-23T03:01:00Z"
        self.assertIn("PRIVATE_ARTIFACT_VALIDATION_FAILED",audit_private_bundle(fx,r,d)["blockers"])

    def test_forecast_after_odds_rejected(self):
        fx,r,d=private();r["forecast"]["observed_utc"]="2026-11-23T00:00:00Z"
        r["forecast"]["captured_utc"]="2026-11-23T00:00:00Z"
        self.assertIn("PRIVATE_ARTIFACT_VALIDATION_FAILED",audit_private_bundle(fx,r,d)["blockers"])

    def test_future_xg_history_rejected(self):
        fx,r,d=private();xg=json.loads(d["xg"]);xg["matches"][0]["kickoff_utc"]="2026-11-25T00:00:00Z"
        d["xg"]=json.dumps(xg).encode();r["xg"]["sha256"]=hashlib.sha256(d["xg"]).hexdigest()
        self.assertIn("PRIVATE_ARTIFACT_VALIDATION_FAILED",audit_private_bundle(fx,r,d)["blockers"])

    def test_xg_published_after_capture_rejected(self):
        fx,r,d=private();xg=json.loads(d["xg"]);xg["matches"][0]["published_utc"]="2026-11-22T23:00:00Z"
        d["xg"]=json.dumps(xg).encode();r["xg"]["sha256"]=hashlib.sha256(d["xg"]).hexdigest()
        self.assertIn("PRIVATE_ARTIFACT_VALIDATION_FAILED",audit_private_bundle(fx,r,d)["blockers"])

    def test_nan_xg_rejected(self):
        fx,r,d=private();xg=json.loads(d["xg"]);xg["matches"][0]["home_xg"]=float("nan")
        d["xg"]=json.dumps(xg).encode();r["xg"]["sha256"]=hashlib.sha256(d["xg"]).hexdigest()
        self.assertIn("PRIVATE_ARTIFACT_VALIDATION_FAILED",audit_private_bundle(fx,r,d)["blockers"])

    def test_duplicate_json_rejected(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_JSON_MEMBER"):
            strict_json_bytes(b'{"provider":"a","provider":"b"}')

    def test_payload_does_not_leak(self):
        fx,r,d=private();d["odds"]=b'{"private":"Bookmaker-Top-Secret-Odds"}'
        r["odds"]["sha256"]=hashlib.sha256(d["odds"]).hexdigest()
        result=audit_private_bundle(fx,r,d)
        self.assertNotIn("Bookmaker-Top-Secret",json.dumps(result))

    def test_missing_license_reference(self):
        fx,r,d=private();r["xg"]["license_reference"]=""
        self.assertIn("PRIVATE_ARTIFACT_VALIDATION_FAILED",audit_private_bundle(fx,r,d)["blockers"])

    def test_duplicate_xg_identity_rejected(self):
        fx,r,d=private();xg=json.loads(d["xg"]);xg["matches"].append(xg["matches"][0])
        d["xg"]=json.dumps(xg).encode();r["xg"]["sha256"]=hashlib.sha256(d["xg"]).hexdigest()
        self.assertIn("PRIVATE_ARTIFACT_VALIDATION_FAILED",audit_private_bundle(fx,r,d)["blockers"])

    def test_source_not_proven_by_receipts(self):
        fx,r,d=private();r["odds"]["license_reference"]="I CERTIFY LICENSE"
        v=audit_private_bundle(fx,r,d)
        self.assertIn("LICENSE_AND_CHAIN_OF_CUSTODY_EXTERNAL_REVIEW_REQUIRED",v["blockers"])


if __name__ == "__main__": unittest.main()
