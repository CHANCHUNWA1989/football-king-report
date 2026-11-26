import unittest
from copy import deepcopy
from ops.live_evidence_contract_20261126 import audit_evidence

NOW="2026-11-26T22:47:00+08:00"
REG={"a":("up1","x1"),"b":("up2","x2"),"c":("up1","x3")}

def row(provider="a", external="x1", **kw):
    d=dict(provider=provider,provider_fixture_id=external,fixture_id="match",
           event_at="2026-11-26T22:46:30+08:00",observed_at="2026-11-26T22:46:40+08:00",
           period="FIRST_HALF",minute=45,score=[0,0],red_cards=[0,0])
    d.update(kw)
    return d

def check(rows, **kw):
    return audit_evidence(rows,REG,"match",NOW,**kw)

class EvidenceTests(unittest.TestCase):
    def test_structural_only(self):
        r=check([row(),row("b","x2")])
        self.assertTrue(r["structural_match"])
        for k in ("source_attestation_verified","positive_ev_verified","qualified"):
            self.assertFalse(r[k])
        self.assertEqual(r["deployment"],"HOLD")
    def test_alias_and_duplicates(self):
        self.assertIn("INDEPENDENT_UPSTREAMS_MISSING",check([row(),row("c","x3")])["reasons"])
        self.assertIn("DUPLICATE_PROVIDER",check([row(),row(),row("b","x2")])["reasons"])
    def test_conflicts(self):
        for patch, reason in [
            ({"score":[0,1]},"STATE_CONFLICT"),
            ({"red_cards":[1,0]},"STATE_CONFLICT"),
            ({"period":"SECOND_HALF"},"STATE_CONFLICT"),
            ({"minute":48},"CLOCK_CONFLICT"),
            ({"fixture_id":"other"},"FIXTURE_MISMATCH"),
            ({"provider_fixture_id":"other"},"FIXTURE_MISMATCH"),
            ({"event_at":"2026-11-26T22:45:59+08:00"},"STALE_OR_FUTURE_EVIDENCE"),
            ({"observed_at":"2026-11-26T22:47:01+08:00"},"STALE_OR_FUTURE_EVIDENCE"),
            ({"event_at":"2026-11-26T22:46:30"},"INVALID_TIMESTAMP"),
            ({"minute":True},"INVALID_CLOCK"),
            ({"period":[]},"INVALID_CLOCK"),
            ({"red_cards":[0,True]},"INVALID_SCORE_OR_RED_CARDS"),
        ]:
            b=row("b","x2"); b.update(patch)
            with self.subTest(patch=patch):
                r=check([row(),b])
                self.assertIn(reason,r["reasons"])
                self.assertFalse(r["structural_match"])
    def test_regression(self):
        r=check([row(),row("b","x2")],previous={"minute":44,"score":[1,0],"red_cards":[0,0]})
        self.assertIn("STATE_REGRESSION_REQUIRES_REVIEW",r["reasons"])
    def test_bad_inputs(self):
        for rows in (None,{},[None],[row(provider=[])],[]):
            with self.subTest(rows=rows):
                self.assertFalse(check(rows)["structural_match"])
    def test_exhaustive_state_agreement(self):
        states=[(h,a,rh,ra,m) for h in range(3) for a in range(3)
                for rh in range(2) for ra in range(2) for m in (44,45,48)]
        for h,a,rh,ra,m in states:
            for j,k,s,t,n in states:
                x=row(score=[h,a],red_cards=[rh,ra],minute=m)
                y=row("b","x2",score=[j,k],red_cards=[s,t],minute=n)
                r=check([x,y])
                expected=(h,a,rh,ra)==(j,k,s,t) and abs(m-n)<=2
                self.assertEqual(r["structural_match"],expected)
                self.assertFalse(r["qualified"])

if __name__=="__main__": unittest.main()
