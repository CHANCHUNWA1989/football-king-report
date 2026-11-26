import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from live_core_provider_evidence import normalize,run
from live_core_xg_calibration import evaluate
from live_core_real_observations import epoch_iso


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.now=1795680240
        self.mapping=dict(fixture_id="test-fixture",provider_id=7,home_id=1,away_id=2,
                          kickoff_utc=epoch_iso(self.now-3600))
        self.row=dict(fixture=dict(id=7,date=self.mapping["kickoff_utc"],
                     status=dict(short="2H",elapsed=45,extra=None)),
                     teams=dict(home=dict(id=1),away=dict(id=2)),goals=dict(home=0,away=0),
                     events=[dict(type="Card",detail="Red Card",team=dict(id=1),
                                  player=dict(id=8),time=dict(elapsed=11))],
                     statistics=[dict(team=dict(id=i),statistics=[dict(type="expected_goals",value=v)])
                                 for i,v in ((1,"0.28"),(2,"0.39"))])
        self.clock=dict(captured=self.now-4,received=self.now-3,
                        observed_claim=self.now-5,now=self.now)
        self.prior=dict(fixture_id="test-fixture",model_id="fixture-test",
                        forecast_utc=epoch_iso(self.now-4500),
                        inputs_available_utc=epoch_iso(self.now-4600),
                        expected_home_goals=1.3,expected_away_goals=1.1,
                        input_sha256="c"*64,production_recommendations="DISABLED",calibrated=False)

    def raw(self):
        return json.dumps(dict(errors=[],response=[self.row])).encode()

    def parse(self):
        return normalize(self.raw(),self.mapping,**self.clock)

    def run_case(self,quotes=None):
        a,_=self.parse()
        b=dict(state={**a["state"],"origin":"fixture-test-secondary"},
               url="https://example.org/game",payload_sha256="a"*64)
        markets=[dict(market="totals",side="UNDER",line=1.25)]
        return run(self.raw(),self.mapping,**self.clock,secondary=b,prematch=self.prior,
                   markets=markets,quotes=quotes)

    def quote(self):
        return dict(fixture_id="test-fixture",observed=self.now-5,minute=45,
                    score=[0,0],reds=[1,0],market="totals",side="UNDER",line=1.25,
                    decimal_price=1.93,source_url="https://example.com/game",
                    bookmaker="test-only",suspended=False,scope="REGULATION_FULLTIME")

    def test_pipeline(self):
        r=self.run_case([self.quote()])
        self.assertEqual(r["research_status"],"RESEARCH_ONLY")
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["xg_claim_same_cut"]["away"],.39)
        self.assertFalse(r["xg_used_by_model"])
        self.assertFalse(r["quote_reviews"][0]["executable_verified"])
        self.assertFalse(r["positive_ev_verified"])
        self.assertIsNone(r["model_edge"])

    def test_wrong_fixture(self):
        self.mapping["provider_id"]=8
        with self.assertRaises(ValueError): self.parse()

    def test_missing_events(self):
        del self.row["events"]
        with self.assertRaises(ValueError): self.parse()

    def test_var(self):
        self.row["events"].append(dict(type="Var"))
        with self.assertRaises(ValueError): self.parse()

    def test_missing_xg(self):
        del self.row["statistics"]
        self.assertIsNone(self.parse()[1])

    def test_duplicate_card_same_player(self):
        self.row["events"].append(copy.deepcopy(self.row["events"][0]))
        self.assertEqual(self.parse()[0]["state"]["red_home"],1)

    def test_stale(self):
        self.clock["observed_claim"]=self.now-91
        with self.assertRaises(ValueError): self.parse()

    def test_suspended(self):
        q=self.quote();q["suspended"]=True
        self.assertNotIn("probabilities_1x2",self.run_case([q]))

    def test_quote_wrong_score(self):
        q=self.quote();q["score"]=[1,0]
        self.assertNotIn("probabilities_1x2",self.run_case([q]))

    def test_quote_wrong_scope(self):
        q=self.quote();q["scope"]="REMAINING_ONLY"
        self.assertNotIn("probabilities_1x2",self.run_case([q]))


class CalibrationTests(unittest.TestCase):
    def row(self,i):
        return dict(fixture_id=str(i),decision=1000+i*100,
                    result_available=1050+i*100,minute=45,score=[0,0],reds=[1,0],
                    xg=[.2,1.2],base_remaining=[.6,.8],final=[0,1])

    def test_insufficient(self):
        self.assertIsNone(evaluate([self.row(0)],split=11000,assessment_end=30000)["selected_weight"])

    def test_chronological(self):
        r=evaluate([self.row(i) for i in range(150)],split=11000,assessment_end=30000)
        self.assertEqual((r["train_n"],r["test_n"]),(100,50))
        self.assertIsNotNone(r["assessment"])
        self.assertFalse(r["model_calibrated"])
        self.assertFalse(r["automatic_promotion"])

    def test_duplicate(self):
        with self.assertRaises(ValueError):
            evaluate([self.row(0)]*2,split=11000,assessment_end=30000)

    def test_future_result(self):
        r=self.row(0);r["result_available"]=30000
        with self.assertRaises(ValueError): evaluate([r],split=11000,assessment_end=30000)

    def test_cross_split_exclusion(self):
        r=self.row(99);r["result_available"]=11001
        out=evaluate([r],split=11000,assessment_end=30000)
        self.assertEqual(out["excluded_cross_split_n"],1)
