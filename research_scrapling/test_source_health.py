"""Synthetic health states; no actual network or failover activation."""
import unittest
from datetime import timedelta
from source_health import assess
from test_evidence_intake import doc,NOW

class HealthTests(unittest.TestCase):
    def check_safety(self,r):
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["live_trading"],"DISABLED")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertFalse(r["model_input_allowed"])
        self.assertFalse(r["automatic_failover_allowed"])
    def test_good_historical(self):
        for domain in ("football","quant"):
            r=assess(domain,doc(domain),NOW)
            self.check_safety(r)
            self.assertEqual(r["health"],"HISTORICAL_METADATA_OK")
    def test_stale(self):
        r=assess("football",doc("football"),NOW+timedelta(seconds=301))
        self.check_safety(r)
        self.assertEqual(r["health"],"DEGRADED_HOLD")
        self.assertTrue(all(x["state"]=="STALE_CAPTURE" for x in r["sources"]))
    def test_missing(self):
        r=assess("quant",{},NOW);self.check_safety(r)
        self.assertEqual(r["health"],"DEGRADED_HOLD")
    def test_duplicate(self):
        x=doc("football");x["source_evidence"].append(x["source_evidence"][0])
        r=assess("football",x,NOW);self.check_safety(r)
        self.assertIn("DUPLICATE_SOURCE",[s["state"] for s in r["sources"]])
    def test_future(self):
        r=assess("quant",doc("quant"),NOW-timedelta(seconds=1))
        self.check_safety(r)
        self.assertTrue(all(x["state"]=="FUTURE_CAPTURE" for x in r["sources"]))
    def test_conflict(self):
        x=doc("football");x["rows"][0]["score_b"]=[0,0]
        r=assess("football",x,NOW);self.check_safety(r)
        self.assertEqual(r["health"],"DEGRADED_HOLD")
        self.assertTrue(all(s["state"]=="UNVERIFIED_CAPTURE" for s in r["sources"]))
    def test_single_source_never_authorizes(self):
        x=doc("quant");x["source_evidence"].pop()
        r=assess("quant",x,NOW);self.check_safety(r)
        self.assertEqual(r["health"],"DEGRADED_HOLD")
    def test_exact_age_boundary(self):
        r=assess("quant",doc("quant"),NOW+timedelta(seconds=300))
        self.check_safety(r)
        self.assertEqual(r["health"],"HISTORICAL_METADATA_OK")

if __name__=="__main__":unittest.main(verbosity=2)
