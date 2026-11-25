import json,unittest
from datetime import datetime,timezone,timedelta
from ops.v9_market_research import audit,choose,evaluate,load
NOW=datetime(2026,11,25,tzinfo=timezone.utc)
def row(i=0,y=0):
    ko=datetime(2026,10,1,tzinfo=timezone.utc)+timedelta(days=i%10,hours=12)
    return {"key":json.dumps(["epl",str(i),"away",ko.isoformat()]),"league":"epl","kickoff_utc":ko.isoformat(),
        "forecast_utc":(ko-timedelta(hours=1)).isoformat(),"market_utc":(ko-timedelta(hours=2)).isoformat(),
        "y":y,"p":[.6,.2,.2],"m":[.4,.3,.3],"production_recommendations":"DISABLED","fixture_result_source_independently_verified":False}
class MarketTests(unittest.TestCase):
    def test_pin(self):
        with self.assertRaisesRegex(ValueError,"PINNED"):load(b"{}")
    def test_clock(self):
        r=row();r["market_utc"]=r["kickoff_utc"]
        self.assertEqual(audit([r],NOW)[1],{"CLOCK":1})
    def test_stale(self):
        r=row();r["market_utc"]="2026-09-01T00:00:00Z"
        self.assertEqual(audit([r],NOW)[1],{"RESEARCH_STALE":1})
    def test_duplicate(self):
        r=row();self.assertEqual(audit([r,r],NOW)[1],{"DUPLICATE":2})
    def test_weight(self):
        a,_=audit([row(i) for i in range(100)],NOW)
        self.assertEqual(choose(a),0.)
    def test_no_assessment_leakage(self):
        a,_=audit([row(i) for i in range(100)],NOW)
        r=evaluate(a);b=[dict(x,y=2) if x["kickoff"][:10]>=r["cutoff_utc_day"] else x for x in a]
        self.assertEqual(r["chosen_weight"],evaluate(b)["chosen_weight"])
