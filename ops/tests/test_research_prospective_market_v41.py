import json
import unittest
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from ops.research_prospective_market_v41 import audit,from_root

NOW=datetime(2026,11,20,9,tzinfo=timezone.utc)
def fixture():
    return {"schema":"football-king-market-consensus-v1","provider":"the-odds-api.com/v4",
            "as_of_utc":(NOW-timedelta(minutes=5)).isoformat(),"status":"RESEARCH_ONLY",
            "market":"h2h","requested_markets":["h2h"],"production_recommendations":"DISABLED",
            "raw_bookmaker_quotes_redistributed":False,"raw_bookmaker_names_redistributed":False,
            "market_probabilities_calibrated":False,"model_value_advantage_verified":False,
            "event_count":1,"events":[{"league":"epl","source_event_id":"test-id",
                "home":"Arsenal","away":"Chelsea","kickoff_utc":(NOW+timedelta(hours=2)).isoformat(),
                "market_last_update_utc":(NOW-timedelta(hours=1)).isoformat(),
                "contributing_bookmakers":2,"p_home":.5,"p_draw":.3,"p_away":.2,
                "probabilities_are_no_vig_consensus":True,"prediction_or_value_bet":False}]}
def run(d,now=NOW):
    return audit(json.dumps(d).encode(),as_of=now.isoformat(),include_components=True)
class ProspectiveMarketTests(unittest.TestCase):
    def test_fresh_component_oldest_update(self):
        d=fixture()
        with patch("ops.research_prospective_market_v41.REGISTRATION_NOT_BEFORE","2026-11-20T00:00:00Z"):
            r=run(d)
        self.assertEqual(r["market_components"],1)
        c=r["components"][0]
        self.assertEqual(c["market"]["captured_utc"],d["events"][0]["market_last_update_utc"])
        self.assertEqual(c["snapshot_captured_utc"],d["as_of_utc"])
        self.assertEqual(c["market"]["evidence_sha256"],r["snapshot_sha256"])
        self.assertEqual(r["complete_prospective_inputs"],0)
    def test_oldest_update_stale(self):
        d=fixture();d["events"][0]["market_last_update_utc"]=(NOW-timedelta(seconds=3601)).isoformat()
        self.assertEqual(run(d)["states"],{"STALE_OLDEST_UPDATE":1})
    def test_stale_snapshot(self):
        self.assertEqual(run(fixture(),NOW+timedelta(days=7))["states"],{"STALE_SNAPSHOT":1})
    def test_before_registration(self):
        self.assertEqual(run(fixture())["states"],{"BEFORE_REGISTRATION_WINDOW":1})
    def test_kickoff_lead(self):
        d=fixture();d["events"][0]["kickoff_utc"]=(NOW+timedelta(minutes=14)).isoformat()
        self.assertEqual(run(d)["states"],{"INSUFFICIENT_KICKOFF_LEAD":1})
    def test_future_snapshot(self):
        with self.assertRaises(ValueError):run(fixture(),NOW-timedelta(minutes=6))
    def test_duplicate_canonical_fixture(self):
        d=fixture();e=deepcopy(d["events"][0]);e["source_event_id"]="different"
        e["home"]="Arsenal FC";d["events"].append(e);d["event_count"]=2
        # Exact names also must collide regardless of the alias registry.
        e["home"]=d["events"][0]["home"]
        with self.assertRaises(ValueError):run(d)
    def test_actual_archive(self):
        root=Path(__file__).resolve().parents[2];path=root/"market/latest.json";raw=path.read_bytes()
        r=from_root(root,as_of=datetime.now(timezone.utc).isoformat())
        self.assertEqual(sum(r["states"].values()),r["snapshot_events"])
        self.assertEqual(r["provider_calls_made"],0)
        self.assertEqual(r["authenticated_samples"],0)
        self.assertEqual(path.read_bytes(),raw)
        if r["snapshot_age_seconds"]>3600:self.assertEqual(r["market_components"],0)
        print("V41_PROSPECTIVE_MARKET_SUMMARY "+json.dumps(r,sort_keys=True,allow_nan=False))
