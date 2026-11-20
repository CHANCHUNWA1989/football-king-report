"""Purely synthetic acceptance tests: no Kloppy wheel is installed."""
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ops.kloppy_native_smoke_acceptance import (
    _write_receipt_exclusive, verify_local_native_smoke,
)
from ops.kloppy_offline_wheel_preflight import UnsafeWheel


def completed(*, code=0, stderr="Ran 2 tests in 0.010s\n\nOK\n", stdout=""):
    return subprocess.CompletedProcess(["python"], code, stdout, stderr)


class LocalNativeSmokeAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.wheel = "/isolated/in-memory/kloppy-3.19.1-py3-none-any.whl"

    def evaluate(self, version="3.19.1", runner=None):
        if runner is None:
            runner = lambda *args, **kwargs: completed()
        with patch("ops.kloppy_native_smoke_acceptance.verify_official_kloppy_wheel",
                   return_value={"sha256": "synthetic-only"}) as mock_verify:
            result = verify_local_native_smoke(
                self.wheel, _version=lambda name: version,
                _runner=runner,
            )
        mock_verify.assert_called_once_with(self.wheel)
        return result

    def test_positive_mock_is_research_only_never_an_independent_certificate(self):
        result = self.evaluate()
        self.assertEqual(result["status"], "RESEARCH_ONLY_LOCAL_SMOKE_PASSED")
        self.assertEqual(result["local_native_test_count"], 2)
        self.assertTrue(result["real_native_tests_passed_locally"])
        for flag in ("independent_software_provenance_verified",
                     "third_party_dependencies_independently_audited",
                     "licensed_match_data_verified", "model_promoted",
                     "positive_ev_verified"):
            self.assertFalse(result[flag])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertEqual(result["forward_samples_certified"], 0)

    def test_real_wheel_preflight_failure_never_runs_tests(self):
        with patch("ops.kloppy_native_smoke_acceptance.verify_official_kloppy_wheel",
                   side_effect=UnsafeWheel("no official wheel")):
            result = verify_local_native_smoke(self.wheel,
                          _version=lambda _: "3.19.1",
                          _runner=lambda *a, **k: self.fail("must not run"))
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "OFFICIAL_WHEEL_PREFLIGHT_FAILED")
        self.assertFalse(result["real_native_tests_executed"])

    def test_incorrect_installed_version_rejects_before_tests(self):
        result = self.evaluate(version="3.19.0",
                               runner=lambda *a, **k: self.fail("must not run"))
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "WRONG_INSTALLED_KLOPPY_VERSION")

    def test_import_failure_reports_not_installed(self):
        from importlib.metadata import PackageNotFoundError
        with patch("ops.kloppy_native_smoke_acceptance.verify_official_kloppy_wheel",
                   return_value={"sha256": "synthetic-only"}):
            result = verify_local_native_smoke(
                self.wheel, _version=lambda _: (_ for _ in ()).throw(
                    PackageNotFoundError("kloppy")),
                _runner=lambda *a, **k: self.fail("must not run"))
        self.assertEqual(result["reason"], "KLOPPY_NOT_INSTALLED")

    def test_unittest_nonzero_exit_cannot_pass(self):
        result = self.evaluate(runner=lambda *a, **k: completed(code=1))
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "NATIVE_SMOKE_TESTS_NOT_PASSED")

    def test_stdout_spoofed_test_count_does_not_pass(self):
        result = self.evaluate(runner=lambda *a, **k: completed(
            stdout="Ran 10000 tests in 0.002s\nOK\n",
            stderr="No tests were run\n"))
        self.assertEqual(result["status"], "HOLD")

    def test_skipped_or_zero_native_tests_cannot_pass(self):
        for body in (
            "Ran 0 tests in 0.002s\n\nOK\n",
            "Ran 2 tests in 0.002s\n\nOK (skipped=1)\n",
            "Ran 1 test in 0.002s\n\nOK\n",
        ):
            with self.subTest(body=body):
                result = self.evaluate(runner=lambda *a, **k: completed(stderr=body))
                self.assertEqual(result["status"], "HOLD")

    def test_timeout_fails_closed(self):
        result = self.evaluate(runner=lambda *a, **k: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("python", 180)))
        self.assertEqual(result["reason"], "NATIVE_SMOKE_EXECUTION_FAILED")

    def test_sensitive_provider_env_vars_not_passed_to_native_test(self):
        observed = {}
        def runner(*args, **kwargs):
            observed.update(kwargs)
            return completed()
        with patch.dict(os.environ, {
            "THE_ODDS_API_KEY": "secret",
            "FOOTBALL_DATA_ORG_TOKEN": "secret",
            "GITHUB_TOKEN": "secret",
            "PYTHONPATH": "/malicious/import/path",
        }):
            result = self.evaluate(runner=runner)
        self.assertEqual(result["status"], "RESEARCH_ONLY_LOCAL_SMOKE_PASSED")
        self.assertEqual(observed["check"], False)
        self.assertEqual(observed["timeout"], 180)
        self.assertTrue(observed["capture_output"])
        self.assertEqual(observed["args"] if "args" in observed else None, None)
        for key in ("THE_ODDS_API_KEY", "FOOTBALL_DATA_ORG_TOKEN",
                    "GITHUB_TOKEN", "PYTHONPATH"):
            self.assertNotIn(key, observed["env"])

    def test_receipt_is_private_and_exclusive_create(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "receipt.json"
            result = self.evaluate()
            _write_receipt_exclusive(target, result, wheel_path=self.wheel)
            self.assertIn("RESEARCH_ONLY_LOCAL_SMOKE_PASSED",
                          target.read_text(encoding="utf-8"))
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                _write_receipt_exclusive(target, result, wheel_path=self.wheel)

    def test_receipt_never_overwrites_wheel_path(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "kloppy-3.19.1-py3-none-any.whl"
            with self.assertRaisesRegex(ValueError, "RECEIPT_CANNOT_OVERWRITE_WHEEL"):
                _write_receipt_exclusive(file, self.evaluate(), wheel_path=file)


if __name__ == "__main__":
    unittest.main()
