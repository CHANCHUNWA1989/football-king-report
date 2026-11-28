import copy
import unittest
from datetime import datetime,timezone
from evidence_intake import intake,URLS,EXPECTED
NOW=datetime(2026,11,28,tzinfo=timezone.utc)
def doc(domain):
    x={"status":"HOLD","historical_only":True,"production_recommendations":"DISABLED",
       "source_evidence":[{"url":u,"bytes":100,"sha256":str(i+1)*64,"captured_utc":NOW.isoformat()} for i,u in enumerate(sorted(URLS[domain]))]}
    if domain=="football":
        x.update(independent_upstream_certified=False,matched=7,expected=7,rows=[{"match_id":i,"score_a":[2,1],"score_b":[2,1],"status":"HISTORICAL_MATCH"} for i in sorted(EXPECTED)])
    else:
        x.update(live_trading="DISABLED",same_fixing_time=False,comparison="DIFFERENT_FIXING_TIMES_RESEARCH_ONLY",ecb_usd_per_eur="1.20",fed_usd_per_eur="1.21",relative_difference_bps="83.33")
    return x
class Tests(unittest.TestCase):
    def check_hold(self,r,accepted):
        self.assertEqual(r["status"],"HOLD")
        self.assertFalse(r["model_input_allowed"])
        self.assertFalse(r["raw_body_verified"])
        self.assertEqual(r["live_trading"],"DISABLED")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertIs(r["evidence_metadata_accepted"],accepted)
    def test_good_both(self):
        for domain in URLS:self.check_hold(intake(doc(domain),domain,NOW),True)
    def test_flags(self):
        for key,value in (("status","LIVE"),("historical_only",False),("production_recommendations","ENABLED"),("independent_upstream_certified",True)):
            x=doc("football");x[key]=value;self.check_hold(intake(x,"football",NOW),False)
    def test_sources(self):
        for key,value in (("sha256","bogus"),("bytes",True),("captured_utc","2030-01-01T00:00:00Z"),("url","https://fake.example")):
            x=doc("football");x["source_evidence"][0][key]=value;self.check_hold(intake(x,"football",NOW),False)
    def test_duplicate_source(self):
        x=doc("football");x["source_evidence"][1]=copy.deepcopy(x["source_evidence"][0]);self.check_hold(intake(x,"football",NOW),False)
    def test_duplicate_match(self):
        x=doc("football");x["rows"][1]=copy.deepcopy(x["rows"][0]);self.check_hold(intake(x,"football",NOW),False)
    def test_conflict(self):
        x=doc("football");x["rows"][0]["score_b"]=[0,0];self.check_hold(intake(x,"football",NOW),False)
    def test_bool_score(self):
        x=doc("football");x["rows"][0]["score_b"]=[True,1];self.check_hold(intake(x,"football",NOW),False)
    def test_fx_fixing_and_difference(self):
        for k,v in (("same_fixing_time",True),("relative_difference_bps","0"),("fed_usd_per_eur","NaN"),("live_trading","ENABLED")):
            x=doc("quant");x[k]=v;self.check_hold(intake(x,"quant",NOW),False)
    def test_duplicate_body_digest(self):
        x=doc("football");x["source_evidence"][1]["sha256"]=x["source_evidence"][0]["sha256"];self.check_hold(intake(x,"football",NOW),False)
    def test_unsupported_claims(self):
        for key in ("model_input_allowed","raw_body_verified","independent_upstream_certified"):
            x=doc("quant");x[key]=True;self.check_hold(intake(x,"quant",NOW),False)
    def test_float_match_identity(self):
        x=doc("football");x["rows"][0]["match_id"]=float(x["rows"][0]["match_id"]);self.check_hold(intake(x,"football",NOW),False)
    def test_unsafe_football_trade_flag(self):
        x=doc("football");x["live_trading"]="ENABLED";self.check_hold(intake(x,"football",NOW),False)
    def test_error_never_accepted(self):
        x=doc("football");x["error_type"]="TimeoutError";self.check_hold(intake(x,"football",NOW),False)
if __name__=="__main__":unittest.main(verbosity=2)
