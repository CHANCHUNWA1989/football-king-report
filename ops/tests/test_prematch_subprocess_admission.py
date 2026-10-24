"""Real subprocess contention, process death and admission-gate tests."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

OPS = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, OPS)
from prematch_raw_archive import archive_response
from prematch_evidence_chain import append_evidence, verify_evidence_chain
from prematch_admission_gate import assess_prematch_admission

WORKER = """import sys,time
sys.path.insert(0,sys.argv[1])
from prematch_raw_archive import archive_response
from prematch_evidence_chain import append_evidence
raw=sys.argv[3].encode()
archive=archive_response(raw,directory=sys.argv[2])
for _ in range(100):
 try:
  append_evidence(sys.argv[2],archive)
  sys.exit(0)
 except BlockingIOError:
  time.sleep(.01)
sys.exit(2)
"""


class TestSubprocessEvidence(unittest.TestCase):
    def test_parallel_processes_no_lost_entries(self):
        with tempfile.TemporaryDirectory() as root:
            children = [subprocess.Popen(
                [sys.executable, "-c", WORKER, OPS, root, "quote-" + str(i)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(8)]
            for child in children:
                out, err = child.communicate(timeout=20)
                self.assertEqual(child.returncode, 0, err.decode())
            entries = verify_evidence_chain(root)
            self.assertEqual(len(entries), 8)
            self.assertEqual([e["index"] for e in entries], list(range(8)))
            self.assertEqual(len({e["archive_sha256"] for e in entries}), 8)

    def test_killed_lock_owner_releases_kernel_lock(self):
        with tempfile.TemporaryDirectory() as root:
            code = """import fcntl,os,sys,time
fd=os.open(sys.argv[1],os.O_CREAT|os.O_RDWR,0o600)
fcntl.flock(fd,fcntl.LOCK_EX)
print("LOCKED",flush=True)
time.sleep(60)
"""
            owner = subprocess.Popen([sys.executable, "-c", code,
                                     str(Path(root) / ".evidence.lock")],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True)
            try:
                self.assertEqual(owner.stdout.readline().strip(), "LOCKED")
                owner.kill()
                owner.wait(timeout=5)
                archive = archive_response(b"after-crash", directory=root)
                self.assertEqual(append_evidence(root, archive)["index"], 0)
                self.assertEqual(len(verify_evidence_chain(root)), 1)
            finally:
                if owner.poll() is None:
                    owner.kill()
                    owner.wait(timeout=5)

    def test_gate_reports_all_unverified_requirements(self):
        with tempfile.TemporaryDirectory() as root:
            report = assess_prematch_admission(root)
            self.assertEqual(report["status"], "HOLD")
            self.assertEqual(report["production_recommendations"], "DISABLED")
            self.assertIn("EMPTY_EVIDENCE_CHAIN", report["rejection_reasons"])
            archive = archive_response(b"sample", directory=root)
            append_evidence(root, archive)
            report = assess_prematch_admission(
                root, fixture_id="fixture", provider_id="provider",
                independent_source_receipt={"verified": True},
                independent_timestamp_receipt={"verified": True},
                heldout_validation={"passed": True})
            self.assertTrue(report["checks"]["archive_chain"])
            self.assertFalse(report["checks"]["independent_source"])
            self.assertFalse(report["checks"]["trusted_timestamp"])
            self.assertFalse(report["checks"]["heldout_performance"])
            self.assertEqual(report["evidence_entries"], 1)

    def test_corrupted_chain_reports_failure(self):
        with tempfile.TemporaryDirectory() as root:
            archive = archive_response(b"sample", directory=root)
            append_evidence(root, archive)
            (Path(root) / "evidence-ledger.jsonl").write_text("broken\n")
            report = assess_prematch_admission(root, fixture_id="f", provider_id="p")
            self.assertIn("INVALID_EVIDENCE_CHAIN", report["rejection_reasons"])


if __name__ == "__main__":
    unittest.main()
