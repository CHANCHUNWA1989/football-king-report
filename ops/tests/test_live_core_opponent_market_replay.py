import unittest
import json
from unittest.mock import patch
from datetime import date,timedelta
from live_core_opponent_strength import forecasts
from live_core_opponent_market_replay import grade_brier,report,parse,MARKETS,SPECS,stability,SEASON_KEYS,STABILITY_METRICS,EQUIVALENT_BRIER
from live_core_multi_source import blob
from score_distribution_vnext import score_matrix
class OpponentMarketReplayTests(unittest.TestCase):
    def train(self):
        return [((date(2023,8,1)+timedelta(days=i)).isoformat(),"A","B",i%3,1) for i in range(60)]
    def test_matrices_preserve_original_forecasts(self):
        t=[("2024-08-01","A","B",1,0)]
        plain=forecasts(self.train(),t)[0]
        extra=forecasts(self.train(),t,include_matrices=True)[0]
        self.assertEqual(plain,extra[:7])
        self.assertEqual(set(extra[-1]),{"baseline","blend_50"})
    def test_exact_quarter_grade_brier(self):
        # Home win by one: -0.75 is half win, +0.25 full win.
        matrix=((0.,0.),(1.,0.))
        self.assertEqual(grade_brier(matrix,1,0,"asian_handicap","HOME",-.75),0.)
        self.assertEqual(grade_brier(matrix,0,0,"asian_handicap","HOME",-.75),2.)
        for _,market,side,line in MARKETS:
            self.assertTrue(0<=grade_brier(score_matrix(1.5,1.2),1,0,market,side,line)<=2)
    def test_same_cases_and_metric_count(self):
        r=report(self.train(),[("2024-08-01","A","B",1,0)])
        self.assertEqual(r["assessment_n"],1)
        self.assertEqual(len(r["metrics"]),9)
        for v in r["metrics"].values():
            self.assertAlmostEqual(v["baseline"]-v["blend_50"],v["baseline_minus_candidate"])
    def test_bad_pin(self):
        with self.assertRaisesRegex(ValueError,"BLOB_PIN_CHANGED"):parse(b"{}","EPL")

    def test_bare_placeholder_not_counted_as_draw(self):
        doc={"name":"Synthetic","matches":[
            {"date":"2025-08-01","team1":"A","team2":"B","score":[0,0]},
            {"date":"2025-08-02","team1":"B","team2":"A","score":{"ft":[0,0]}}]}
        raw=json.dumps(doc).encode()
        with patch.dict(SPECS,{"EPL":("en.1","Synthetic",2,1,blob(raw))}):
            self.assertEqual(parse(raw,"EPL"),[("2025-08-02","B","A",0,0)])
        doc["matches"][0]["score"]=[1,2]
        raw=json.dumps(doc).encode()
        with patch.dict(SPECS,{"EPL":("en.1","Synthetic",2,1,blob(raw))}):
            with self.assertRaisesRegex(ValueError,"UNRECOGNIZED_SCORE_FORMAT"):
                parse(raw,"EPL")

    def stability_fixture(self):
        from live_core_opponent_strength import SPECS as prior
        import copy
        all_leagues={}
        for league in SPECS:
            blocks={}
            for season,scheduled in zip(SEASON_KEYS,(prior[league][2],SPECS[league][2])):
                metric={"baseline":1.0,"blend_50":0.99,
                        "baseline_minus_candidate":0.01,"descriptive_ci95":[-0.01,0.03]}
                keys=list(STABILITY_METRICS)+[a for v in EQUIVALENT_BRIER.values() for a in v]
                blocks[season]={"assessment_n":scheduled-1,"assessment_missing":1,
                                "metrics":{k:copy.deepcopy(metric) for k in keys}}
            all_leagues[league]=blocks
        return all_leagues
    def test_stability_uncertain_not_promotion(self):
        r=stability(self.stability_fixture())
        self.assertEqual(r["total_missing_observations"],6)
        self.assertEqual(r["total_scored_observations"],2126)
        self.assertEqual(r["leagues"]["EPL"]["metric_stability"]["1x2_log_loss"]["state"],
                         "DIRECTIONALLY_POSITIVE_UNCERTAIN")
        self.assertIsNone(r["independent_evidence_count"])
        self.assertFalse(r["automatic_promotion"])
    def test_stability_degradation_and_positive_interval(self):
        data=self.stability_fixture()
        for period in data["BL"].values():
            period["metrics"]["1x2_log_loss"]["descriptive_ci95"]=[.001,.02]
        data["BL"][SEASON_KEYS[1]]["metrics"]["under25_brier"].update(
            blend_50=1.01,baseline_minus_candidate=-.01)
        r=stability(data)["leagues"]["BL"]["metric_stability"]
        self.assertEqual(r["1x2_log_loss"]["state"],"POSITIVE_DESCRIPTIVE_INTERVALS_BOTH_SEASONS")
        self.assertEqual(r["under25_brier"]["state"],"DEGRADATION_IN_AT_LEAST_ONE_SEASON")
    def test_stability_rejects_equivalent_grade_mismatch(self):
        data=self.stability_fixture()
        data["ES"][SEASON_KEYS[0]]["metrics"]["home_minus_025_grade_brier"].update(
            blend_50=.98,baseline_minus_candidate=.02)
        with self.assertRaisesRegex(ValueError,"EQUIVALENT_GRADE_CONFLICT"):
            stability(data)
    def test_stability_rejects_bad_count_and_interval(self):
        data=self.stability_fixture()
        data["EPL"][SEASON_KEYS[1]]["assessment_missing"]=True
        with self.assertRaisesRegex(ValueError,"ASSESSMENT_ACCOUNTING"):
            stability(data)
        data=self.stability_fixture()
        data["EPL"][SEASON_KEYS[1]]["metrics"]["1x2_log_loss"]["descriptive_ci95"]=[.1,-.1]
        with self.assertRaisesRegex(ValueError,"INVALID_INTERVAL"):
            stability(data)
