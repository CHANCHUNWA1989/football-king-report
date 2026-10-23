"""End-to-end subprocess CLI tests with synthetic historical records."""
import hashlib
import base64
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
except ImportError:
    Ed25519PrivateKey = None
    serialization = None

SCRIPT = Path(__file__).resolve().parents[1] / "run_pinned_walkforward.py"


@unittest.skipUnless(Ed25519PrivateKey is not None, "cryptography unavailable; verified in pinned research CI")
class TestPinnedWalkforwardCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "history.json"
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rows = []
        for i in range(180):
            kickoff = base + timedelta(days=i)
            rows.append({
                "event_id": f"match-{i}", "model_version": "v1",
                "predicted_at_utc": (kickoff - timedelta(hours=2)).isoformat(),
                "kickoff_at_utc": kickoff.isoformat(),
                "settled_at_utc": (kickoff + timedelta(hours=3)).isoformat(),
                "probability": 0.8, "outcome": 1,
            })
        raw = json.dumps({"schema_version": 1, "model_version": "v1",
                          "rows": rows}).encode()
        self.path.write_bytes(raw)
        self.digest = hashlib.sha256(raw).hexdigest()
        self.manifest_path = Path(self.tmp.name) / "manifest.json"
        captures = [{"event_id": row["event_id"],
                     "captured_at_utc": row["predicted_at_utc"],
                     "evidence_source": "independent-test-ledger"} for row in rows]
        manifest_raw = json.dumps({"schema_version": 1,
                                   "history_sha256": self.digest,
                                   "captures": captures}).encode()
        self.manifest_path.write_bytes(manifest_raw)
        self.manifest_digest = hashlib.sha256(manifest_raw).hexdigest()
        self.receipt_path = Path(self.tmp.name) / "receipt.json"
        self.private = Ed25519PrivateKey.generate()
        self.public_b64 = base64.b64encode(self.private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)).decode()
        receipt = {
            "schema_version": 1, "issuer": "test-issuer",
            "issued_at_utc": "2026-10-01T00:00:00Z",
            "history_sha256": self.digest,
            "capture_manifest_sha256": self.manifest_digest,
            "model_version": "v1", "reference_id": "test-001"}
        message = json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode()
        self.receipt_path.write_text(json.dumps({
            "schema_version": 1, "algorithm": "Ed25519", "key_id": "test-key",
            "receipt": receipt,
            "signature_b64": base64.b64encode(self.private.sign(message)).decode()}))

    def _run(self, digest):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--history", str(self.path),
             "--sha256", digest, "--model-version", "v1",
             "--capture-manifest", str(self.manifest_path),
             "--capture-manifest-sha256", self.manifest_digest,
             "--source-receipt", str(self.receipt_path),
             "--trusted-key-id", "test-key",
             "--trusted-public-key-b64", self.public_b64],
            capture_output=True, text=True, check=False)

    def test_valid_history_emits_research_json(self):
        process = self._run(self.digest)
        self.assertEqual(process.returncode, 0, process.stderr)
        report = json.loads(process.stdout)
        self.assertEqual(report["status"], "RESEARCH_ONLY")
        self.assertEqual(report["checks"]["source_receipt_consistency"], "PASS")
        self.assertGreaterEqual(report["fold_count"], 2)
        self.assertEqual(report["checks"]["capture_manifest"], "PASS")
        self.assertEqual(report["checks"]["trusted_timestamp_authority"], "NOT_VERIFIED")
        self.assertEqual(report["history_row_count"], 180)
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_missing_source_receipt_holds(self):
        self.receipt_path.unlink()
        process = self._run(self.digest)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(json.loads(process.stdout)["status"], "HOLD")

    def test_missing_capture_manifest_exits_nonzero(self):
        self.manifest_path.unlink()
        process = self._run(self.digest)
        self.assertEqual(process.returncode, 2)
        report = json.loads(process.stdout)
        self.assertEqual(report["status"], "HOLD")
        self.assertIn("evidence_reason", report["failure"])

    def test_wrong_pin_exits_nonzero(self):
        process = self._run("0" * 64)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(json.loads(process.stdout)["status"], "HOLD")

    def test_modified_history_exits_nonzero(self):
        self.path.write_bytes(self.path.read_bytes() + b" ")
        self.assertEqual(self._run(self.digest).returncode, 2)


if __name__ == "__main__":
    unittest.main()
