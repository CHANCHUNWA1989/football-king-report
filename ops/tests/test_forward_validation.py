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


if __name__=="__main__":
    unittest.main()
