"""Bounded stress and crash-injection harness for research evidence chain."""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from prematch_evidence_chain import verify_evidence_chain
from prematch_integrity_report import evidence_integrity_report

WORKER = """import sys,time
sys.path.insert(0,sys.argv[1])
from prematch_raw_archive import archive_response
from prematch_evidence_chain import append_evidence
for i in range(int(sys.argv[4])):
 archive=archive_response(('p11-'+sys.argv[3]+'-'+str(i)).encode(),directory=sys.argv[2])
 for retry in range(5000):
  try:
   append_evidence(sys.argv[2],archive)
   break
  except BlockingIOError:
   time.sleep(.002)
 else:
  sys.exit(4)
"""


def run_stress(*, workers=4, writes_per_worker=20, timeout_seconds=90):
    if (type(workers) is not int or not 1 <= workers <= 16 or
            type(writes_per_worker) is not int or not 1 <= writes_per_worker <= 200 or
            type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 600):
        raise ValueError("invalid stress bounds")
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as root:
        children = [subprocess.Popen([sys.executable, "-c", WORKER,
                    str(Path(__file__).resolve().parent), root, str(i),
                    str(writes_per_worker)], stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE) for i in range(workers)]
        try:
            failures = []
            for child in children:
                remaining = max(.01, timeout_seconds - (time.monotonic() - started))
                _, error = child.communicate(timeout=remaining)
                if child.returncode != 0:
                    failures.append({"exit_code": child.returncode,
                                     "stderr": error.decode(errors="replace")[-500:]})
        except subprocess.TimeoutExpired:
            for child in children:
                if child.poll() is None:
                    child.kill()
            for child in children:
                child.wait()
            return {"status": "HOLD", "reason": "STRESS_TIMEOUT"}
        report = evidence_integrity_report(root)
        expected = workers * writes_per_worker
        valid = (not failures and report["chain_verified"] and
                 report["archive_entries"] == expected and
                 report["unique_archive_digests"] == expected and
                 not report["rejection_reasons"])
        return {"status": "RESEARCH_ONLY" if valid else "HOLD",
                "expected_writes": expected, "observed_writes": report["archive_entries"],
                "duration_seconds": round(time.monotonic() - started, 3),
                "failures": failures, "integrity": report,
                "production_recommendations": "DISABLED"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--writes-per-worker", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=int, default=90)
    args = parser.parse_args()
    print(json.dumps(run_stress(workers=args.workers,
        writes_per_worker=args.writes_per_worker,
        timeout_seconds=args.timeout_seconds), sort_keys=True))
