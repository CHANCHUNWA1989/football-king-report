"""Synthetic zero-network tests for caller-supplied in-play source claim bytes."""
import copy
from datetime import datetime, timezone, timedelta
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inplay_two_source_byte_packet import audit

NOW=datetime(2026,11,23,0,50,20,tzinfo=timezone.utc)


def fixture():
    return {
        "fixture_id":"synthetic_event_123","league_id":"argentina_lpf",
        "home_id":"synthetic_home","away_id":"synthetic_away",
        "kickoff_utc":"2026-11-23T00:00:00Z",
        "identity_sealed_utc":"2026-11-22T23:30:00Z",
        "decision_utc":"2026-11-23T00:50:10Z",
    }


def source(provider):
    host={"fotmob":"www.fotmob.com","sofascore":"www.sofascore.com"}[provider]
    return {
        "schema":"football-king-untrusted-inplay-source-claim-v1",
        "provider":provider,
        "provider_event_id":provider+"_synthetic_700",
        "source_url":"https://"+host+"/football/matches/synthetic_700",
        "fixture_id":"synthetic_event_123",
        "league_id":"argentina_lpf","home_id":"synthetic_home",
        "away_id":"synthetic_away",
        "kickoff_utc":"2026-11-23T00:00:00Z",
        "source_updated_utc":"2026-11-23T00:49:50Z",
        "captured_utc":"2026-11-23T00:50:01Z",
        "received_utc":"2026-11-23T00:50:03Z",
        "match_status":"HALF_TIME",
        "elapsed_regulation_minute":45,
        "home_goals":1,"away_goals":1,
        "home_red_cards":0,"away_red_cards":0,
        "var_review_pending":False,
    }


def raw(item):
    return json.dumps(item,sort_keys=True,separators=(",",":"),allow_nan=False).encode()


def pair():
    return [raw(source("fotmob")),raw(source("sofascore"))]


class InPlayTwoSourceBytePacketTests(unittest.TestCase):
    def test_two_claims_match_but_cannot_certify_source_or_prediction(self):
        inputs=pair()
        original=copy.deepcopy(inputs)
        result=audit(fixture(),inputs,now=NOW)
        self.assertEqual(result["status"],"RESEARCH_ONLY")
        self.assertTrue(result["two_distinct_claimed_publishers_agree"])
        self.assertEqual(result["claimed_publisher_count"],2)
        self.assertEqual(result["production_recommendations"],"DISABLED")
        self.assertFalse(result["provider_identity_authenticated"])
        self.assertFalse(result["source_independence_verified"])
        self.assertFalse(result["third_party_timestamp_verified"])
        self.assertFalse(result["eligible_for_model_input"])
        self.assertFalse(result["eligible_for_model_scoring"])
        self.assertFalse(result["positive_ev_verified"])
        self.assertFalse(result["odds_or_xg_verified"])
        self.assertEqual(result["certified_forward_samples"],0)
        self.assertEqual(result["source_byte_sha256_unattested"][0],
                         hashlib.sha256(inputs[0]).hexdigest())
        self.assertEqual(len(result["packet_sha256_unattested"]),64)
        self.assertEqual(inputs,original)
        self.assertNotIn("synthetic_home",str(result.get("source_raw_bytes")))

    def test_order_invariance_deterministic_packet_digest(self):
        a=audit(fixture(),pair(),now=NOW)
        b=audit(fixture(),list(reversed(pair())),now=NOW)
        self.assertEqual(a["packet_sha256_unattested"],b["packet_sha256_unattested"])
        self.assertEqual(a["source_byte_sha256_unattested"],b["source_byte_sha256_unattested"])

    def test_score_red_and_status_conflict_are_hold(self):
        for fld,value in (("home_goals",2),("away_red_cards",1),
                          ("match_status","SECOND_HALF"),
                          ("elapsed_regulation_minute",46)):
            second=source("sofascore")
            second[fld]=value
            result=audit(fixture(),[raw(source("fotmob")),raw(second)],now=NOW)
            self.assertEqual(result["status"],"HOLD")
            self.assertEqual(result["reason"],"CROSS_SOURCE_STATE_CONFLICT")

    def test_active_var_review_blocks_matching_scores(self):
        second=source("sofascore")
        second["var_review_pending"]=True
        result=audit(fixture(),[raw(source("fotmob")),raw(second)],now=NOW)
        self.assertEqual(result["reason"],"UNRESOLVED_VAR_REVIEW")

    def test_duplicate_source_and_host_spoofing(self):
        same=[raw(source("fotmob")),raw(source("fotmob"))]
        self.assertEqual(audit(fixture(),same,now=NOW)["reason"],
                         "DUPLICATE_CLAIMED_PUBLISHER")
        for url in ("http://www.sofascore.com/m/1",
                    "https://sofascore.com.evil.tld/m/1",
                    "https://user:password@www.sofascore.com/m/1",
                    "https://www.sofascore.com:8443/m/1"):
            second=source("sofascore")
            second["source_url"]=url
            self.assertEqual(audit(fixture(),[raw(source("fotmob")),raw(second)],now=NOW)["status"],"HOLD")

    def test_wrong_fixture_native_id_and_teams_fail_closed(self):
        for field,value in (("fixture_id","another_event"),
                            ("league_id","other_league"),
                            ("away_id","elsewhere"),
                            ("kickoff_utc","2026-11-23T00:02:00Z"),
                            ("provider_event_id","")):
            second=source("sofascore")
            second[field]=value
            self.assertEqual(audit(fixture(),[raw(source("fotmob")),raw(second)],now=NOW)["status"],"HOLD")

    def test_after_decision_or_late_receipt_is_not_admissible(self):
        for field,value in (("source_updated_utc","2026-11-23T00:51:00Z"),
                            ("captured_utc","2026-11-23T00:51:00Z"),
                            ("received_utc","2026-11-23T00:51:00Z"),
                            ("source_updated_utc","2026-11-23T00:45:00Z"),
                            ("received_utc","2026-11-23T00:44:00Z")):
            second=source("sofascore")
            second[field]=value
            self.assertEqual(audit(fixture(),[raw(source("fotmob")),raw(second)],now=NOW)["status"],"HOLD")

    def test_future_or_stale_decision_fails_even_with_matching_claims(self):
        now=NOW+timedelta(minutes=5)
        self.assertEqual(audit(fixture(),pair(),now=now)["reason"],"STALE_OR_FUTURE_DECISION")
        before=NOW-timedelta(minutes=1)
        self.assertEqual(audit(fixture(),pair(),now=before)["reason"],"STALE_OR_FUTURE_DECISION")

    def test_claimed_identity_seal_too_late(self):
        fi=fixture()
        fi["identity_sealed_utc"]="2026-11-22T23:55:00Z"
        self.assertEqual(audit(fi,pair(),now=NOW)["status"],"HOLD")

    def test_duplicate_json_keys_nan_and_secret_injection_fail(self):
        original=pair()
        bad=b'{"schema":"x","provider":"fotmob","provider":"sofascore"}'
        self.assertEqual(audit(fixture(),[bad,original[1]],now=NOW)["status"],"HOLD")
        payload=raw(source("sofascore")).replace(b'"home_goals":1',b'"home_goals":NaN')
        self.assertEqual(audit(fixture(),[original[0],payload],now=NOW)["status"],"HOLD")
        second=source("sofascore")
        second["api_key"]="MUST_NOT_LEAK"
        result=audit(fixture(),[original[0],raw(second)],now=NOW)
        self.assertEqual(result["status"],"HOLD")
        self.assertNotIn("MUST_NOT_LEAK",str(result))

    def test_bad_binary_oversize_and_wrong_count_rejected(self):
        for inputs in ([b"{}"],[b"{}"]*3,[b"x"*11000,pair()[1]],[None,pair()[1]]):
            self.assertEqual(audit(fixture(),inputs,now=NOW)["status"],"HOLD")

    def test_bool_goals_and_false_timestamp_and_nonzero_reds(self):
        second=source("sofascore")
        second["home_goals"]=True
        self.assertEqual(audit(fixture(),[pair()[0],raw(second)],now=NOW)["status"],"HOLD")
        second=source("sofascore")
        second["received_utc"]="2026-11-23T00:50:03"  # naive
        self.assertEqual(audit(fixture(),[pair()[0],raw(second)],now=NOW)["status"],"HOLD")
        for p in ("fotmob","sofascore"):
            a=source(p);a["home_red_cards"]=1
            b=source("sofascore" if p=="fotmob" else "fotmob")
            self.assertEqual(audit(fixture(),[raw(a),raw(b)],now=NOW)["status"],"HOLD")

    def test_same_two_red_cards_still_unverified_not_model_input(self):
        a,b=source("fotmob"),source("sofascore")
        a["home_red_cards"]=b["home_red_cards"]=1
        r=audit(fixture(),[raw(a),raw(b)],now=NOW)
        self.assertEqual(r["status"],"RESEARCH_ONLY")
        self.assertFalse(r["eligible_for_model_input"])

    def test_claimed_source_url_is_bound_but_not_echoed(self):
        first=source("fotmob")
        second=source("sofascore")
        second["source_url"]="https://www.sofascore.com/football/matches/SENSITIVE_PATH_123"
        result=audit(fixture(),[raw(first),raw(second)],now=NOW)
        self.assertEqual(result["status"],"RESEARCH_ONLY")
        self.assertNotIn("SENSITIVE_PATH_123",str(result))
        self.assertNotIn(second["source_url"],str(result))
        self.assertEqual(len(result["packet_metadata_unattested"]["sources"]),2)


    def test_no_quote_xg_postmatch_or_auth_cert_claims(self):
        for key,val in (("odds",1.8),("xg",2.6),("final_score",[3,1]),
                        ("officially_verified",True),("timestamp_certified",True)):
            b=source("sofascore");b[key]=val
            r=audit(fixture(),[raw(source("fotmob")),raw(b)],now=NOW)
            self.assertEqual(r["status"],"HOLD")

    def test_invalid_clock_malformed_fixture_and_self_hash_not_auth(self):
        fi=fixture()
        fi["source_authenticity_verified"]=True
        self.assertEqual(audit(fi,pair(),now=NOW)["status"],"HOLD")
        self.assertEqual(audit(fixture(),pair(),now=NOW.replace(tzinfo=None))["status"],"HOLD")


if __name__ == "__main__":
    unittest.main()
