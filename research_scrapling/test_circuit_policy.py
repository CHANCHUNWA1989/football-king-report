"""Deterministic circuit policy simulations, not live source evidence."""
import unittest
from datetime import timedelta
from circuit_policy import start,advance,snapshot
from test_evidence_intake import doc,NOW

def at(seconds):return NOW+timedelta(seconds=seconds)
def observation(domain,seconds):
    x=doc(domain)
    for row in x["source_evidence"]:row["captured_utc"]=at(seconds).isoformat()
    return x

class CircuitTests(unittest.TestCase):
    def initial(self):return start("football",NOW)
    def step(self,s,t):return advance(s,observation(s.domain,t),at(t))
    def recovered(self):
        s=self.initial()
        for t in (300,330,360):s=self.step(s,t)
        return s
    def test_initial_open(self):
        self.assertEqual(self.initial().phase,"OPEN")
    def test_cooldown(self):
        self.assertEqual(self.step(self.initial(),299).phase,"OPEN")
    def test_three_distinct_successes(self):
        s=self.initial()
        for t,phase in ((300,"HALF_OPEN"),(330,"HALF_OPEN"),(360,"HISTORICAL_RESEARCH_READY")):
            s=self.step(s,t);self.assertEqual(s.phase,phase)
    def test_failure_reopens(self):
        s=advance(self.recovered(),{},at(361))
        self.assertEqual((s.phase,s.successes,s.reopen_until),("OPEN",0,at(661)))
    def test_replay_reopens(self):
        s=self.step(self.initial(),300)
        s=advance(s,observation("football",300),at(330))
        self.assertEqual((s.phase,s.successes),("OPEN",0))
    def test_clock_reversal(self):
        s=self.step(self.initial(),300)
        s=advance(s,observation("football",290),at(290))
        self.assertEqual(s.phase,"OPEN")
        self.assertEqual(s.last_checked,at(300))
    def test_stale_capture(self):
        s=advance(self.initial(),observation("football",0),at(301))
        self.assertEqual(s.phase,"OPEN")
    def test_too_fast(self):
        s=self.step(self.initial(),300);s=self.step(s,301)
        self.assertEqual(s.successes,1)
    def test_one_source_replay_despite_rising_minimum(self):
        s=self.initial()
        first=observation("football",300)
        first["source_evidence"][1]["captured_utc"]=at(330).isoformat()
        s=advance(s,first,at(330))
        second=observation("football",330)
        second["source_evidence"][0]["captured_utc"]=at(331).isoformat()
        s=advance(s,second,at(331))
        self.assertEqual((s.phase,s.successes),("OPEN",0))
    def test_fast_poll_does_not_starve_success(self):
        s=self.step(self.initial(),300)
        for t in (310,320,329,330):s=self.step(s,t)
        self.assertEqual(s.successes,2)
    def test_source_order_independent(self):
        s=self.step(self.initial(),300)
        x=observation("football",330);x["source_evidence"].reverse()
        s=advance(s,x,at(330))
        self.assertEqual(s.successes,2)
    def test_both_sources_need_spacing(self):
        s=self.step(self.initial(),300)
        x=observation("football",330)
        x["source_evidence"][1]["captured_utc"]=at(329).isoformat()
        s=advance(s,x,at(330))
        self.assertEqual(s.successes,1)
    def test_quant_same_safety(self):
        s=start("quant",NOW)
        for t in (300,330,360):s=self.step(s,t)
        self.assertEqual(s.phase,"HISTORICAL_RESEARCH_READY")
        r=snapshot(s)
        self.assertEqual((r["status"],r["live_trading"],r["production_recommendations"]),("HOLD","DISABLED","DISABLED"))
        self.assertFalse(r["model_input_allowed"]);self.assertFalse(r["automatic_failover_allowed"])
    def test_pre_cooldown_capture_cannot_recover(self):
        s=advance(self.initial(),observation("football",299),at(300))
        self.assertEqual(s.phase,"OPEN")

if __name__=="__main__":unittest.main(verbosity=2)
