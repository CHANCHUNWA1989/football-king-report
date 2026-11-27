import unittest
from copy import deepcopy
from unittest.mock import patch
from ops.research_private_replayed_evaluation import evaluate_replayed
from ops.research_private_run_store_v48 import encode_run
from ops.tests.test_research_private_full_replay import inputs
from ops.tests.test_research_private_settlement_v49 import inputs as settled_inputs
from ops.tests.test_research_archive_score_recovery_v14 import fixture,encode
from ops.tests.test_research_private_propline_v43 import NOW

def bundle(two=False):
    ledger,a,b,p=inputs(two=two)
    return dict(run_raw=encode_run(b,p),ledger_raw=ledger,primary=a,secondary=[],
                include_supplemental=True)

class ReplayedEvaluationTests(unittest.TestCase):
    def test_replayed_pending(self):
        r=evaluate_replayed([bundle()],[],[],as_of=NOW.isoformat())
        self.assertEqual(r["replayed_runs"],1)
        self.assertEqual(r["replayed_receipts"],1)
        self.assertEqual(r["paired_candidates"],0)
        self.assertTrue(r["historical_reference_bytes_rechecked"])
        self.assertFalse(r["cohort_completeness_proven"])
        self.assertEqual(r["authenticated_samples"],0)
    def test_replayed_dual_settlement(self):
        raw,p,s,now=settled_inputs()
        ledger,prior=fixture()
        b=dict(run_raw=raw,ledger_raw=ledger,primary=[("prior",encode(prior))],
               secondary=[],include_supplemental=False)
        r=evaluate_replayed([b],[("p",encode(p))],[("s",encode(s))],as_of=now)
        self.assertEqual(r["paired_candidates"],1)
        self.assertEqual(r["models"]["market"]["n"],1)
        self.assertFalse(r["independent_oos_proven"])
    def test_missing_archive_blocks_evaluation(self):
        b=bundle();b["primary"]=[]
        with patch("ops.research_private_replayed_evaluation.evaluate") as evaluate:
            with self.assertRaises(ValueError):
                evaluate_replayed([b],[],[],as_of=NOW.isoformat())
            evaluate.assert_not_called()
    def test_omitted_prediction_blocks_evaluation(self):
        ledger,a,b,p=inputs(two=True)
        item=dict(run_raw=encode_run(b,p[:1]),ledger_raw=ledger,primary=a,secondary=[],
                  include_supplemental=True)
        with self.assertRaises(ValueError):
            evaluate_replayed([item],[],[],as_of=NOW.isoformat())
    def test_duplicate_and_budget(self):
        b=bundle()
        with self.assertRaises(ValueError):
            evaluate_replayed([b,b],[],[],as_of=NOW.isoformat())
        with patch("ops.research_private_replayed_evaluation.MAX_ARCHIVE_BYTES",1):
            with self.assertRaises(ValueError):
                evaluate_replayed([b],[],[],as_of=NOW.isoformat())
    def test_empty_cohort_not_verified(self):
        r=evaluate_replayed([],[],[],as_of=NOW.isoformat())
        self.assertFalse(r["supplied_input_rosters_reproduced"])
        self.assertIsNone(r["candidate_coverage"])
