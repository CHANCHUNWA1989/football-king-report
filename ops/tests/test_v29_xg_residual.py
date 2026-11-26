import unittest
from datetime import timedelta
from ops.v29_xg_residual import correction,join,evaluate,run,enc,sha
from ops.v6_forward_bundle import utc
from ops.v8_multiseason import PIN

def sample():
    ko=utc("2025-09-01T18:00:00Z")
    r={"league":"de.1","season":"2025-26","date":"2025-09-01","home":"A","away":"B","y":0,"goals":[2,1],"stack":[.5,.3,.2]}
    anchor={"schema":"v29-stack-reference-v1","historical_source_commit":PIN,"rows":[r],"status":"HOLD","production_recommendations":"DISABLED","verified_forward_sample_credit":0}
    x={"id":"1","home":"2","away":"3","ko":ko,"available":ko+timedelta(hours=3),"goals":(2,1),"xg":(1.6,.9)}
    m={"schema":"v29-explicit-xg-fixture-crosswalk-v1","league":"de.1","provider":"test",
       "pairs":[{"match_id":"1","home_id":"2","away_id":"3","kickoff_utc":ko.isoformat(),"date":"2025-09-01","home":"A","away":"B","evidence_reference":"https://example.invalid/fixture"}]}
    return anchor,x,m
class XgResidualTests(unittest.TestCase):
    def test_exact_fallback_and_mass(self):
        r={"stack":[.5,.3,.2],"goal_model":[.5,.3,.2],"xg_model":[.2,.3,.5]}
        self.assertEqual(correction(r,0.),r["stack"])
        p=correction(r,.5);self.assertAlmostEqual(sum(p),1.)
        self.assertLess(p[0],r["stack"][0])
    def test_map_requires_exact_score(self):
        a,x,m=sample();x["goals"]=(3,1)
        with self.assertRaisesRegex(ValueError,"MAP_SCORE_CLOCK"):join(a,[x],m,"de.1","test")
    def test_map_requires_exact_id_and_time(self):
        a,x,m=sample();m["pairs"][0]["home_id"]="9"
        with self.assertRaisesRegex(ValueError,"MAP_SCORE_CLOCK"):join(a,[x],m,"de.1","test")
    def test_insufficient_history_never_scores(self):
        a,x,m=sample();rows,total=join(a,[x],m,"de.1","test")
        self.assertEqual(rows,[]);out=evaluate(rows,total)
        self.assertIsNone(out["metrics"]);self.assertEqual(out["verified_forward_sample_credit"],0)
    def test_explicit_authorization_required(self):
        a,x,m=sample();ar,mr=enc(a),enc(m)
        with self.assertRaisesRegex(ValueError,"AUTHORIZATION_OR_AVAILABILITY"):
            run(ar,sha(ar),b"{}",enc({"competition_scope":"de.1"}),mr,sha(mr),now=x["available"])
