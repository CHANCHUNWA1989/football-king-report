"""Crash inspection and interrupted-write adversarial tests."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prematch_raw_archive import archive_response
from prematch_evidence_chain import append_evidence, verify_evidence_chain
from prematch_crash_inspection import inspect_crash_tail


class TestCrashInspection(unittest.TestCase):
    def test_partial_tail_detected_without_mutation(self):
        with tempfile.TemporaryDirectory() as root:
            archive = archive_response(b"valid", directory=root)
            append_evidence(root, archive)
            ledger = Path(root) / "evidence-ledger.jsonl"
            with ledger.open("ab") as stream:
                stream.write(b'{"index":1,"archive_sha256":')
            before = ledger.read_bytes()
            report = inspect_crash_tail(root)
            self.assertEqual(report["reason"], "PARTIAL_TRAILING_RECORD")
            self.assertEqual(report["valid_prefix_entries"], 1)
            self.assertEqual(ledger.read_bytes(), before)
            with self.assertRaises(ValueError):
                verify_evidence_chain(root)

    def test_valid_chain_and_corrupt_complete_record(self):
        with tempfile.TemporaryDirectory() as root:
            archive = archive_response(b"valid", directory=root)
            append_evidence(root, archive)
            self.assertEqual(inspect_crash_tail(root)["reason"], "CHAIN_VALID")
            with (Path(root) / "evidence-ledger.jsonl").open("ab") as stream:
                stream.write(b"invalid-complete-line\n")
            self.assertEqual(inspect_crash_tail(root)["reason"],
                             "CORRUPTION_REQUIRES_MANUAL_INVESTIGATION")

    def test_symlink_ledger_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            outside = Path(root) / "outside"
            outside.write_bytes(b"fake")
            (Path(root) / "evidence-ledger.jsonl").symlink_to(outside)
            self.assertEqual(inspect_crash_tail(root)["reason"], "UNSAFE_LEDGER_PATH")


if __name__ == "__main__":
    unittest.main()
