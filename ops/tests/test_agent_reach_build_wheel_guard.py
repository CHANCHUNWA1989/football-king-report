"""Offline synthetic cases for Agent Reach build-backend wheel SHA256 gate."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_reach_build_wheel_guard import EXPECTED, BuildHold, discover, verify, identity

VERSIONS = {
    "hatchling": "1.27.0",
    "packaging": "26.0",
    "pathspec": "0.12.1",
    "pluggy": "1.6.0",
    "trove-classifiers": "2026.11.1",
}


class BuildWheelGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        for name in EXPECTED:
            filename = f"{name.replace('-', '_')}-{VERSIONS[name]}-py3-none-any.whl"
            (self.directory / filename).write_bytes((f"synthetic-only:{name}").encode("utf-8"))
        self.manifest = discover(self.directory)

    def test_approved_hashes_still_keep_formal_hold(self):
        report, req = verify(self.directory, self.manifest)
        self.assertEqual(report["build_dependency_wheel_count"], 5)
        self.assertTrue(report["build_dependency_wheel_sha256_matched"])
        self.assertFalse(report["offline_build_proved_by_this_step"])
        self.assertFalse(report["container_network_none_proved_by_this_step"])
        self.assertFalse(report["docker_image_digest_pinned"])
        self.assertFalse(report["eligible_for_model"])
        self.assertIsNone(report["verified_positive_ev"])
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertEqual(len(req.strip().splitlines()), 5)
        self.assertTrue(all("--hash=sha256:" in x for x in req.strip().splitlines()))

    def test_tampered_bytes_rejected(self):
        next(self.directory.glob("*.whl")).write_bytes(b"tampered")
        with self.assertRaises(BuildHold):
            verify(self.directory, self.manifest)

    def test_missing_wheel_rejected(self):
        next(self.directory.glob("*.whl")).unlink()
        with self.assertRaises(BuildHold):
            verify(self.directory, self.manifest)

    def test_unapproved_extra_wheel_rejected(self):
        (self.directory / "evil-0.0-py3-none-any.whl").write_bytes(b"untrusted")
        with self.assertRaises(BuildHold):
            verify(self.directory, self.manifest)

    def test_manifest_bad_digest_rejected(self):
        changed = copy.deepcopy(self.manifest)
        changed["wheels"][0]["sha256"] = "abcd"
        with self.assertRaises(BuildHold):
            verify(self.directory, changed)

    def test_duplicate_manifest_rejected(self):
        changed = copy.deepcopy(self.manifest)
        changed["wheels"][1] = changed["wheels"][0]
        with self.assertRaises(BuildHold):
            verify(self.directory, changed)

    def test_path_traversal_or_query_rejected(self):
        for filename in ("../hatchling-1.27.0-py3-none-any.whl",
                         "https://evil.invalid/x.whl",
                         "hatchling-1.27.0-py3-none-any.whl?key=secret",
                         "hatchling-1.27.0-any.whl"):
            with self.subTest(filename=filename), self.assertRaises(BuildHold):
                identity(filename)

    def test_symlink_wheel_rejected(self):
        path = next(self.directory.glob("*.whl"))
        target = self.directory / "archive"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
        with self.assertRaises(BuildHold):
            discover(self.directory)

    def test_unknown_inventory_rejected(self):
        path = next(self.directory.glob("*.whl"))
        path.rename(path.with_name("hatchling-1.26.0-py3-none-any.whl"))
        with self.assertRaises(BuildHold):
            verify(self.directory, self.manifest)

    def test_fail_closed_on_invalid_envelopes(self):
        for data in (None, {}, {"schema": "unknown", "wheels": []},
                     {"schema": self.manifest["schema"], "wheels": self.manifest["wheels"][:2]}):
            with self.subTest(case=data), self.assertRaises(BuildHold):
                verify(self.directory, data)


if __name__ == "__main__":
    unittest.main()
