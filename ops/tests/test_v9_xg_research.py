import unittest,json
from datetime import datetime,timezone,timedelta
from ops.v9_xg_research import load,sha,replay,build
NOW=datetime(2026,11,26,tzinfo=timezone.utc)
def row():
    return {"match_id":1,"home_id":2,"away_id":3,"kickoff_utc":"2026-10-01T12:00:00Z","xg_available_utc":"2026-10-01T15:00:00Z","phase":"REGULATION","status":"FINISHED","home_goals":2,"away_goals":0,"home_xg":1.3,"away_xg":.5,"xg_kind":"PROVIDER_PRE_SHOT_XG","metric_definition":"test-only"}
def inputs(rows):
    raw=json.dumps({"schema":"v9-1-historical-xg-matches-v1","provider":"synthetic","matches":rows}).encode()
    return raw,{"schema":"v9-1-authorized-xg-receipt-v1","sha256":sha(raw),"provider":"synthetic","metric_definition":"test-only","authorization_reference":"synthetic unit test","captured_utc":NOW.isoformat()}
class XGTests(unittest.TestCase):
    def test_valid_unqualified(self):
        r=build(load(*inputs([row()]),NOW))
        self.assertEqual(r["paired_matches"],0);self.assertFalse(r["authorization_independently_verified"])
    def test_bad_digest(self):
        a,b=inputs([row()])
        with self.assertRaisesRegex(ValueError,"INTEGRITY"):load(a+b" ",b,NOW)
    def test_missing_xg(self):
        r=row();r["home_xg"]=None
        with self.assertRaisesRegex(ValueError,"INVALID_NUMBER"):load(*inputs([r]),NOW)
    def test_wrong_metric(self):
        r=row();r["xg_kind"]="ESTIMATED_FROM_GOALS"
        with self.assertRaisesRegex(ValueError,"XG_DEFINITION"):load(*inputs([r]),NOW)
    def test_future(self):
        r=row();r["xg_available_utc"]="2027-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError,"XG_CLOCK"):load(*inputs([r]),NOW)
    def test_no_same_day_leakage(self):
        a=[]
        for i in range(22):
            d=NOW-timedelta(days=40-i)
            a.append({"id":str(i),"home":"2","away":"3","ko":d,"available":d+timedelta(hours=3),"goals":(2,1),"xg":(1.4,.8)})
        a.append(dict(a[-1],id="23",ko=a[-1]["ko"]+timedelta(hours=6)))
        b=[dict(r) for r in a];b[-2]["xg"]=(9.,0.)
        self.assertEqual(replay(a)[-1]["candidate"],replay(b)[-1]["candidate"])
