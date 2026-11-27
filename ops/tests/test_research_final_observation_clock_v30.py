import json
import unittest
from pathlib import Path
from datetime import datetime,timezone
from ops.tests.test_research_archive_score_recovery_v14 import fixture,encode
from ops.tests.test_research_missing_fixture_discovery_v16 import raw_missing
from ops.tests.test_research_two_publisher_recovery_v15 import secondary
from ops.research_final_observation_clock_v30 import recover,from_root
NOW="2026-11-02T00:00:00Z"
class FinalObservationClockTests(unittest.TestCase):
    def test_dual_uses_later_final(self):
        raw,p=fixture()
        r=recover(raw,[("p",encode(p))],[("s",encode(secondary()))],as_of=NOW)
        self.assertEqual(r["states"],{"TWO_PUBLISHER_FINAL_CLOCK_CANDIDATE":1})
        self.assertEqual(r["cases"][0]["recorded_final_observation_utc"],"2026-11-01T18:01:00+00:00")
        self.assertFalse(r["training_admission"])
    def test_unpinned_dual(self):
        _,p=fixture()
        r=recover(raw_missing(),[("p",encode(p))],[("s",encode(secondary()))],as_of=NOW)
        self.assertEqual(r["states"],{"TWO_PUBLISHER_FINAL_CLOCK_CANDIDATE":1})
    def test_pre_final_not_used(self):
        s=secondary();s["sampled_fixtures"][0]["status"]="SCHEDULED";s["sampled_fixtures"][0]["score_ft"]=None
        s["started_utc"]="2026-11-01T12:00:00Z";s["collected_utc"]="2026-11-01T12:01:00Z"
        r=recover(raw_missing(),[],[("before",encode(s)),("final",encode(secondary()))],as_of=NOW)
        self.assertEqual(r["cases"][0]["recorded_final_observation_utc"],"2026-11-01T18:01:00+00:00")
        self.assertEqual(r["cases"][0]["references"][0]["path"],"final")
    def test_conflict_rejected(self):
        raw,p=fixture();s=secondary();s["sampled_fixtures"][0]["score_ft"]=[3,1]
        r=recover(raw,[("p",encode(p))],[("s",encode(s))],as_of=NOW)
        self.assertIsNone(r["cases"][0]["recorded_final_observation_utc"])
    def test_future_rejected(self):
        _,p=fixture();p["collected_utc"]="2026-11-03T00:00:00Z"
        r=recover(raw_missing(),[("p",encode(p))],[],as_of=NOW)
        self.assertIsNone(r["cases"][0]["recorded_final_observation_utc"])
    def test_actual_archive(self):
        root=Path(__file__).resolve().parents[2]
        ledger=root/"evidence/settled.json";raw=ledger.read_bytes()
        r=from_root(root,as_of=datetime.now(timezone.utc).isoformat())
        self.assertEqual(sum(r["states"].values()),r["ledger_rows"])
        self.assertEqual(r["authenticated_samples"],0)
        self.assertEqual(raw,ledger.read_bytes())
        print("V30_FINAL_CLOCK_SUMMARY "+json.dumps({k:r[k] for k in ("ledger_rows","states","invalid_referenced_snapshots","authenticated_samples","training_admission")},sort_keys=True))
