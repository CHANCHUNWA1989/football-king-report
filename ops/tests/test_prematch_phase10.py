"""Phase 10 release gate and adversarial evidence ledger validation."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prematch_release_gate import evaluate_release, REQUIRED_CI
from prematch_raw_archive import archive_response
from prematch_evidence_chain import append_evidence, verify_evidence_chain


class TestPhaseTen(unittest.TestCase):
    def test_all_green_still_requires_independent_provenance(self):
        report = evaluate_release(commit_sha="a" * 40,
            ci_conclusions={name: "success" for name in REQUIRED_CI},
            sandbox_evidence={"verified": True},
            tsa_evidence={"verified": True},
            source_evidence={"verified": True},
            heldout_evidence={"passed": True})
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertEqual(len(report["rejection_reasons"]), 4)
        self.assertEqual(len(report["manifest_sha256"]), 64)

    def test_missing_ci_and_unpinned_commit(self):
        report = evaluate_release(commit_sha="branch-main", ci_conclusions={})
        self.assertIn("UNPINNED_COMMIT", report["rejection_reasons"])
        self.assertEqual(sum(x.startswith("CI_NOT_SUCCESS:") for x in
                             report["rejection_reasons"]), len(REQUIRED_CI))

    def test_ledger_digest_path_injection_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            archive = archive_response(b"fixture", directory=root)
            append_evidence(root, archive)
            ledger = Path(root) / "evidence-ledger.jsonl"
            row = json.loads(ledger.read_text().splitlines()[0])
            row["archive_sha256"] = "../" + "a" * 61
            signed = {k: v for k, v in row.items() if k != "entry_hash"}
            row["entry_hash"] = hashlib.sha256(
                (json.dumps(signed, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
            ledger.write_text(json.dumps(row) + "\n")
            with self.assertRaises(ValueError):
                verify_evidence_chain(root)

    def test_ledger_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            outside = Path(root) / "outside"
            outside.write_text("data")
            (Path(root) / "evidence-ledger.jsonl").symlink_to(outside)
            with self.assertRaises((ValueError, OSError)):
                verify_evidence_chain(root)


if __name__ == "__main__":
    unittest.main()
