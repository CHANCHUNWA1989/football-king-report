import copy
import unittest
from datetime import timedelta
import test_live_core_blend50_forward_seal as fixtures
from live_core_blend50_forward_seal import seal,digest
from live_core_blend50_forward_settlement import settle,aggregate

class Blend50SettlementTests(unittest.TestCase):
    def case(self):
        now,original=fixtures.Blend50ForwardSealTests().fixture()
        f=seal(original,now=now)
        check=now+timedelta(hours=5)
        results=[dict(s,observed_utc=check.isoformat(),status="FINAL_REGULATION",score=[1,0]) for s in original["fixture"]["sources"]]
        return check,{"original":original,"forecast":f,"results":results}
    def test_replay_and_pair_metrics(self):
        now,c=self.case()
        r=settle(c["original"],c["forecast"],c["results"],now=now)
        self.assertEqual(r["record_sha256"],digest(r["record"]))
        self.assertEqual(len(r["record"]["metrics"]["baseline"]),9)
        self.assertEqual(r["record"]["authenticated_forward_samples"],0)
        summary=aggregate([c],now=now)
        self.assertEqual(summary["recorded_local_cases"],1)
        self.assertIsNone(summary["pooled"]["primary_descriptive_ci95"])
        self.assertEqual(summary["production_recommendations"],"DISABLED")
    def test_rehash_tamper_not_accepted(self):
        now,c=self.case();r=c["forecast"]["record"]
        r["models"]["baseline"]["goal_rates"]=[5.0,.1]
        c["forecast"]["record_sha256"]=digest(r)
        with self.assertRaisesRegex(ValueError,"SEALED_REPLAY_MISMATCH"):aggregate([c],now=now)
    def test_source_score_conflict_and_clock(self):
        now,c=self.case()
        for field,value in (("score",[0,1]),("fixture_id","other"),("observed_utc",(now+timedelta(seconds=1)).isoformat()),("status","LIVE")):
            x=copy.deepcopy(c);x["results"][1][field]=value
            with self.assertRaises(ValueError):aggregate([x],now=now)
        with self.assertRaises(ValueError):aggregate([c],now=now-timedelta(hours=4))
    def test_duplicate_case_and_empty(self):
        now,c=self.case()
        with self.assertRaisesRegex(ValueError,"DUPLICATE_SETTLEMENT"):aggregate([c,c],now=now)
        r=aggregate([],now=now)
        self.assertEqual(r["recorded_local_cases"],0)
        self.assertIsNone(r["pooled"]["metrics"]["1x2_log_loss"]["baseline"])
    def test_original_input_change(self):
        now,c=self.case();c["original"]["history"][0]["score"]=[4,2]
        with self.assertRaisesRegex(ValueError,"SEALED_REPLAY_MISMATCH"):aggregate([c],now=now)
    def test_native_id_reuse_across_fixtures(self):
        now,c=self.case()
        d=copy.deepcopy(c)
        d["original"]["fixture"]["home"]="C"
        for s in d["original"]["fixture"]["sources"]:s["home"]="C"
        for s in d["results"]:s["home"]="C"
        d["forecast"]=seal(d["original"],now=now-timedelta(hours=5))
        with self.assertRaisesRegex(ValueError,"REUSED_NATIVE_ID"):aggregate([c,d],now=now)
