"""Local, fail-closed Kloppy 3.19.1 native smoke acceptance.

This script does not download, install or fetch provider match data. Run it
ONLY inside a reviewed isolated virtual environment with an already vetted
Kloppy wheel and dependencies. Success is *local research evidence* only:
no independent source attestation, model certification or permission to bet.
"""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from ops.kloppy_offline_wheel_preflight import UnsafeWheel, verify_official_kloppy_wheel

SCHEMA = "football-king-local-kloppy-native-smoke-v1"
TEST_MODULE = "ops.tests.kloppy_native_real_smoke"
REQUIRED_TESTS = 2
MAX_SECONDS = 180


def _hold(reason):
    return {
        "schema": SCHEMA,
        "status": "HOLD",
        "reason": reason,
        "wheel_sha256_verified_locally": False,
        "installed_native_version_verified_locally": False,
        "real_native_tests_executed": False,
        "real_native_tests_passed_locally": False,
        "independent_software_provenance_verified": False,
        "third_party_dependencies_independently_audited": False,
        "licensed_match_data_verified": False,
        "forward_samples_certified": 0,
        "model_promoted": False,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }


def verify_local_native_smoke(wheel_path, *, _version=None, _runner=None):
    """Fail closed; injection hooks are private and used only in synthetic tests."""
    outcome = _hold("LOCAL_SMOKE_NOT_PERFORMED")
    try:
        evidence = verify_official_kloppy_wheel(wheel_path)
    except (UnsafeWheel, OSError, ValueError):
        outcome["reason"] = "OFFICIAL_WHEEL_PREFLIGHT_FAILED"
        return outcome
    outcome["wheel_sha256_verified_locally"] = True
    if _version is None:
        _version = importlib.metadata.version
    try:
        installed = _version("kloppy")
    except (importlib.metadata.PackageNotFoundError, ImportError, OSError, ValueError):
        outcome["reason"] = "KLOPPY_NOT_INSTALLED"
        return outcome
    if installed != "3.19.1":
        outcome["reason"] = "WRONG_INSTALLED_KLOPPY_VERSION"
        return outcome
    outcome["installed_native_version_verified_locally"] = True
    if _runner is None:
        _runner = subprocess.run
    # No network data, credentials or user files are provided to this process.
    # A disposable HOME prevents tests from searching a user's service config.
    try:
        with tempfile.TemporaryDirectory(prefix="kloppy-native-smoke-") as home:
            allowed = {"PATH", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR", "VIRTUAL_ENV"}
            env = {key: val for key, val in os.environ.items() if key in allowed}
            env.update({"HOME": home, "PYTHONNOUSERSITE": "1",
                        "PYTHONDONTWRITEBYTECODE": "1"})
            completed = _runner(
                [sys.executable, "-m", "unittest", TEST_MODULE, "-v"],
                cwd=str(Path(__file__).resolve().parent.parent),
                env=env, capture_output=True, text=True, timeout=MAX_SECONDS,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        outcome["reason"] = "NATIVE_SMOKE_EXECUTION_FAILED"
        return outcome
    outcome["real_native_tests_executed"] = True
    # Do not trust prints from test-controlled stdout; unittest's final test
    # count belongs to stderr. The process must also exit 0 and report OK.
    stderr = completed.stderr or ""
    counts = re.findall(r"(?m)^Ran (\d+) tests? in [^\n]+", stderr)
    total = int(counts[-1]) if counts else 0
    if (completed.returncode != 0 or total < REQUIRED_TESTS
            or not re.search(r"(?m)^OK(?: \(skipped=\d+\))?\s*$", stderr)
            or "skipped=" in stderr):
        outcome["reason"] = "NATIVE_SMOKE_TESTS_NOT_PASSED"
        return outcome
    outcome["status"] = "RESEARCH_ONLY_LOCAL_SMOKE_PASSED"
    outcome["reason"] = "LOCAL_WHEEL_AND_NATIVE_OBJECT_TESTS_PASSED_NOT_CERTIFIED"
    outcome["real_native_tests_passed_locally"] = True
    outcome["local_native_test_count"] = total
    outcome["wheel_sha256"] = evidence["sha256"]
    return outcome


def _write_receipt_exclusive(path, result, *, wheel_path):
    target = Path(path)
    if target.resolve() == Path(wheel_path).resolve():
        raise ValueError("RECEIPT_CANNOT_OVERWRITE_WHEEL")
    # An existing file or symlink must never be replaced.
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(result, output, indent=2, ensure_ascii=False, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local-only Kloppy smoke acceptance")
    parser.add_argument("--wheel", required=True, help="Existing official PyPI wheel path")
    parser.add_argument("--receipt", help="New local JSON receipt file; exclusive create")
    args = parser.parse_args(argv)
    report = verify_local_native_smoke(args.wheel)
    if args.receipt:
        try:
            _write_receipt_exclusive(args.receipt, report, wheel_path=args.wheel)
        except (OSError, ValueError) as exc:
            print("HOLD: RECEIPT_NOT_WRITTEN: " + type(exc).__name__, file=sys.stderr)
            return 1
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "RESEARCH_ONLY_LOCAL_SMOKE_PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
