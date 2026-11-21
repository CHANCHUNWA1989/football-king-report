import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from ops.rfc3161_timestamp_gate import verify


class RFC3161Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = []
        for name in ("receipt.json", "stamp.tsr", "trusted-ca.pem"):
            p = Path(self.tmp.name) / name
            p.write_bytes(b"synthetic-test-only")
            self.paths.append(p)

    def run_gate(self, *, verify_ok=True, text="Time stamp: Nov  7 12:00:00 2026 GMT"):
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            if "-verify" in args:
                return SimpleNamespace(returncode=0 if verify_ok else 1, stdout="", stderr="")
            return SimpleNamespace(returncode=0, stdout=text, stderr="")
        return verify(*self.paths, "2026-11-07T13:00:00Z", runner=runner), calls

    def test_valid_synthetic_output_still_requires_policy_review(self):
        result, calls = self.run_gate()
        self.assertEqual(result["status"], "CRYPTOGRAPHIC_TIMESTAMP_CHECK_PASSED")
        self.assertFalse(result["independently_timestamped"])
        self.assertEqual(len(calls), 2)

    def test_invalid_signature_holds(self):
        result, calls = self.run_gate(verify_ok=False)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(len(calls), 1)

    def test_after_kickoff_holds(self):
        result, _ = self.run_gate(text="Time stamp: Nov  7 14:00:00 2026 GMT")
        self.assertEqual(result["status"], "HOLD")

    def test_unknown_timestamp_format_holds(self):
        result, _ = self.run_gate(text="untrusted timestamp")
        self.assertEqual(result["status"], "HOLD")

    def test_naive_kickoff_holds(self):
        result = verify(*self.paths, "2026-11-07T13:00:00")
        self.assertEqual(result["status"], "HOLD")

    def test_missing_ca_holds(self):
        self.paths[-1].unlink()
        result = verify(*self.paths, "2026-11-07T13:00:00Z")
        self.assertEqual(result["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
