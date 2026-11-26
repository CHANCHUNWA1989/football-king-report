import unittest
from live_core_quality_batch_audit import reconcile,LEAGUES,MARKETS
class QualityBatchTests(unittest.TestCase):
    def docs(self):
        stamp="2026-11-26T12:53:19Z"
        def base(schema):return {"schema":schema,"captured_utc":stamp,"production_recommendations":"DISABLED"}
        m=dict(base("football-king-six-free-league-quality-v1"),raw_bookmaker_quotes_published=False,requests_attempted=6,max_requests=7,coverage=[dict(league=k,upcoming_events=10,not_executable_odds=True,**{f:8 for f in MARKETS}) for k in LEAGUES])
        o=dict(base("football-king-six-league-two-publisher-fixtures-v1"),original_bookmaker_quotes_stored=False,market_as_of_utc=None,secondary_as_of_utc=None,market_sample_count=0,time_valid_market_count=0,at_least_one_other_publisher_agreement=0,at_least_two_other_publisher_agreements=0,by_league=[dict(league=k,market_events=0,time_valid_market_events=0,one_other_publisher_agreements=0,two_other_publisher_agreements=0) for k in LEAGUES])
        g=dict(base("football-king-seven-evidence-gates-v1"),can_promote_model=False,can_recommend_bets=False,checks=[{"key":str(i),"state":"HOLD"} for i in range(7)],passed=0,partial=0,held=7,total=7)
        return m,o,g
    def test_marginals_not_joint_identity(self):
        r=reconcile(*self.docs())
        self.assertEqual(r["market_intersection_bounds"],[12,48])
        self.assertFalse(r["cross_source_event_join_verified"])
        self.assertEqual(r["authenticated_forward_samples"],0)
    def test_clock_mismatch(self):
        m,o,g=self.docs();o["captured_utc"]="2026-11-26T12:54:19Z"
        with self.assertRaisesRegex(ValueError,"BATCH_CLOCK_MISMATCH"):reconcile(m,o,g)
    def test_invalid_counts(self):
        m,o,g=self.docs();m["coverage"][0]["full_1x2_events"]=11
        with self.assertRaises(ValueError):reconcile(m,o,g)
    def test_overlap_and_gate_totals(self):
        m,o,g=self.docs();o["at_least_two_other_publisher_agreements"]=1
        with self.assertRaisesRegex(ValueError,"OVERLAP_TOTAL"):reconcile(m,o,g)
        m,o,g=self.docs();g["passed"]=1
        with self.assertRaisesRegex(ValueError,"GATE_TOTAL"):reconcile(m,o,g)
