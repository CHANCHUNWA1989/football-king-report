"""Offline guard that both regression workflows exercise pinned-age crypto tests.

No secrets, provider HTTP, or binary are accessed by this module. Real
age roundtrip tests run only in Actions after the verified installer.
"""
from pathlib import Path
import re
import unittest


REPO=Path(__file__).resolve().parents[2]
SECONDARY=REPO/".github/workflows/football-king-regression.yml"
PRIMARY=REPO/".github/workflows/football-king-ci.yml"


class PinnedAgeCoverageParityTests(unittest.TestCase):
    def test_full_regression_has_verified_age_installer_before_unittest(self):
        text=SECONDARY.read_text(encoding="utf-8")
        install='python -m ops.install_age --destination "$RUNNER_TEMP/football-age"'
        export='echo "FOOTBALL_AGE_BINARY=$RUNNER_TEMP/football-age/age" >> "$GITHUB_ENV"'
        suite="python -m unittest discover -s ops/tests -q"
        self.assertEqual(text.count(install),1)
        self.assertEqual(text.count(export),1)
        self.assertEqual(text.count(suite),1)
        self.assertLess(text.index(install),text.index(export))
        self.assertLess(text.index(export),text.index(suite))
        self.assertIn("permissions:\n  contents: read",text)

    def test_research_workflow_reuses_exact_production_free_crypto_installer(self):
        ci=PRIMARY.read_text(encoding="utf-8")
        regression=SECONDARY.read_text(encoding="utf-8")
        for line in (
            'python -m ops.install_age --destination "$RUNNER_TEMP/football-age"',
            'echo "FOOTBALL_AGE_BINARY=$RUNNER_TEMP/football-age/age" >> "$GITHUB_ENV"',
        ):
            self.assertIn(line,ci)
            self.assertIn(line,regression)
        self.assertNotIn("curl -",regression)
        self.assertNotIn("wget ",regression)
        self.assertNotIn("secrets.",regression)

    def test_skip_modules_depend_on_pinned_age_file(self):
        counts={}
        for name in ("test_private_response_relay.py","test_private_drive_handoff.py"):
            body=(REPO/"ops/tests"/name).read_text(encoding="utf-8")
            self.assertIn("@unittest.skipUnless(AGE.is_file()",body)
            self.assertIn("FOOTBALL_AGE_BINARY",body)
            counts[name]=len(re.findall(r"^\s+def test_",body,re.M))
        self.assertEqual(counts["test_private_response_relay.py"],10)
        self.assertEqual(counts["test_private_drive_handoff.py"],6)

    def test_hash_pinned_age_installer_remains_identity_checked(self):
        code=(REPO/"ops/install_age.py").read_text(encoding="utf-8")
        self.assertIn("VERSION = 'v1.3.2'",code)
        self.assertIn("ARCHIVE_SHA256",code)
        self.assertIn("BINARY_HASHES",code)
        self.assertIn("AGE_ARCHIVE_DIGEST_MISMATCH",code)
        self.assertIn("AGE_BINARY_DIGEST_MISMATCH",code)


if __name__=="__main__":
    unittest.main()
