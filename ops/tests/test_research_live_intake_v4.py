import json
import unittest
from ops.tests.test_research_unified_live_v2 import fixture,NOW
from ops.research_live_intake_v4 import intake,decode
from ops.research_live_evidence_v3 import verify_bundle

def inputs():
    s,p=fixture()
    policy={"schema":"live-intake-policy-v1","fixtures":{"synthetic":{"kickoff":s["kickoff"],
        "last_material_event":s["last_material_event"],"provider_ids":{}}},"adapters":{}}
    rows=[]
    def add(kind,record,i):
        adapter="adapter"+str(i)
        policy["adapters"][adapter]={"kinds":[kind],"source":"s"+str(i),"origin":"o"+str(i)}
        policy["fixtures"]["synthetic"]["provider_ids"][adapter]="id"+str(i)
        capture=record.get("captured",p["frozen_at"])
        payload={k:v for k,v in record.items() if k not in ("event_id","source","origin","captured","frozen_at")}
        if kind=="prior":payload["updated"]=p["frozen_at"]
        rows.append(dict(schema="live-adapter-envelope-v1",kind=kind,adapter=adapter,
                    provider_fixture_id="id"+str(i),captured_at=capture,payload=payload))
    for i,r in enumerate(s["score"]):add("score",r,i)
    for i,r in enumerate(s["stats"]):add("stats",r,i+2)
    add("quote",s["quote"],4);add("prior",p,5)
    return rows,policy
def run(rows,policy):
    return intake([json.dumps(r).encode() for r in rows],policy,event_id="synthetic",
                  as_of=NOW,model_release="synthetic")
class IntakeTests(unittest.TestCase):
    def test_valid(self):
        r,p=inputs(); out=run(r,p)
        self.assertTrue(out["structural_intake_passed"])
        self.assertTrue(verify_bundle(out["bundle"]))
        self.assertEqual(len(out["capture_bindings"]),6)
        self.assertFalse(out["eligible_for_training"])
    def test_bad_fixture(self):
        r,p=inputs();r[0]["provider_fixture_id"]="other"
        self.assertFalse(run(r,p)["structural_intake_passed"])
    def test_origin_override(self):
        r,p=inputs();r[0]["payload"]["origin"]="fake"
        self.assertFalse(run(r,p)["structural_intake_passed"])
    def test_shared_origin(self):
        r,p=inputs();p["adapters"]["adapter1"]["origin"]="o0"
        self.assertFalse(run(r,p)["structural_intake_passed"])
    def test_future_and_late_prior(self):
        for index in (0,5):
            r,p=inputs();r[index]["captured_at"]=NOW if index==5 else "2026-11-27T09:07:00Z"
            self.assertFalse(run(r,p)["structural_intake_passed"])
    def test_missing(self):
        r,p=inputs();self.assertFalse(run(r[:-1],p)["structural_intake_passed"])
    def test_duplicate_json(self):
        with self.assertRaises(ValueError):decode(b'{"a":1,"a":2}')
    def test_nan(self):
        with self.assertRaises(ValueError):decode(b'{"a":NaN}')
