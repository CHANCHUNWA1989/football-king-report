import json
import unittest
from pathlib import Path
from ops.tests.test_research_candidate_gap_v6 import data
from ops.research_archive_score_recovery_v14 import compare,targets,archive_snapshots

def fixture():
    d=data();r=d["samples"][0];r.update(league="bundesliga",key=json.dumps(["bundesliga","a","b",r["kickoff_utc"]]),
        source_fixture_identity={"provider":"OpenLigaDB","match_id":"123"})
    snap=dict(schema="football-king-openligadb-hourly-v1",source="OpenLigaDB",production_recommendations="DISABLED",
        collected_utc="2026-11-01T18:00:00Z",matches=[dict(league="bundesliga",home="a",away="b",provider_match_id=123,
        kickoff_utc=r["kickoff_utc"],status="FINISHED_CONFIRMED_BY_SOURCE",score_ft=[2,1])])
    return json.dumps(d).encode(),snap
def encode(d):return json.dumps(d).encode()
class ArchiveRecoveryTests(unittest.TestCase):
    def test_agreement(self):
        raw,s=fixture();r=compare(raw,[("a",encode(s)),("b",encode(s))])
        self.assertEqual(r["states"],{"SINGLE_PUBLISHER_OUTCOME_AGREEMENT":1})
        self.assertEqual(len(r["cases"][0]["observations"]),1)
        self.assertEqual(r["authenticated_samples"],0)
    def test_conflict(self):
        raw,s=fixture();one=encode(s);s["matches"][0]["score_ft"]=[3,1]
        self.assertEqual(compare(raw,[("a",one),("b",encode(s))])["states"],{"CONFLICT_REVIEW":1})
    def test_wrong_identity(self):
        raw,s=fixture();s["matches"][0]["away"]="other"
        self.assertEqual(compare(raw,[("a",encode(s))])["states"],{"CONFLICT_REVIEW":1})
    def test_wrong_outcome(self):
        raw,s=fixture();s["matches"][0]["score_ft"]=[0,1]
        self.assertEqual(compare(raw,[("a",encode(s))])["states"],{"OUTCOME_CONFLICT_REVIEW":1})
    def test_existing_archive_read_only(self):
        root=Path(__file__).resolve().parents[2]
        ledger=root/"evidence/settled.json"
        raw=ledger.read_bytes()
        wanted=targets(raw)
        result=compare(raw,archive_snapshots(root/"sources/live_germany/history",wanted))
        self.assertEqual(sum(result["states"].values()),len(wanted))
        self.assertEqual(result["authenticated_samples"],0)
        self.assertEqual(ledger.read_bytes(),raw)
        print("V14_ARCHIVE_RECOVERY_SUMMARY "+json.dumps({k:result[k] for k in ("fixed_id_candidates","snapshots_examined","invalid_snapshots","states","authenticated_samples")},sort_keys=True))
