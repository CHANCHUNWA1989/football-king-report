"""Offline RFC3161 TSA token verification gate; research only.

OpenSSL verifies CMS signature, trust chain and data imprint. The parser only
accepts a narrow English UTC OpenSSL text format; unknown output fails closed.
TSA trust anchors must be independently provisioned, never downloaded here.
"""
import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

_STAMP = re.compile(r"^Time stamp:\s*([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})\s+(\d{4})\s+GMT\s*$", re.MULTILINE)


def verify(receipt_path, token_path, ca_path, kickoff_utc, *, openssl="openssl", runner=subprocess.run):
    hold = {"status": "HOLD", "production_recommendations": "DISABLED",
            "independently_timestamped": False, "positive_ev_verified": False}
    try:
        for path in (receipt_path, token_path, ca_path):
            p = Path(path)
            if not p.is_file() or p.is_symlink() or p.stat().st_size == 0:
                raise ValueError("MISSING_OR_UNSAFE_INPUT")
        kickoff = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
        if kickoff.tzinfo is None or kickoff.utcoffset() is None:
            raise ValueError("NAIVE_KICKOFF")
        verify_cmd = [openssl, "ts", "-verify", "-in", str(token_path),
                      "-data", str(receipt_path), "-CAfile", str(ca_path)]
        checked = runner(verify_cmd, capture_output=True, text=True, timeout=20, check=False)
        if checked.returncode != 0:
            raise ValueError("TSA_SIGNATURE_OR_IMPRINT_UNTRUSTED")
        describe = runner([openssl, "ts", "-reply", "-in", str(token_path), "-text"],
                          capture_output=True, text=True, timeout=20, check=False)
        if describe.returncode != 0:
            raise ValueError("INVALID_TIMESTAMP_TOKEN")
        matches = _STAMP.findall(describe.stdout)
        if len(matches) != 1:
            raise ValueError("UNRECOGNIZED_TIMESTAMP_FORMAT")
        month, day, clock, year = matches[0]
        stamped = datetime.strptime(f"{month} {day} {clock} {year}",
                                    "%b %d %H:%M:%S %Y").replace(tzinfo=timezone.utc)
        if stamped >= kickoff.astimezone(timezone.utc):
            raise ValueError("TIMESTAMP_NOT_BEFORE_KICKOFF")
        return {**hold, "status": "CRYPTOGRAPHIC_TIMESTAMP_CHECK_PASSED",
                "timestamp_utc": stamped.isoformat(),
                "signature_and_imprint_verified": True,
                "independently_timestamped": False,
                "reason": "TSA_POLICY_AND_PROVENANCE_REVIEW_REQUIRED"}
    except (ValueError, OSError, subprocess.TimeoutExpired, TypeError, AttributeError) as exc:
        return {**hold, "reason": str(exc) if isinstance(exc, ValueError) else "VERIFIER_ERROR"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--ca", required=True)
    parser.add_argument("--kickoff-utc", required=True)
    args = parser.parse_args()
    result = verify(args.receipt, args.token, args.ca, args.kickoff_utc)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "CRYPTOGRAPHIC_TIMESTAMP_CHECK_PASSED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
