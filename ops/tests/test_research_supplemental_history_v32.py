import json
import unittest
from datetime import datetime,timezone
from pathlib import Path
from ops.tests.test_research_archive_score_recovery_v14 import fixture,encode
from ops.research_supplemental_history_v32 import inventory,from_root

NOW="2026-11-02T00:00:00Z"
def earlier():
    raw,p=fixture()
    p["collected_utc"]="2026-10-31T18:00:00Z"
    p["matches"]=[dict(league="bundesliga",home="a",away="c",provider_match_id=124,
        kickoff_utc="2026-10-31T15:00:00Z",status="FINISHED_CONFIRMED_BY_SOURCE",score_ft=[1,0])]
    return raw,p

class SupplementalHistoryTests(unittest.TestCase):
    def test_extra_prior_not_forecast_sample(self):
        raw,p=earlier()
        r=inventory(raw,[("earlier",encode(p))],[],as_of=NOW)
        self.assertEqual(r["extra_prior_candidates"],1)
        self.assertEqual(r["authenticated_samples"],0)
        self.assertFalse(r["training_admission"])
    def test_exclude_ledger_pair_even_different_kickoff(self):
        raw,p=earlier();p["matches"][0]["away"]="b"
        r=inventory(raw,[("earlier",encode(p))],[],as_of=NOW)
        self.assertEqual(r["extra_prior_candidates"],0)
        self.assertEqual(r["excluded"]["LEDGER_PAIR_OR_POSSIBLE_RESCHEDULE"],1)
    def test_conflicting_score(self):
        raw,p=earlier();a=encode(p);p["matches"][0]["score_ft"]=[2,0]
        r=inventory(raw,[("a",a),("b",encode(p))],[],as_of=NOW)
        self.assertEqual(r["extra_prior_candidates"],0)
    def test_id_reuse(self):
        raw,p=earlier();a=encode(p);p["matches"][0]["away"]="d"
        r=inventory(raw,[("a",a),("b",encode(p))],[],as_of=NOW)
        self.assertEqual(r["extra_prior_candidates"],0)
    def test_future_capture(self):
        raw,p=earlier();p["collected_utc"]="2026-11-03T00:00:00Z"
        self.assertEqual(inventory(raw,[("a",encode(p))],[],as_of=NOW)["extra_prior_candidates"],0)
    def test_actual_archives(self):
        root=Path(__file__).resolve().parents[2];ledger=root/"evidence/settled.json";raw=ledger.read_bytes()
        r=from_root(root,as_of=datetime.now(timezone.utc).isoformat())
        self.assertEqual(ledger.read_bytes(),raw)
        self.assertEqual(r["authenticated_samples"],0)
        self.assertFalse(r["weights_fitted"])
        for s in r["scenarios"].values():
            for k,n in s["original"].items():self.assertGreaterEqual(s["expanded"][k],n)
        print("V32_SUPPLEMENTAL_HISTORY_SUMMARY "+json.dumps(r,sort_keys=True))
