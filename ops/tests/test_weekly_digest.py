"""No fabricated weekly metric when no settled forecast + outcome exists."""
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from weekly_digest import digest,to_markdown

class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,9,5,tzinfo=timezone.utc)
        self.evidence={"n":0,"samples":[],"production_recommendations":"DISABLED"}
        self.market={"as_of_utc":self.now.isoformat(),
                     "quota":{"remaining":480},
                     "production_recommendations":"DISABLED"}

    def test_missing_samples_no_accuracy_claims(self):
        d=digest(self.evidence,self.market,self.now)
        self.assertEqual(d["last_7d_settled"],0)
        self.assertIsNone(d["model_vs_market"])
        m=to_markdown(d)
        self.assertIn("HOLD / DISABLED",m)
        self.assertIn("—",m)

    def test_bad_evidence_n_rejected(self):
        self.evidence["n"]=3
        with self.assertRaisesRegex(ValueError,"MISMATCHED_WEEKLY_SAMPLES"):
            digest(self.evidence,self.market,self.now)

    def test_quota_warning_near_floor(self):
        self.market["quota"]["remaining"]=140
        self.assertTrue(any("額度" in x or "餘額" in x for x in
                            digest(self.evidence,self.market,self.now)["warnings"]))

    def test_no_unsafe_evidence(self):
        self.market["production_recommendations"]="ENABLED"
        with self.assertRaisesRegex(ValueError,"UNSAFE_WEEKLY_MARKET"):
            digest(self.evidence,self.market,self.now)

if __name__=="__main__":
    unittest.main()
