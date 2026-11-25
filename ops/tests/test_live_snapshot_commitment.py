import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_snapshot_commitment import commitment, audit_bound_predict
from test_live_snapshot_adapter import A, B, NOW, M
from test_inplay_state_challenger_vnext import sample


def envelope():
    return dict(a=copy.deepcopy(A), b=copy.deepcopy(B),
                model=sample(minute=50, decision=M["decision_utc"]),
                decision_epoch=NOW,
                previous_a=dict(A, observed=NOW-70, received=NOW-65, minute=49),
                previous_b=dict(B, observed=NOW-68, received=NOW-65, minute=49))


class CommitmentTests(unittest.TestCase):
    def reject(self, e, reason, digest=None, now=NOW):
        result = audit_bound_predict(e, commitment(e) if digest is None else digest, now)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], reason)
        self.assertFalse(result["positive_ev_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_unchanged_envelope(self):
        e = envelope()
        digest = commitment(e)
        self.assertEqual(digest, commitment(dict(reversed(list(e.items())))))
        out = audit_bound_predict(e, digest, NOW)
        self.assertEqual(out["status"], "RESEARCH_ONLY")
        self.assertEqual(out["envelope_sha256_unattested"], digest)
        self.assertFalse(out["external_commitment_authenticated"])
        self.assertFalse(out["source_independence_verified"])
        self.assertEqual(out["production_recommendations"], "DISABLED")

    def test_mutation_after_commit(self):
        for field, key, val in (
            ("a","home",1), ("b","observed",NOW-9),
            ("previous_a","minute",48), ("previous_b","red_home",1),
            ("model","score_home",1)):
            with self.subTest(field=field,key=key):
                e=envelope()
                digest=commitment(e)
                e[field][key]=val
                self.reject(e,"COMMITMENT_MISMATCH",digest)
        e=envelope()
        digest=commitment(e)
        e["model"]["prematch"]["expected_home_goals"]=4.0
        self.reject(e,"COMMITMENT_MISMATCH",digest)

    def test_history_required(self):
        e=envelope()
        e["previous_b"]=None
        self.reject(e,"MISSING_OR_INVALID_HISTORY")

    def test_prior_source_mismatch(self):
        e=envelope()
        e["previous_a"]["origin"]="unrelated"
        self.reject(e,"HISTORY_REPLAY_OR_CORRECTION_REVIEW")

    def test_replay_equal_timestamps(self):
        e=envelope()
        e["previous_a"]=dict(e["a"])
        e["previous_b"]=dict(e["b"])
        self.reject(e,"HISTORY_REPLAY_OR_CORRECTION_REVIEW")

    def test_var_or_red_correction_quarantined(self):
        for key in ("home","red_home"):
            e=envelope()
            for side in ("previous_a","previous_b"):
                e[side][key]=1
            self.reject(e,"HISTORY_REPLAY_OR_CORRECTION_REVIEW")

    def test_history_conflict(self):
        e=envelope()
        e["previous_b"]["home"]=1
        self.reject(e,"HISTORY_CONFLICT")

    def test_history_unsynced(self):
        e=envelope()
        e["previous_b"]["observed"]-=60
        self.reject(e,"HISTORY_UNSYNCED")

    def test_decision_mismatch(self):
        e=envelope()
        self.reject(e,"DECISION_MISMATCH",now=NOW+1)

    def test_pre_kickoff_observation(self):
        e=envelope()
        e["model"]["kickoff_utc"]="2026-11-03T21:05:00Z"
        self.reject(e,"PRE_KICKOFF_OBSERVATION")

    def test_malformed_digest(self):
        e=envelope()
        for bad in ("a"*64,"é"*64,None):
            self.reject(e,"COMMITMENT_MISMATCH",digest=bad if bad is not None else "")

    def test_non_finite_input(self):
        e=envelope()
        e["model"]["prematch"]["expected_home_goals"]=float("nan")
        self.reject(e,"INVALID_BOUND_INPUT",digest="a"*64)

    def test_recomputed_commitment_not_authentication(self):
        e=envelope()
        e["model"]["prematch"]["expected_home_goals"]=2.0
        out=audit_bound_predict(e,commitment(e),NOW)
        self.assertEqual(out["status"],"RESEARCH_ONLY")
        self.assertFalse(out["external_commitment_authenticated"])
        self.assertFalse(out["source_authenticated"])
        self.assertFalse(out["model_scoring_eligible"])


if __name__ == "__main__":
    unittest.main()
