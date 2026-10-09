"""Synthetic tests proving forward-only scoring, deduplication and HOLD safety."""
import gzip
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forward_validation import load_archived, extend, report_metrics


class ForwardEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.pred = datetime(2026,10,1,8,tzinfo=timezone.utc)
        self.kickoff = self.pred+timedelta(days=1)
        self.now = self.kickoff+timedelta(hours=4)
        self.pair = {
            "league": "bundesliga", "home": "FC Köln", "away": "Bayern",
            "prediction_utc": self.pred.isoformat(),
            "market_snapshot_utc": (self.pred-timedelta(minutes=9)).isoformat(),
            "kickoff_utc": self.kickoff.isoformat(),
            "model": [.3,.3,.4], "market": [.2,.2,.6],
            "production_recommendations": "DISABLED"
        }
        self.report = {"checked_utc": self.now.isoformat(),
                       "fixtures": {"matches": [{
                           "league": "bundesliga", "home": "FC Koln", "away": "Bayern",
                           "kickoff_utc": self.kickoff.isoformat(),
                           "status": "FINISHED", "score_ft": [0,2]}]}}

    def test_later_finished_score_can_be_used_once(self):
        samples=extend({}, [(("bundesliga", "fckoln", "bayern",self.kickoff.isoformat()), self.pair)],self.report)
        self.assertEqual(samples["n"],1)
        self.assertEqual(samples["newly_settled"],1)
        self.assertEqual(samples["samples"][0]["y"],2)
        again=extend(samples, [(("bundesliga", "fckoln", "bayern",self.kickoff.isoformat()), self.pair)],self.report)
        self.assertEqual(again["n"],1)
        self.assertEqual(again["newly_settled"],0)
        stats=report_metrics(again)
        self.assertEqual(stats["status"],"HOLD")
        self.assertEqual(stats["forward_archive_samples"],1)

    def test_unfinished_match_never_scores(self):
        self.report["fixtures"]["matches"][0]["status"]="SCHEDULED"
        r=extend({},[(("bundesliga","fckoln","bayern",self.kickoff.isoformat()),self.pair)],self.report)
        self.assertEqual(r["n"],0)

    def test_score_before_two_hours_is_excluded(self):
        self.report["checked_utc"]=(self.kickoff+timedelta(minutes=90)).isoformat()
        r=extend({},[(("bundesliga","fckoln","bayern",self.kickoff.isoformat()),self.pair)],self.report)
        self.assertEqual(r["n"],0)

    def test_v41_combined_rows_without_league_can_settle_using_source_index(self):
        # The merged V4.1 report drops league; the same fetch that powers
        # Shadow Mode keeps the league on its internal finished observations.
        report={"checked_utc":self.now.isoformat(),
                "fixtures":{"matches":[{
                    "home":"FC Koln","away":"Bayern","date":self.kickoff.date().isoformat(),
                    "kickoff_utc":None,"status":"FINISHED","score_ft":[0,2]}]}}
        results={"schema":"football-king-single-source-finished-results-1",
                 "captured_utc":self.now.isoformat(),
                 "production_recommendations":"DISABLED",
                 "independently_verified_all_leagues":False,
                 "records":[{
                     "league":"bundesliga","home":"FC Köln","away":"Bayern",
                     "date":self.kickoff.date().isoformat(),"kickoff_utc":None,
                     "status":"FINISHED","score_ft":[0,2]}]}
        records=[(("bundesliga","fckoln","bayern",self.kickoff.isoformat()),self.pair)]
        result=extend({},records,report,results)
        self.assertEqual(result["n"],1)
        self.assertEqual(result["samples"][0]["y"],2)
        self.assertFalse(result["samples"][0]["fixture_result_source_independently_verified"])

    def test_wrong_league_or_date_cannot_create_settlement(self):
        report={"checked_utc":self.now.isoformat(),"fixtures":{"matches":[]}}
        results={"schema":"football-king-single-source-finished-results-1",
                 "captured_utc":self.now.isoformat(),
                 "production_recommendations":"DISABLED",
                 "independently_verified_all_leagues":False,
                 "records":[{
                     "league":"epl","home":"FC Köln","away":"Bayern",
                     "date":self.kickoff.date().isoformat(),
                     "status":"FINISHED","score_ft":[0,2]}]}
        rows=[(("bundesliga","fckoln","bayern",self.kickoff.isoformat()),self.pair)]
        self.assertEqual(extend({},rows,report,results)["n"],0)
        results["records"][0]["league"]="bundesliga"
        results["records"][0]["date"]=(self.kickoff.date()+timedelta(days=2)).isoformat()
        self.assertEqual(extend({},rows,report,results)["n"],0)

    def test_ambiguous_finished_scores_require_manual_review(self):
        report={"checked_utc":self.now.isoformat(),"fixtures":{"matches":[]}}
        one={"league":"bundesliga","home":"FC Köln","away":"Bayern",
             "date":self.kickoff.date().isoformat(),
             "status":"FINISHED","score_ft":[0,2]}
        results={"schema":"football-king-single-source-finished-results-1",
                 "captured_utc":self.now.isoformat(),
                 "production_recommendations":"DISABLED",
                 "independently_verified_all_leagues":False,
                 "records":[one,{**one,"score_ft":[1,1]}]}
        rows=[(("bundesliga","fckoln","bayern",self.kickoff.isoformat()),self.pair)]
        self.assertEqual(extend({},rows,report,results)["n"],0)

    def test_archived_future_leakage_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with gzip.open(root/"a.json.gz","wt",encoding="utf-8") as f:
                json.dump({"production_recommendations":"DISABLED",
                           "comparisons":[{**self.pair,"prediction_utc":(self.kickoff+timedelta(hours=1)).isoformat()}]},f)
            self.assertEqual(load_archived(root),[])

    def test_earliest_model_prediction_selected(self):
        early={**self.pair,"model":[.1,.3,.6]}
        later={**self.pair,"prediction_utc":(self.pred+timedelta(hours=1)).isoformat(),
               "model":[.8,.1,.1]}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for filename,record in [("old.json.gz",early),("new.json.gz",later)]:
                with gzip.open(root/filename,"wt",encoding="utf-8") as f:
                    json.dump({"production_recommendations":"DISABLED","comparisons":[record]},f)
            selected=load_archived(root)
            self.assertEqual(len(selected),1)
            self.assertEqual(selected[0][1]["model"],[.1,.3,.6])


    def test_old_market_baseline_cannot_enter_immutable_archive(self):
        old={**self.pair,
             "market_snapshot_utc":(self.pred-timedelta(hours=14)).isoformat()}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with gzip.open(root/"old-market.json.gz","wt",encoding="utf-8") as f:
                json.dump({"production_recommendations":"DISABLED",
                           "comparisons":[old]},f)
            self.assertEqual(load_archived(root),[])

    def test_malformed_previous_settlements_not_trusted(self):
        prior={"samples":[{"key":"fake","y":True,"production_recommendations":"DISABLED"},
                          {"key":"fake2","y":1,"production_recommendations":"ENABLED"}]}
        self.assertEqual(extend(prior,[],self.report)["n"],0)

    def test_metrics_reason_exists_beyond_300_samples(self):
        evidence={"newly_settled":0,"samples":[{
            "kickoff_utc":(self.kickoff+timedelta(days=i//4)).isoformat(),
            "p":[.2,.3,.5],"m":[.25,.25,.5],"y":i%3
        } for i in range(300)]}
        result=report_metrics(evidence)
        self.assertEqual(result["forward_archive_samples"],300)
        self.assertTrue(result["reason"])
        self.assertEqual(result["production_recommendations"],"DISABLED")

if __name__=="__main__":
    unittest.main()
