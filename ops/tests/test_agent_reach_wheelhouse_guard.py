"""Synthetic wheelhouse hash validation; no actual PyPI traffic in tests."""
import copy
import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_reach_wheelhouse_guard import EXTERNAL, WheelHold, discover, verify


class WheelhouseGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, version in EXTERNAL.items():
            file = f"{name.replace('-', '_')}-{version}-py3-none-any.whl"
            (self.root / file).write_bytes(f"synthetic-test-only-{name}".encode())
        self.candidate = discover(self.root)

    def test_exact_known_manifest_verifies_only_runtime_bytes(self):
        report, requirements = verify(self.root, self.candidate)
        self.assertTrue(report["runtime_wheel_hash_verified"])
        self.assertEqual(report["runtime_wheel_count"], 13)
        self.assertFalse(report["build_dependency_hash_verified"])
        self.assertFalse(report["upstream_signature_verified"])
        self.assertFalse(report["egress_firewall_verified"])
        self.assertFalse(report["eligible_for_model"])
        self.assertIsNone(report["verified_positive_ev"])
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertEqual(len(requirements.strip().splitlines()), 13)
        for line in requirements.splitlines():
            self.assertIn("--hash=sha256:", line)

    def test_tampered_bytes_fail(self):
        one = next(self.root.glob("*.whl"))
        one.write_bytes(b"modified-synthetic-wheel")
        with self.assertRaisesRegex(WheelHold, "WHEEL_BYTES_OR_FILENAME_MISMATCH"):
            verify(self.root, self.candidate)

    def test_extra_wheel_fails(self):
        (self.root / "extra-1.2.3-py3-none-any.whl").write_bytes(b"fake")
        with self.assertRaises(WheelHold):
            verify(self.root, self.candidate)

    def test_missing_wheel_fails(self):
        next(self.root.glob("*.whl")).unlink()
        with self.assertRaisesRegex(WheelHold, "INCOMPLETE_WHEEL_INVENTORY"):
            verify(self.root, self.candidate)

    def test_unknown_or_loose_manifest_digest_fails(self):
        broken = copy.deepcopy(self.candidate)
        broken["wheels"][0]["sha256"] = "a" * 64
        with self.assertRaises(WheelHold):
            verify(self.root, broken)
        broken["wheels"][0]["sha256"] = "not a digest"
        with self.assertRaises(WheelHold):
            verify(self.root, broken)

    def test_injected_paths_rejected(self):
        broken = copy.deepcopy(self.candidate)
        broken["wheels"][0]["file"] = "../attacker.whl"
        with self.assertRaises(WheelHold):
            verify(self.root, broken)

    def test_symlink_is_not_followed(self):
        one = next(self.root.glob("*.whl"))
        target = self.root / "upstream"
        target.write_bytes(one.read_bytes())
        one.unlink()
        one.symlink_to(target)
        with self.assertRaises(WheelHold):
            discover(self.root)

    def test_empty_manifest_fails(self):
        for bad in ({}, {"schema": "old", "wheels": []}, None):
            with self.subTest(bad=bad), self.assertRaises(WheelHold):
                verify(self.root, bad)

    def test_duplicate_manifest_package_fails(self):
        broken = copy.deepcopy(self.candidate)
        broken["wheels"][1] = broken["wheels"][0]
        with self.assertRaises(WheelHold):
            verify(self.root, broken)

    def test_unexpected_non_wheel_rejected(self):
        (self.root / "notes.txt").write_text("untrusted")
        with self.assertRaises(WheelHold):
            discover(self.root)


if __name__ == "__main__":
    unittest.main()
