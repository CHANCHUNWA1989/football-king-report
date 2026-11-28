import json
import unittest
from datetime import datetime,timezone
from pathlib import Path
from ops.tests.test_research_archive_score_recovery_v14 import fixture,encode
from ops.tests.test_research_missing_fixture_discovery_v16 import raw_missing
from ops.tests.test_research_two_publisher_recovery_v15 import secondary
from ops.research_historical_evidence_triage_v17 import review,from_root

NOW="2026-11-02T00:00:00Z"
class UnifiedTriageTests(unittest.TestCase):
    def test_two_sources_not_double_counted(self):
        raw,p=fixture()
        r=review(raw,[("p",encode(p))],[("s",encode(secondary()))],as_of=NOW)
        self.assertEqual(r["states"],{"TWO_PUBLISHER_SCORE_AGREEMENT":1})
        self.assertEqual(r["outcome_corroborated_candidates"],1)
        self.assertEqual(r["authenticated_samples"],0)
        self.assertFalse(r["model_promotion_allowed"])
    def test_discovery(self):
        r=review(raw_missing(),[],[("s",encode(secondary()))],as_of=NOW)
        self.assertEqual(r["states"],{"ONE_PUBLISHER_OUTCOME_AGREEMENT":1})
        self.assertIn("RECOVER_SECOND_PUBLISHER_SCORE",r["cases"][0]["blockers"])
    def test_conflict(self):
        raw,p=fixture();s=secondary();s["sampled_fixtures"][0]["score_ft"]=[3,1]
        r=review(raw,[("p",encode(p))],[("s",encode(s))],as_of=NOW)
        self.assertEqual(r["states"],{"CONFLICT_REVIEW":1})
        self.assertEqual(r["outcome_corroborated_candidates"],0)
    def test_future_primary(self):
        raw,p=fixture();p["collected_utc"]="2026-11-03T00:00:00Z"
        r=review(raw,[("p",encode(p))],[],as_of=NOW)
        self.assertEqual(r["invalid_primary_snapshots"],1)
        self.assertEqual(r["states"],{"FIXED_ID_RESULT_MISSING":1})
    def test_actual_archives(self):
        root=Path(__file__).resolve().parents[2]
        ledger=root/"evidence/settled.json";raw=ledger.read_bytes()
        r=from_root(root,as_of=datetime.now(timezone.utc).isoformat())
        self.assertEqual(sum(r["states"].values()),r["ledger_rows"])
        self.assertEqual(len({x["key"] for x in r["cases"]}),r["ledger_rows"])
        self.assertEqual(r["authenticated_samples"],0)
        self.assertEqual(raw,ledger.read_bytes())
        print("V17_UNIFIED_EVIDENCE_SUMMARY "+json.dumps({k:r[k] for k in ("ledger_rows","states","outcome_corroborated_candidates","primary_snapshots_examined","secondary_snapshots_examined","invalid_primary_snapshots","invalid_secondary_snapshots","blocker_counts","authenticated_samples")},sort_keys=True))
