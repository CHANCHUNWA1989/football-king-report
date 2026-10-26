"""Offline integrity audit of historical CSV fixtures.

No network requests, no betting signals, and no production approval.
"""
import csv
from collections import Counter
from pathlib import Path


def audit_history(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            return {"status": "HOLD", "reason": "INVALID_HEADERS"}
        if not required.issubset(reader.fieldnames):
            return {"status": "HOLD", "reason": "MISSING_FIXTURE_FIELDS"}
        rows = list(reader)
    if not rows:
        return {"status": "HOLD", "reason": "EMPTY_HISTORY"}
    keys = []
    invalid = 0
    for row in rows:
        key = tuple((row.get(field) or "").strip() for field in ("Date", "HomeTeam", "AwayTeam"))
        try:
            home, away = int(row["FTHG"]), int(row["FTAG"])
            if not all(key) or key[1] == key[2] or home < 0 or away < 0:
                raise ValueError("BAD_FIXTURE")
        except (ValueError, TypeError, KeyError):
            invalid += 1
        keys.append(key)
    duplicate_count = sum(count - 1 for count in Counter(keys).values() if count > 1)
    return {"status": "HOLD" if invalid or duplicate_count else "OFFLINE_INTEGRITY_ONLY",
            "total_rows": len(rows), "invalid_rows": invalid,
            "duplicate_fixture_rows": duplicate_count,
            "production_recommendations": "DISABLED"}
