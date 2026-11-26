"""Synthetic-only tests for the private DHE input adapter."""
import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deep_handicap_private_capture import capture
from shadow_forecast import poisson_1x2

NOW = datetime(2026,11,27,8,tzinfo=timezone.utc)
KO = (NOW+timedelta(hours=2)).isoformat()
SOURCE = (NOW-timedelta(minutes=5)).isoformat()


def inputs():
    p = poisson_1x2(2.9,.9)
    r = {"league":"epl","event_id":"source:42","home":"Liverpool","away":"Arsenal",
         "kickoff_utc":KO,"prediction_utc":SOURCE,"model":"poisson-shrinkage-unvalidated-v4.1",
         "training_games":80,"training_cutoff_local_day":"2026-11-26",
         "training_observations_sha256":"a"*64,"expected_home_goals":2.9,"expected_away_goals":.9,
         "p_home":p[0],"p_draw":p[1],"p_away":p[2],"production_recommendations":"DISABLED"}
    s = {"schema":"football-king-uncalibrated-shadow-1","as_of_utc":SOURCE,"status":"SHADOW_ONLY",
         "predictions_count":1,"predictions":[r],"production_recommendations":"DISABLED"}
    q = {"schema":"football-king-quote-freshness-v1","production_recommendations":"DISABLED",
         "market_snapshot_research_only":True,"executable_bookmaker_price_verified":False,
         "status":"RESEARCH_ONLY","matched_events":1,"home":"Liverpool","away":"Arsenal",
         "league":"soccer_epl","captured_utc":(NOW-timedelta(seconds=10)).isoformat(),
         "quotes_accepted":2,"quotes":[]}
    for name, point in (("Liverpool",-2.25),("Arsenal",2.25)):
        q["quotes"].append({"source":"the_odds_api_v4","status":"FRESH_OBSERVATION_NOT_EXECUTABLE",
             "quote_pre_match_at_capture":True,"market_phase_at_capture":"PREMATCH","event_id":"synthetic-event",
             "bookmaker":"synthetic-private-book","market":"spreads","outcome":name,"point":point,
             "decimal_odds":1.91,"kickoff_utc":KO,
             "market_last_update_utc":(NOW-timedelta(seconds=20)).isoformat()})
    return s,q


class PrivateCaptureTests(unittest.TestCase):
    def test_valid_structural_candidate_is_not_authenticated(self):
        s,q = inputs()
        before = copy.deepcopy((s,q))
        out = capture(s,q,now=NOW)
        self.assertEqual((s,q),before)
        self.assertEqual(out["reason"],"CANDIDATE_READY_FOR_PRIVATE_EXTERNAL_WITNESS")
        c = out["candidate"]
        self.assertEqual(c["handicap"],-2.25)
        self.assertEqual(c["baseline"]["information_cutoff_utc"],c["challenger"]["information_cutoff_utc"])
        for name in ("baseline","challenger"):
            self.assertAlmostEqual(sum(c[name]["probabilities"].values()),1)
        self.assertNotIn("results",c)
        self.assertFalse(out["source_authenticated"])
        self.assertFalse(out["external_archive_witness_verified"])
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["true_forward_sample_count"],0)
        dump = json.dumps(out)
        self.assertNotIn("synthetic-private-book",dump)
        self.assertNotIn("decimal_odds",dump)
        self.assertEqual(out,capture(s,q,now=NOW))

    def test_quote_gate_rejects_bad_inputs(self):
        for change in (
            lambda q: q["quotes"][0].update(market_last_update_utc=(NOW-timedelta(seconds=121)).isoformat()),
            lambda q: q["quotes"][0].update(quote_pre_match_at_capture=False),
            lambda q: q["quotes"][1].update(point=2),
            lambda q: q["quotes"][1].update(event_id="different"),
            lambda q: q["quotes"][1].update(bookmaker="different"),
            lambda q: q["quotes"][1].update(decimal_odds=True),
            lambda q: q.update(captured_utc=(NOW+timedelta(seconds=1)).isoformat()),
            lambda q: q.update(matched_events=2),
        ):
            s,q=inputs()
            change(q)
            self.assertIsNone(capture(s,q,now=NOW)["candidate"])

    def test_duplicate_shadow_future_training_and_wrong_kickoff_rejected(self):
        for change in (
            lambda s: (s["predictions"].append(copy.deepcopy(s["predictions"][0])),s.update(predictions_count=2)),
            lambda s: s["predictions"][0].update(training_cutoff_local_day="2026-11-27"),
            lambda s: s["predictions"][0].update(kickoff_utc=(NOW+timedelta(hours=3)).isoformat()),
            lambda s: s["predictions"][0].update(score_ft=[2,0]),
            lambda s: s.update(as_of_utc=(NOW+timedelta(seconds=1)).isoformat()),
        ):
            s,q=inputs()
            change(s)
            self.assertIsNone(capture(s,q,now=NOW)["candidate"])

    def test_multiple_complete_lines_are_rejected_not_selected_by_price(self):
        s,q=inputs()
        for item in copy.deepcopy(q["quotes"]):
            item["point"] = -2 if item["point"] < 0 else 2
            q["quotes"].append(item)
        q["quotes_accepted"]=4
        self.assertIsNone(capture(s,q,now=NOW)["candidate"])
