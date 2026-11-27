import json
import unittest
from copy import deepcopy
from ops.research_private_full_replay import recheck
from ops.research_private_run_store_v48 import encode_run,verify_run
from ops.research_integrated_fusion_v45 import prepare
from ops.tests.test_research_archive_score_recovery_v14 import fixture,encode
from ops.tests.test_research_private_propline_v43 import fixture as market_fixture,NOW

def inputs(two=False):
    ledger,p=fixture()
    m=market_fixture()
    events=[m]
    if two:
        other=deepcopy(m)
        other["id"]="other-fixture"
        other["away_team"]="Liverpool"
        for b in other["bookmakers"]:
            for o in b["markets"][0]["outcomes"]:
                if o["name"]==m["away_team"]:o["name"]="Liverpool"
        events.append(other)
    batch={"raw":encode({"events":events}),"league":"epl","captured_utc":NOW.isoformat()}
    archives=[("p",encode(p))]
    packets,_=prepare(ledger,archives,[],None,[batch],as_of=NOW.isoformat(),include_supplemental=True)
    return ledger,archives,batch,packets

class PrivateFullReplayTests(unittest.TestCase):
    def test_exact_reconstruction(self):
        ledger,a,b,p=inputs()
        r=recheck(encode_run(b,p),ledger,a,[],include_supplemental=True)
        self.assertTrue(r["historical_reference_bytes_rechecked"])
        self.assertTrue(r["supplied_input_roster_reproduced"])
        self.assertFalse(r["cohort_completeness_proven"])
        self.assertEqual(r["authenticated_samples"],0)
    def test_missing_archive(self):
        ledger,a,b,p=inputs()
        with self.assertRaises(ValueError):
            recheck(encode_run(b,p),ledger,[],[],include_supplemental=True)
    def test_changed_archive(self):
        ledger,a,b,p=inputs()
        d=json.loads(a[0][1]);d["matches"][0]["score_ft"]=[3,1]
        with self.assertRaises(ValueError):
            recheck(encode_run(b,p),ledger,[("p",encode(d))],[],include_supplemental=True)
    def test_omitted_prediction(self):
        ledger,a,b,p=inputs(two=True)
        self.assertEqual(len(p),2)
        raw=encode_run(b,p[:1])
        self.assertTrue(verify_run(raw)["local_replay_verified"])
        with self.assertRaises(ValueError):
            recheck(raw,ledger,a,[],include_supplemental=True)
    def test_invalid_mode(self):
        ledger,a,b,p=inputs()
        with self.assertRaises(ValueError):
            recheck(encode_run(b,p),ledger,a,[],include_supplemental=1)
