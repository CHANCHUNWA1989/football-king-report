"""Synthetic adversarial checks; real PR433 import is a separate CI smoke step."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inplay_pinned_pr433_probe import (
    PINNED_COMMIT, PINNED_BLOBS, _git_blob_sha1, _validate_tree,
    _inputs, run_pinned, _hold,
)


class InPlayPinnedPR433ProbeTests(unittest.TestCase):
    def test_sha1_git_blob_hash_exact(self):
        raw=b"original\n"
        expected=hashlib.sha1(b"blob 9\x00"+raw).hexdigest()
        self.assertEqual(_git_blob_sha1(raw), expected)
        self.assertNotEqual(_git_blob_sha1(b"altered\n"), expected)

    def test_approved_manifest_is_fixed_full_commit_and_two_blobs(self):
        self.assertEqual(len(PINNED_COMMIT),40)
        self.assertEqual(set(PINNED_BLOBS),{
            "ops/inplay_state_challenger_vnext.py",
            "ops/score_distribution_vnext.py"})
        for h in [PINNED_COMMIT,*PINNED_BLOBS.values()]:
            self.assertTrue(all(c in "0123456789abcdef" for c in h))

    def test_valid_synthetic_case_is_time_scoped_and_not_results(self):
        case,snap=_inputs()
        self.assertEqual(case["state"]["as_of_utc"],snap["decision_utc"])
        self.assertEqual(case["fixture"]["fixture_id"],snap["fixture_id"])
        self.assertEqual(case["state"]["home_goals"],1)
        self.assertEqual(case["state"]["away_goals"],1)
        self.assertNotIn("final_score",json.dumps(snap))
        self.assertNotIn("odds",json.dumps(snap))
        self.assertEqual(snap["prematch"]["production_recommendations"],"DISABLED")

    def test_missing_checkout_is_hold_not_fake_execution(self):
        with tempfile.TemporaryDirectory() as t:
            r=run_pinned(Path(t))
            self.assertEqual(r["status"],"HOLD")
            self.assertEqual(r["reason"],"PINNED_CHECKOUT_MISMATCH")
            self.assertFalse(r["genuine_pr433_execution_observed_locally"])
            self.assertEqual(r["certified_paired_samples"],0)

    def test_byte_pin_detects_corrupt_dependency(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for p in PINNED_BLOBS:
                target=root/p
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_text("a=1\n",encoding="utf-8")
            with patch("inplay_pinned_pr433_probe.subprocess.run") as proc:
                proc.return_value.stdout=PINNED_COMMIT+"\n"
                proc.return_value.returncode=0
                with self.assertRaisesRegex(ValueError,"SOURCE_BLOB_MISMATCH"):
                    _validate_tree(root)

    def test_fake_checkout_commit_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as t:
            with patch("inplay_pinned_pr433_probe.subprocess.run") as proc:
                proc.return_value.stdout="0"*40+"\n"
                proc.return_value.returncode=0
                with self.assertRaisesRegex(ValueError,"PINNED_HEAD_MISMATCH"):
                    _validate_tree(Path(t))

    def test_symlink_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/"ops").mkdir()
            (root/"src.py").write_text("print(1)\n")
            (root/"ops"/"inplay_state_challenger_vnext.py").symlink_to(root/"src.py")
            with patch("inplay_pinned_pr433_probe.subprocess.run") as proc:
                proc.return_value.stdout=PINNED_COMMIT+"\n"
                proc.return_value.returncode=0
                with self.assertRaisesRegex(ValueError,"SOURCE_NOT_REGULAR_FILE"):
                    _validate_tree(root)

    def test_failed_git_command_is_hold(self):
        with tempfile.TemporaryDirectory() as t:
            with patch("inplay_pinned_pr433_probe.subprocess.run",side_effect=OSError("secret_token")):
                r=run_pinned(Path(t))
                self.assertEqual(r["status"],"HOLD")
                self.assertNotIn("secret_token",str(r))

    def test_safety_flags_never_upgrade_on_claims(self):
        result=_hold("CHECK")
        for k in ("production_recommendations","genuine_pr433_execution_observed_locally",
                  "candidate_source_publisher_authenticated","formal_model_comparison_allowed",
                  "externally_witnessed","positive_ev_verified","certified_paired_samples"):
            self.assertIn(k,result)
        self.assertEqual(result["production_recommendations"],"DISABLED")
        self.assertFalse(result["genuine_pr433_execution_observed_locally"])
        self.assertFalse(result["candidate_source_publisher_authenticated"])
        self.assertFalse(result["externally_witnessed"])
        self.assertFalse(result["formal_model_comparison_allowed"])
        self.assertFalse(result["positive_ev_verified"])
        self.assertEqual(result["certified_paired_samples"],0)


if __name__=="__main__":
    unittest.main()
