"""Synthetic tests for Agent Reach dependency version and inventory guard."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_reach_dependency_guard import EXPECTED, audit, canonical, parse_constraints

CONSTRAINTS = "\n".join(f"{name}=={version}" for name, version in EXPECTED.items()) + "\n"


class DependencyGuardTests(unittest.TestCase):
    def test_pass_still_hold_no_source_authentication(self):
        report, rc = audit(CONSTRAINTS, version_reader=EXPECTED.__getitem__)
        self.assertEqual(rc, 0)
        self.assertEqual(report["dependency_version_check"], "PASS_VERSION_ONLY")
        self.assertEqual(report["checked_packages"], 14)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertFalse(report["supply_chain_hash_verified"])
        self.assertFalse(report["build_isolation_hash_verified"])
        self.assertFalse(report["egress_firewall_verified"])
        self.assertFalse(report["eligible_for_model"])
        self.assertIsNone(report["verified_positive_ev"])

    def test_dependency_version_drift_fails(self):
        values = dict(EXPECTED, requests="2.99.0")
        report, rc = audit(CONSTRAINTS, version_reader=values.__getitem__)
        self.assertEqual(rc, 2)
        self.assertEqual(report["reason"], "PINNED_DEPENDENCY_VERSION_DRIFT")
        self.assertEqual(report["dependency_version_check"], "HOLD")

    def test_missing_required_dependency_fails(self):
        values = {k: v for k, v in EXPECTED.items() if k != "requests"}
        report, rc = audit(CONSTRAINTS, version_reader=values.__getitem__)
        self.assertEqual(rc, 2)
        self.assertEqual(report["reason"], "PINNED_DEPENDENCY_MISSING")

    def test_missing_or_added_constraint_fails(self):
        for changed in (CONSTRAINTS.replace("requests==2.34.2\n", ""),
                        CONSTRAINTS + "unrelated==1.0\n"):
            with self.subTest(changed=changed[-40:]):
                report, rc = audit(changed, version_reader=EXPECTED.__getitem__)
                self.assertEqual(rc, 2)
                self.assertEqual(report["reason"], "CONSTRAINT_INVENTORY_DRIFT")

    def test_no_unpinned_redirect_editable_or_duplicate(self):
        for suffix in ("requests>=2.28\n", "requests\n",
                       "https://example.org/file.zip\n", "-e .\n",
                       "requests==2.34.2\n", "Requests==2.34.2\n"):
            with self.subTest(suffix=suffix):
                report, rc = audit(CONSTRAINTS + suffix,
                                   version_reader=EXPECTED.__getitem__)
                self.assertEqual(rc, 2)
                self.assertEqual(report["status"], "HOLD")

    def test_canonical_distribution_name(self):
        self.assertEqual(canonical("Charset_Normalizer"), "charset-normalizer")
        self.assertEqual(canonical("yt.dlp_ejs"), "yt-dlp-ejs")

    def test_blank_lines_comments_are_safe(self):
        formatted = "# runtime constraint\n\n" + CONSTRAINTS + "# end\n"
        self.assertEqual(parse_constraints(formatted), EXPECTED)

    def test_unreadable_lock_content_rejected(self):
        for data in (None, "z" * 10_001):
            with self.assertRaises((ValueError, TypeError)):
                parse_constraints(data)

    def test_error_contains_no_runtime_exception_data(self):
        def secret_reader(name):
            raise KeyError("TOPSECRET")
        report, rc = audit(CONSTRAINTS, version_reader=secret_reader)
        self.assertEqual(rc, 2)
        self.assertNotIn("TOPSECRET", str(report))
        self.assertEqual(report["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
