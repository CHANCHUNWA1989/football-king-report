import json
import unittest
from datetime import datetime,timezone
from pathlib import Path
from ops.tests.test_research_candidate_gap_v6 import data
from ops.research_forecast_proof_locator_v19 import locate,from_root

NOW="2026-11-02T00:00:00Z"
def fixture():
    d=data();r=d["samples"][0]
    p=dict(league="epl",home="a",away="b",kickoff_utc=r["kickoff_utc"],
        prediction_utc=r["forecast_utc"],market_snapshot_utc=r["market_utc"],
        model=r["p"],market=r["m"],case_id="synthetic",available_for_betting=False,
        production_recommendations="DISABLED")
    return json.dumps(d).encode(),dict(status="RESEARCH_ONLY",production_recommendations="DISABLED",matched_count=1,comparisons=[p])
def run(raw,p,complete=True):
    return locate(raw,[("2026/11/01/123-1",json.dumps(p).encode(),complete)],as_of=NOW)
class ForecastProofLocatorTests(unittest.TestCase):
    def test_link_only(self):
        raw,p=fixture();r=run(raw,p)
        self.assertEqual(r["states"],{"MATCHING_PROOF_INPUT_CANDIDATE":1})
        self.assertEqual(r["authenticated_samples"],0)
        self.assertEqual(r["fresh_cryptographic_verifications"],0)
    def test_changed_probability(self):
        raw,p=fixture();p["comparisons"][0]["model"]=[.5,.3,.2]
        self.assertEqual(run(raw,p)["states"],{"PAIR_CONTENT_CONFLICT_REVIEW":1})
    def test_wrong_clock(self):
        raw,p=fixture();p["comparisons"][0]["prediction_utc"]="2026-11-01T14:01:00Z"
        self.assertEqual(run(raw,p)["states"],{"NO_MATCHING_PROOF_INPUT":1})
    def test_incomplete(self):
        raw,p=fixture();self.assertEqual(run(raw,p,False)["invalid_runs"],1)
    def test_actual_archive(self):
        root=Path(__file__).resolve().parents[2]
        ledger=root/"evidence/settled.json";raw=ledger.read_bytes()
        r=from_root(root,as_of=datetime.now(timezone.utc).isoformat())
        self.assertEqual(sum(r["states"].values()),r["ledger_rows"])
        self.assertEqual(r["authenticated_samples"],0)
        self.assertEqual(raw,ledger.read_bytes())
        print("V19_FORECAST_PROOF_LOCATOR_SUMMARY "+json.dumps({k:r[k] for k in ("ledger_rows","runs_examined","invalid_runs","states","fresh_cryptographic_verifications","authenticated_samples")},sort_keys=True))
