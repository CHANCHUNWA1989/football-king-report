import json
import unittest
from datetime import datetime,timezone
from pathlib import Path
from ops.tests.test_research_archive_score_recovery_v14 import fixture,encode
from ops.tests.test_research_missing_fixture_discovery_v16 import raw_missing
from ops.tests.test_research_two_publisher_recovery_v15 import secondary
from ops.research_german_archive_discovery_v18 import extend,from_root

NOW="2026-11-02T00:00:00Z"
def run(primary,second=()):
    return extend(raw_missing(),primary,second,as_of=NOW)
class GermanDiscoveryTests(unittest.TestCase):
    def test_both(self):
        _,p=fixture()
        r=run([("p",encode(p))],[("s",encode(secondary()))])
        self.assertEqual(r["states"],{"TWO_PUBLISHER_SCORE_AGREEMENT":1})
        self.assertEqual(r["authenticated_samples"],0)
        self.assertFalse(r["ledger_backfill_allowed"])
    def test_primary_only(self):
        _,p=fixture()
        self.assertEqual(run([("p",encode(p))])["states"],{"ONE_PUBLISHER_OUTCOME_AGREEMENT":1})
    def test_exact_score_conflict(self):
        _,p=fixture();s=secondary();s["sampled_fixtures"][0]["score_ft"]=[3,1]
        self.assertEqual(run([("p",encode(p))],[("s",encode(s))])["states"],{"CONFLICT_REVIEW":1})
    def test_id_reuse(self):
        _,p=fixture();a=encode(p);p["matches"][0]["away"]="other"
        self.assertEqual(run([("a",a),("b",encode(p))])["states"],{"CONFLICT_REVIEW":1})
    def test_future_report(self):
        _,p=fixture();p["collected_utc"]="2026-11-03T00:00:00Z"
        self.assertEqual(run([("p",encode(p))])["states"],{"NO_EXACT_FIXTURE_MATCH":1})
    def test_actual_archives(self):
        root=Path(__file__).resolve().parents[2]
        ledger=root/"evidence/settled.json";raw=ledger.read_bytes()
        r=from_root(root,as_of=datetime.now(timezone.utc).isoformat())
        self.assertEqual(sum(r["states"].values()),r["ledger_rows"])
        self.assertEqual(r["authenticated_samples"],0)
        self.assertEqual(ledger.read_bytes(),raw)
        print("V18_GERMAN_DISCOVERY_SUMMARY "+json.dumps({k:r[k] for k in ("ledger_rows","states","outcome_corroborated_candidates","primary_discovery_targets","primary_discovery_states","primary_discovery_invalid_snapshots","primary_snapshots_examined","secondary_snapshots_examined","authenticated_samples")},sort_keys=True))
