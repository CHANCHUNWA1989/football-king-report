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

    def test_separate_populations_and_stale_clocks(self):
        m,o,g=self.docs()
        o.update(market_as_of_utc="2026-11-20T08:24:35Z",market_fresh=False,secondary_fresh=False)
        r=reconcile(m,o,g)["source_readiness_diagnostic"]
        self.assertEqual(r["aggregate_market_observations"],60)
        self.assertEqual(r["separate_overlap_market_observations"],0)
        self.assertTrue(r["population_difference_is_not_missing_fixture_count"])
        self.assertIsNone(r["joined_eligible_fixtures"])
        self.assertEqual(r["overlap_source_clocks"]["market"]["diagnostic_state"],"OLDER_THAN_DIAGNOSTIC_CEILING")
        self.assertEqual(r["overlap_source_clocks"]["secondary"]["diagnostic_state"],"CLOCK_MISSING")
        self.assertEqual(r["executable_verified_fixtures"],0)
    def test_freshness_contradiction_and_invalid_flags(self):
        m,o,g=self.docs();o["market_fresh"]=True
        r=reconcile(m,o,g)["source_readiness_diagnostic"]
        self.assertIn("DECLARED_FRESHNESS_CONTRADICTS_DIAGNOSTIC_CLOCK",r["blockers"])
        o["market_fresh"]=1
        with self.assertRaisesRegex(ValueError,"INVALID_FRESHNESS_FLAG"):reconcile(m,o,g)
    def test_fresh_clocks_do_not_authenticate_quotes(self):
        m,o,g=self.docs()
        o.update(market_as_of_utc=m["captured_utc"],secondary_as_of_utc=m["captured_utc"],
                 market_fresh=True,secondary_fresh=True,secondary_licensed_source_validation=True)
        r=reconcile(m,o,g)["source_readiness_diagnostic"]
        self.assertNotIn("MARKET_FRESHNESS_NOT_ESTABLISHED",r["blockers"])
        self.assertIn("EVENT_LEVEL_MARKET_JOIN_UNVERIFIED",r["blockers"])
        self.assertEqual(r["executable_verified_fixtures"],0)
