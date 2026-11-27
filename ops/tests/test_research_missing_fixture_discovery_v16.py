import json
import unittest
from pathlib import Path
from datetime import datetime,timezone
from ops.tests.test_research_archive_score_recovery_v14 import fixture,encode
from ops.tests.test_research_two_publisher_recovery_v15 import secondary
from ops.research_missing_fixture_discovery_v16 import candidates,discover,secondary_snapshots

def raw_missing():
    raw,_=fixture();d=json.loads(raw);d["samples"][0].pop("source_fixture_identity")
    return encode(d)
def run(s):
    return discover(raw_missing(),[("one",encode(s))],as_of="2026-11-02T00:00:00Z")
class MissingIdentityTests(unittest.TestCase):
    def test_match(self):
        r=run(secondary())
        self.assertEqual(r["states"],{"FIXTURE_AND_OUTCOME_CANDIDATE":1})
        self.assertEqual(r["authenticated_samples"],0)
        self.assertFalse(r["ledger_backfill_allowed"])
    def test_kickoff_mismatch(self):
        s=secondary();s["sampled_fixtures"][0]["kickoff_utc"]="2026-11-01T15:01:00Z"
        self.assertEqual(run(s)["states"],{"NO_EXACT_FIXTURE_MATCH":1})
    def test_outcome_conflict(self):
        s=secondary();s["sampled_fixtures"][0]["score_ft"]=[0,1]
        self.assertEqual(run(s)["states"],{"RECORDED_OUTCOME_CONFLICT":1})
    def test_same_id_changed_identity(self):
        s=secondary();a=encode(s);s["sampled_fixtures"][0]["away"]="other"
        r=discover(raw_missing(),[("a",a),("b",encode(s))],as_of="2026-11-02T00:00:00Z")
        self.assertEqual(r["states"],{"AMBIGUOUS_OR_CONFLICTING":1})
    def test_existing_archive(self):
        root=Path(__file__).resolve().parents[2]
        ledger=root/"evidence/settled.json";raw=ledger.read_bytes()
        wanted={k:r for k,r in candidates(raw).items() if not r.get("source_fixture_identity")}
        r=discover(raw,secondary_snapshots(root/"sources/history",wanted),as_of=datetime.now(timezone.utc).isoformat())
        self.assertEqual(sum(r["states"].values()),len(wanted))
        self.assertEqual(r["authenticated_samples"],0)
        self.assertEqual(raw,ledger.read_bytes())
        print("V16_MISSING_ID_SUMMARY "+json.dumps({k:r[k] for k in ("ledger_rows","missing_identity_rows","snapshots_examined","invalid_snapshots","states","by_league","authenticated_samples")},sort_keys=True))
