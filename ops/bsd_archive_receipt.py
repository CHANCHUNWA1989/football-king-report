"""Read-only, redacted BSD archive-branch verification receipt.

Archive snapshots may be days old. Validate their structure *as captured*,
then separately report current freshness. Stale optional research is HOLD,
not CI failure. Never certify provider identity, profit, or executable odds.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bsd_archive_reader import FILES, inspect_archive
from bsd_free import stamp
from bsd_guard import validate

FRESH_FOR_RESEARCH = timedelta(hours=12)
MAX_FUTURE_DRIFT = timedelta(minutes=5)


def _unique_json(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("BSD_ARCHIVE_DUPLICATE_JSON_FIELD")
        obj[key] = value
    return obj


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"),
                      object_pairs_hook=_unique_json,
                      parse_constant=lambda _: (_ for _ in ()).throw(
                          ValueError("BSD_ARCHIVE_NONFINITE_JSON")))


def receipt(root: Path, *, now=None):
    manifest = inspect_archive(root)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("BSD_ARCHIVE_CLOCK_NOT_AWARE")
    now = now.astimezone(timezone.utc)
    report = {
        "schema": "bsd-archive-readonly-receipt-v1",
        "source_status": None,
        "captured_utc": None,
        "market_count": 0,
        "status": "HOLD",
        "reason": "BSD_STATUS_MISSING_OPTIONAL",
        "archive_fresh_for_research": False,
        "archive_immutable": False,
        "source_authenticity_independently_verified": False,
        "market_is_executable": False,
        "production_recommendations": "DISABLED",
    }
    source = Path(root) / "sources"
    if manifest["files"][FILES[0]] == "MISSING_OPTIONAL":
        return report

    doc = _read_json(source / FILES[0])
    if not isinstance(doc, dict):
        raise ValueError("BSD_ARCHIVE_STATUS_NOT_OBJECT")
    captured = stamp(doc.get("captured_utc"))
    # Validate the original record as of its capture clock, rather than
    # treating a well-formed old archive as damaged after five days.
    validate(doc, now=captured)
    if captured > now + MAX_FUTURE_DRIFT:
        raise ValueError("BSD_ARCHIVE_FUTURE_CAPTURE")

    report["captured_utc"] = captured.isoformat()
    report["source_status"] = doc["status"]
    report["market_count"] = doc["market_count"]
    fresh = now - captured <= FRESH_FOR_RESEARCH
    report["archive_fresh_for_research"] = fresh
    if not fresh:
        report["reason"] = "BSD_STALE_OPTIONAL_HOLD"
        return report
    if doc["status"] != "RESEARCH_ONLY" or not doc["market_count"]:
        report["reason"] = "BSD_NO_QUALIFIED_MARKET"
        return report
    if manifest["files"][FILES[1]] == "MISSING_OPTIONAL":
        report["reason"] = "BSD_MISSING_MARKET_COUNTERPART"
        return report
    market = _read_json(source / FILES[1])
    if market != doc:
        report["reason"] = "BSD_MISMATCHED_MARKET_COUNTERPART"
        return report
    report["status"] = "RESEARCH_ONLY"
    report["reason"] = "BSD_OPTIONAL_RESEARCH_PAIR_MATCHES"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = receipt(args.root)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError,
            OverflowError) as exc:
        print(json.dumps({
            "schema": "bsd-archive-readonly-receipt-v1",
            "status": "HOLD",
            "reason": "BSD_INVALID_ARCHIVE_EVIDENCE",
            "error_type": type(exc).__name__,
            "production_recommendations": "DISABLED",
        }, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
