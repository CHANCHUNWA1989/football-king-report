import unittest
from scripts.evidence_audit_v2 import audit

def row():
    return {"key":"fixture1","kickoff_utc":"2026-10-14T18:00:00+00:00",
        "forecast_utc":"2026-10-14T10:00:00+00:00",
        "market_utc":"2026-10-14T09:00:00+00:00",
        "y":0,"p":[0.5,0.3,0.2],"m":[0.4,0.3,0.3],
        "production_recommendations":"DISABLED",
        "fixture_result_source_independently_verified":False}

class AuditTests(unittest.TestCase):
    def test_valid(self):
        report=audit({"samples":[row()]})
        self.assertEqual(report["sample_count"],1)
        self.assertEqual(report["independently_verified_count"],0)
        self.assertFalse(report["promotion_eligible"])
    def test_postkickoff_rejected(self):
        x=row();x["forecast_utc"]=x["kickoff_utc"]
        self.assertEqual(len(audit({"samples":[x]})["errors"]),1)
    def test_duplicate_rejected(self):
        x=row()
        self.assertEqual(len(audit({"samples":[x,x]})["errors"]),1)
    def test_flag_rejected(self):
        x=row();x["production_recommendations"]="ENABLED"
        self.assertEqual(len(audit({"samples":[x]})["errors"]),1)

if __name__=="__main__":
    unittest.main()
