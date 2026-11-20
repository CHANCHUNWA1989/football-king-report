"""Fail-closed repository safety CI coverage; never calls football providers.

The two independent unittest collections must both exist, execute at least
one test, and pass. Unittest discovery otherwise exits 0 when it finds
zero tests, which is not proof that the safety suite executed.
"""
import re
import subprocess
import sys
from pathlib import Path

SUITES = ("tests", "ops/tests")
_RAN = re.compile(r"(?m)^Ran ([0-9]+) tests? in ")


class UnsafeTestScope(ValueError):
    """A required suite is absent, empty, undiscovered or failing."""


def assert_source_files(root, suite):
    """Check a fixed repository-relative suite before invoking unittest."""
    if suite not in SUITES:
        raise UnsafeTestScope("UNAPPROVED_TEST_SUITE")
    folder = Path(root) / suite
    if not folder.is_dir() or folder.is_symlink():
        raise UnsafeTestScope("REQUIRED_TEST_DIRECTORY_MISSING: " + suite)
    discovered = [p for p in folder.glob("test*.py")
                  if p.is_file() and not p.is_symlink() and p.stat().st_size > 0]
    if not discovered:
        raise UnsafeTestScope("REQUIRED_TEST_SOURCES_MISSING: " + suite)
    return len(discovered)


def run_suite(root, suite):
    """Run the real test collection and reject false-green zero-discovery."""
    files = assert_source_files(root, suite)
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover",
         "-s", suite, "-p", "test*.py", "-q"],
        cwd=str(Path(root).resolve()), capture_output=True, text=True,
        check=False,
    )
    # unittest's authoritative final summary is written to stderr.
    # Import-time test-module prints can spoof earlier "Ran N tests" lines in
    # either stream. Read the LAST stderr summary, never the first match
    # across user-controlled stdout and stderr.
    stderr = completed.stderr or ""
    transcript = (completed.stdout or "") + "\n" + stderr
    summaries = _RAN.findall(stderr)
    count = int(summaries[-1]) if summaries else 0
    if completed.returncode != 0 or count == 0:
        # Include bounded failure detail; CI has no provider secrets.
        raise UnsafeTestScope(
            "TEST_SCOPE_NOT_PROVEN: " + suite +
            "; exit=" + str(completed.returncode) +
            "; discovered=" + str(count) + "\n" + transcript[-6000:]
        )
    return {"suite": suite, "test_files": files, "tests_executed": count}


def main():
    root = Path(__file__).resolve().parents[1]
    try:
        for suite in SUITES:
            report = run_suite(root, suite)
            print("PASS " + report["suite"] + ": " +
                  str(report["tests_executed"]) + " tests executed from " +
                  str(report["test_files"]) + " files", flush=True)
    except UnsafeTestScope as exc:
        print("FAIL CLOSED: " + str(exc), file=sys.stderr)
        return 1
    print("REPOSITORY_SAFETY_SCOPES_PASSED; NOT_MODEL_CERTIFICATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
