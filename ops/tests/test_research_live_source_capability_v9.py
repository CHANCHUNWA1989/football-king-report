import unittest
from ops.research_live_source_capability_v9 import audit,REPORTS,EXPECTED
NOW="2026-11-27T10:00:00Z"
def reports():
    docs={}
    for name,(_,schema,clock) in REPORTS.items():
        d=dict(schema=schema,production_recommendations="DISABLED",status="RESEARCH_ONLY")
        d[clock]="2026-11-27T09:00:00Z"
        if name in EXPECTED:
            d["providers"]=[dict(provider=p,status="AVAILABLE") for p in EXPECTED[name]]
        elif name=="germany":d["source"]="OpenLigaDB"
        else:d["provider"]={"market":"propline","bsd":"bzzoiro_sports_data","hkjc":"tipsme_hkjc_third_party"}[name]
        docs[name]=d
    return docs
class CapabilityTests(unittest.TestCase):
    def test_reports_do_not_promote(self):
        r=audit(reports(),as_of=NOW)
        self.assertEqual(len(r["providers"]),10)
        self.assertEqual(r["live_xg_origins_verified"],0)
        self.assertFalse(r["live_training_eligible"])
        self.assertEqual(r["status"],"HOLD")
    def test_stale_future_and_unsafe(self):
        for stamp in ("2026-11-25T00:00:00Z","2026-11-28T00:00:00Z"):
            d=reports();d["extra"]["collected_utc"]=stamp
            self.assertNotIn("api_football",audit(d,as_of=NOW)["providers"])
        d=reports();d["extra"]["production_recommendations"]="ENABLED"
        self.assertNotIn("api_football",audit(d,as_of=NOW)["providers"])
    def test_roster(self):
        d=reports();d["extra"]["providers"].append(d["extra"]["providers"][0])
        self.assertNotIn("api_football",audit(d,as_of=NOW)["providers"])
    def test_reported_capability_not_authentication(self):
        d=reports();d["market"]["executable_live_quotes_verified"]=100
        self.assertEqual(audit(d,as_of=NOW)["executable_live_quotes_verified"],0)
    def test_missing(self):
        r=audit({},as_of=NOW)
        self.assertEqual(len(r["providers"]),0)
        self.assertEqual(len(r["reports"]),6)
