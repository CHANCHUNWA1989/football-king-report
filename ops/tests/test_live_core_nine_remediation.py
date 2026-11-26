import copy
import json
import math
import unittest
import test_live_core_durable_evidence as fixtures
from live_core_nine_remediation import review
from live_core_frozen_2025_holdout import COHORTS,parse_cohort
from live_core_multi_source import blob
from unittest.mock import patch


class NineRemediationTests(unittest.TestCase):
    def setUp(self):
        self.d=fixtures.DualTests()
        self.d.setUp()
        self.markets=[dict(market="totals",side="UNDER",line=2.25),
                      dict(market="asian_handicap",side="AWAY",line=-.25)]

    def cuts(self):
        d=self.d
        a=copy.deepcopy(d.primary)
        b=copy.deepcopy(d.row)
        out=[]
        for i,(h,v) in enumerate(((.28,.39),(.30,.46))):
            a["response"][0]["fixture"]["status"]["elapsed"]=45+i
            a["response"][0]["statistics"]=[
                dict(team=dict(id=t),statistics=[dict(type="expected_goals",value=x)])
                for t,x in ((1,h),(2,v))]
            b["periods"][0]["minutes"]=45+i
            now=d.now+i*60
            clock={k:v+i*60 for k,v in d.clock.items()}
            out.append(dict(primary_raw=json.dumps(a).encode(),
                            secondary_raw=json.dumps(dict(data=b)).encode(),
                            primary_clock=clock,secondary_clock=clock,now=now))
        return out

    def run_review(self,cuts,**kw):
        d=self.d
        return review(cuts,primary_mapping=d.pm,secondary_mapping=d.mapping,
                      prematch=d.prior,markets=self.markets,**kw)

    def alter(self,cuts,fn):
        a=json.loads(cuts[-1]["primary_raw"])
        fn(a["response"][0])
        cuts[-1]["primary_raw"]=json.dumps(a).encode()
        return cuts

    def test_integrated(self):
        r=self.run_review(self.cuts())
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["research_status"],"RESEARCH_ONLY")
        self.assertEqual(r["scenario_count"],9)
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(r["verified_forward_sample_credit"],0)
        self.assertFalse(r["positive_ev_verified"])
        self.assertFalse(r["xg_used_by_model"])
        self.assertIsNone(r["model_edge"])
        for s in r["scenarios"]:
            self.assertAlmostEqual(sum(s["probabilities_1x2"].values()),1)
            for m in s["market_distributions"]:
                self.assertAlmostEqual(sum(m["outcome_probabilities"].values()),1)

    def test_monterrey_xg_rollback_regression(self):
        c=self.alter(self.cuts(),lambda a:a["statistics"][0]["statistics"][0].update(value=.12))
        r=self.run_review(c)
        self.assertEqual(r["reason"],"XG_REVISION_QUARANTINE")
        self.assertNotIn("scenarios",r)

    def test_missing_xg(self):
        c=self.alter(self.cuts(),lambda a:a.pop("statistics"))
        self.assertEqual(self.run_review(c)["reason"],"XG_DISAPPEARED")

    def test_card_conflict(self):
        c=self.alter(self.cuts(),lambda a:a.update(events=[]))
        self.assertEqual(self.run_review(c)["reason"],"STATE_REVISION_QUARANTINE")

    def test_stale_source(self):
        c=self.cuts();c[-1]["secondary_clock"]={k:v-100 for k,v in c[-1]["secondary_clock"].items()}
        self.assertNotIn("scenarios",self.run_review(c))

    def test_history_missing(self):
        self.assertNotIn("scenarios",self.run_review(self.cuts()[:1]))

    def test_same_capture(self):
        c=self.cuts()
        for k in ("primary_raw","secondary_raw"):c[-1][k]=c[0][k]
        self.assertEqual(self.run_review(c)["reason"],"REPEATED_BOTH_RAW_CAPTURES")

    def test_repeated_single_capture_held(self):
        for key in ("primary_raw","secondary_raw"):
            with self.subTest(key=key):
                c=self.cuts()
                c[-1][key]=c[0][key]
                result=self.run_review(c)
                self.assertEqual(result["reason"],"REPEATED_SINGLE_RAW_CAPTURE")
                self.assertNotIn("scenarios",result)

    def test_nonadjacent_pair_replay_held(self):
        c=self.cuts()
        third=copy.deepcopy(c[0])
        third["now"]=c[-1]["now"]+60
        for key in ("primary_clock","secondary_clock"):
            third[key]={k:v+120 for k,v in third[key].items()}
        c.append(third)
        result=self.run_review(c)
        self.assertEqual(result["reason"],"REPEATED_BOTH_RAW_CAPTURES")
        self.assertNotIn("scenarios",result)

    def test_per_provider_clock_must_advance(self):
        for key in ("primary_clock","secondary_clock"):
            with self.subTest(key=key):
                c=self.cuts()
                c[-1][key]=dict(c[0][key])
                result=self.run_review(c)
                self.assertEqual(result["reason"],"PROVIDER_CLOCK_NOT_ADVANCING")
                self.assertNotIn("scenarios",result)

    def test_clock_claim_binding_is_not_authentication(self):
        c=self.cuts()
        a=self.run_review(c)
        self.assertTrue(a["provider_clock_claims_bound"])
        self.assertFalse(a["provider_upstream_clock_verified"])
        c[-1]["primary_clock"]["captured"]-=1
        b=self.run_review(c)
        self.assertEqual(b["research_status"],"RESEARCH_ONLY")
        self.assertNotEqual(a["ledger_digest_unattested"],b["ledger_digest_unattested"])
        self.assertEqual(b["verified_forward_sample_credit"],0)

    def test_context_diagnostic_only(self):
        c=self.cuts()
        ctx=dict(fixture_id="test-match",minute=46,observed=c[-1]["now"]-5,
            source_url="https://example.org/research",keeper_psxg_faced=[.4,.2],
            keeper_goals_conceded=[0,0],competition_format="KNOCKOUT_TWO_LEG",
            aggregate_score=[0,0],tie_rule="RANK_ADVANTAGE",announced_added_minutes=None)
        a=self.run_review(c);b=self.run_review(c,context=ctx)
        self.assertEqual(a["scenarios"],b["scenarios"])
        self.assertTrue(b["context_diagnostics"]["keeper_available"])
        self.assertFalse(b["context_diagnostics"]["keeper_claim_used"])
        self.assertFalse(b["context_diagnostics"]["knockout_claim_used"])
        ctx["observed"]-=100
        self.assertNotIn("scenarios",self.run_review(c,context=ctx))

    def test_sensitivity_direction(self):
        s=self.run_review(self.cuts())["scenarios"]
        self.assertGreater(s[2]["remaining_expected_goals"][0],s[0]["remaining_expected_goals"][0])
        self.assertLess(s[6]["remaining_expected_goals"][0],s[0]["remaining_expected_goals"][0])
        self.assertGreater(s[6]["remaining_expected_goals"][1],s[0]["remaining_expected_goals"][1])

    def test_unverified_quote_never_ev(self):
        c=self.cuts()
        q=dict(fixture_id="test-match",observed=c[-1]["now"]-5,minute=46,score=[0,0],reds=[1,0],
               market="totals",side="UNDER",line=2.25,decimal_price=1.9,
               source_url="https://example.org/quote",bookmaker="test",
               suspended=False,scope="REGULATION_FULLTIME")
        r=self.run_review(c,quotes=[q])
        self.assertEqual(r["quote_claim_count"],1)
        self.assertIsNone(r["model_edge"])
        self.assertFalse(r["positive_ev_verified"])
        q["suspended"]=True
        self.assertNotIn("scenarios",self.run_review(c,quotes=[q]))

    def test_frozen_cohort_rejects_wrong_bytes(self):
        self.assertEqual(sum(v[4] for v in COHORTS.values()),647)
        with self.assertRaises(ValueError):parse_cohort(b"{}", "EPL")


class FrozenScoreEncodingTests(unittest.TestCase):
    def fixture(self):
        return {"name":"Test league","matches":[
            {"date":"2025-08-15","team1":"A","team2":"B","score":{"ft":[0,0]}},
            {"date":"2025-08-16","team1":"C","team2":"D","score":[0,0]},
            {"date":"2025-08-17","team1":"E","team2":"F","score":{"ft":[2,1],"ht":[1,0]}}]}

    def parse(self,d,finished=2):
        raw=json.dumps(d).encode()
        with patch.dict(COHORTS,{"TEST":("test","Test league",blob(raw),3,finished,"team")}):
            return parse_cohort(raw,"TEST")

    def test_explicit_scoreless_draw_retained_alternate_encoding_excluded(self):
        rows=self.parse(self.fixture())
        self.assertEqual(rows,[("2025-08-15","A","B",0,0),("2025-08-17","E","F",2,1)])

    def test_unrecognized_score_encodings_fail_closed(self):
        for invalid in ([1,0],[False,0],[],None,{},{"ft":None},{"ft":[1,True]}):
            with self.subTest(invalid=invalid):
                d=self.fixture();d["matches"][1]["score"]=invalid
                with self.assertRaises(ValueError):self.parse(d)

    def test_alternate_row_duplicate_fails_closed(self):
        d=self.fixture()
        d["matches"][1].update(date="2025-08-15",team1="A",team2="B")
        with self.assertRaisesRegex(ValueError,"DUPLICATE_MATCH"):self.parse(d)

    def test_alternate_row_outside_season_fails_closed(self):
        d=self.fixture();d["matches"][1]["date"]="2024-08-15"
        with self.assertRaisesRegex(ValueError,"SEASON_DATE"):self.parse(d)

    def test_frozen_finished_count_cannot_change(self):
        d=self.fixture();d["matches"][1]["score"]={"ft":[0,0]}
        with self.assertRaisesRegex(ValueError,"FINISHED_COHORT_SCOPE"):self.parse(d)

    def test_conditional_draw_scenario_is_explicit_and_does_not_change_default(self):
        d=self.fixture()
        raw=json.dumps(d).encode()
        with patch.dict(COHORTS,{"TEST":("test","Test league",blob(raw),3,2,"team")}):
            base=parse_cohort(raw,"TEST")
            conditional=parse_cohort(raw,"TEST",assume_alternate_draws=True)
            self.assertEqual(len(base),2)
            self.assertEqual(len(conditional),3)
            self.assertIn(("2025-08-16","C","D",0,0),conditional)
            self.assertEqual(parse_cohort(raw,"TEST"),base)
            with self.assertRaisesRegex(ValueError,"SCENARIO_FLAG"):
                parse_cohort(raw,"TEST",assume_alternate_draws="yes")

    def test_conditional_scenario_does_not_bypass_score_validation(self):
        d=self.fixture()
        d["matches"][1]["score"]=[1,0]
        raw=json.dumps(d).encode()
        with patch.dict(COHORTS,{"TEST":("test","Test league",blob(raw),3,2,"team")}):
            with self.assertRaisesRegex(ValueError,"UNRECOGNIZED_SCORE_ENCODING"):
                parse_cohort(raw,"TEST",assume_alternate_draws=True)
