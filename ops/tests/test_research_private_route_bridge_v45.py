import json
import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import patch
from ops.tests.test_research_private_propline_v43 import fixture,NOW
from ops.tests.test_research_prospective_market_v41 import fixture as primary_fixture
from ops.research_private_route_bridge_v45 import build,replay

def raw(d):return json.dumps(d).encode()
def target():
    r=fixture()
    return dict(league="epl",home=r["home_team"],away=r["away_team"],kickoff_utc=r["commence_time"])
def batches():
    return [dict(raw=raw({"events":[fixture()]}),league="epl",captured_utc=NOW.isoformat())]
def history():
    return raw({"schema":"private-fusion-history-v45","history":[]})
def primary():
    d=primary_fixture()
    d["as_of_utc"]=(NOW-timedelta(minutes=5)).isoformat()
    r=d["events"][0]
    r.update(kickoff_utc=target()["kickoff_utc"],market_last_update_utc=d["as_of_utc"],
             p_home=.39,p_draw=.28,p_away=.33)
    return raw(d)
class PrivateRouteBridgeTests(unittest.TestCase):
    def run_case(self,p=None,b=None,h=None,t=None):
        # Synthetic prospective clock is after registration, not the CI wall clock.
        # Retain every archive guard check; only freeze its wall clock in this test.
        with patch("ops.market_archive_guard.datetime", wraps=datetime) as clock:
            clock.now.return_value=NOW
            return build(p,batches() if b is None else b,history() if h is None else h,
                         target() if t is None else t,as_of=NOW.isoformat())
    def test_private_route_and_replay(self):
        r,s=self.run_case()
        self.assertEqual(s["private_receipts"],1)
        self.assertEqual(r["route"],"PRIVATE_BACKUP_ONLY")
        self.assertTrue(replay(r,None,batches(),history(),target()))
        self.assertEqual(r["fusion_receipt"]["candidate"]["weight"],0)
        self.assertEqual(r["authenticated_samples"],0)
        self.assertFalse(r["public_signer_allowed"])
        self.assertFalse(s["public_output_allowed"])
        self.assertNotIn("Arsenal",json.dumps(s))
        self.assertNotIn("fusion_receipt",s)
    def test_primary_preserved(self):
        r,s=self.run_case(p=primary())
        self.assertEqual(s["private_receipts"],1)
        self.assertEqual(r["route"],"PRIMARY_WITH_BACKUP_CONSISTENCY")
        self.assertEqual(r["fusion_receipt"]["market_p"],[.39,.28,.33])
    def test_conflict_no_receipt(self):
        d=json.loads(primary());d["events"][0].update(p_home=.8,p_draw=.1,p_away=.1)
        r,s=self.run_case(p=raw(d))
        self.assertIsNone(r)
        self.assertEqual(s["private_receipts"],0)
    def test_stale_no_receipt(self):
        b=batches();b[0]["captured_utc"]=(NOW-timedelta(minutes=21)).isoformat()
        self.assertIsNone(self.run_case(b=b)[0])
    def test_tampered_receipt_or_source(self):
        r,_=self.run_case()
        bad=deepcopy(r);bad["fusion_receipt"]["candidate"]["weight"]=.1
        self.assertFalse(replay(bad,None,batches(),history(),target()))
        b=batches();b[0]["raw"]+=b" "
        self.assertFalse(replay(r,None,b,history(),target()))
        self.assertFalse(replay(r,None,batches(),history()+b" ",target()))
    def test_no_target_match(self):
        t=target();t["away"]="Other"
        self.assertIsNone(self.run_case(t=t)[0])
    def test_outcome_field_rejected(self):
        t=target();t["score"]=[1,0]
        self.assertIsNone(self.run_case(t=t)[0])
    def test_history_clock_rejected(self):
        h=raw({"schema":"private-fusion-history-v45","history":[
            dict(league="epl",home="Arsenal",away="Other",
                 kickoff_utc=(NOW-timedelta(hours=4)).isoformat(),
                 observed_utc=(NOW-timedelta(hours=2)).isoformat(),score=[1,0],
                 source_id="test",fixture_id="past",evidence_sha256="a"*64)]})
        self.assertIsNone(self.run_case(h=h)[0])
