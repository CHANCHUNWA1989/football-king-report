import json
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from ops.research_attack_defence_replay_v35 import rates,eligible,vec,from_root,replay
from ops.research_supplemental_history_v32 import inventory
from ops.tests.test_research_archive_score_recovery_v14 import fixture,encode
from ops.research_missing_fixture_discovery_v16 import candidates
NOW="2026-11-02T00:00:00Z"
class AttackDefenceReplayTests(unittest.TestCase):
    def test_equal_boundary_and_future_excluded(self):
        raw,_=fixture();k=next(iter(candidates(raw)))
        f=k[3]-timedelta(hours=1)
        pool=[(f,k,(5,0)),(f+timedelta(seconds=1),k,(0,5))]
        self.assertEqual(eligible(pool,f,0),[])
        self.assertEqual(rates(eligible(pool,f,0),k),rates([],k))
    def test_prior_score_changes_rates(self):
        raw,_=fixture();k=next(iter(candidates(raw)))
        t=k[3]+timedelta(hours=2)
        self.assertNotEqual(rates([(t,k,(5,0))],k),rates([(t,k,(0,5))],k))
        self.assertAlmostEqual(sum(vec(*rates([(t,k,(5,0))],k)[:2])),1)
    def test_empty_strict_cohort_is_not_zero_loss(self):
        raw,p=fixture()
        inv=inventory(raw,[("p",encode(p))],[],as_of=NOW,include_replay_inputs=True)
        r=replay(raw,inv)
        self.assertEqual(r["strict_24h_targets"],0)
        self.assertIsNone(r["scenarios"]["24"]["fixed_strict_24h_cohort"]["expanded_history"]["log_loss"])
        self.assertEqual(r["scenarios"]["24"]["all"]["expanded_history"]["n"],1)
    def test_duplicate_prior_rejected(self):
        raw,p=fixture()
        inv=inventory(raw,[("p",encode(p))],[],as_of=NOW,include_replay_inputs=True)
        inv["replay_inputs"]["extra"]=list(inv["replay_inputs"]["base"])
        with self.assertRaises(ValueError):replay(raw,inv)
    def test_actual_archive(self):
        root=Path(__file__).resolve().parents[2];ledger=root/"evidence/settled.json";raw=ledger.read_bytes()
        r=from_root(root,as_of=datetime.now(timezone.utc).isoformat())
        self.assertEqual(ledger.read_bytes(),raw)
        self.assertFalse(r["training_admission"])
        for s in r["scenarios"].values():
            self.assertEqual({m["n"] for m in s["all"].values()},{r["targets"]})
            self.assertEqual({m["n"] for m in s["fixed_strict_24h_cohort"].values()},{r["strict_24h_targets"]})
        print("V35_ATTACK_DEFENCE_REPLAY_SUMMARY "+json.dumps(r,sort_keys=True,allow_nan=False))
