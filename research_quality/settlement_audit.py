"""Offline research-only audit of forward settlement evidence."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from research_quality.market_baseline_audit import compare

def _time(s):
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return d

def valid(row):
    if not isinstance(row, dict) or row.get("production_recommendations") != "DISABLED":
        return False
    if row.get("fixture_result_source_independently_verified") is not False:
        return False
    try:
        key = json.loads(row["key"])
        if not isinstance(key, list) or len(key) != 4 or key[0] != row["league"] or key[1] == key[2]:
            return False
        market, forecast, kickoff = (_time(row[x]) for x in ("market_utc", "forecast_utc", "kickoff_utc"))
        if (_time(key[3]) != kickoff or not market <= forecast <= kickoff - timedelta(minutes=10)
                or forecast - market > timedelta(minutes=750)):
            return False
        if type(row["y"]) is not int or row["y"] not in (0, 1, 2):
            return False
        compare([row])
        return True
    except (KeyError, ValueError, TypeError, OverflowError, AttributeError):
        return False

def audit(path):
    path = Path(path)
    if path.stat().st_size > 8_000_000:
        raise ValueError("EVIDENCE_FILE_TOO_LARGE")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("samples"), list):
        raise ValueError("INVALID_EVIDENCE_FORMAT")
    rows = data["samples"]
    if len(rows) > 20000:
        raise ValueError("TOO_MANY_EVIDENCE_ROWS")
    accepted, seen = [], set()
    for row in rows:
        if valid(row) and row["key"] not in seen:
            accepted.append(row)
            seen.add(row["key"])
    return {"status": "RESEARCH_ONLY", "total": len(rows), "accepted": len(accepted),
            "rejected": len(rows) - len(accepted), "metrics": compare(accepted),
            "independently_verified": False, "production_recommendations": "DISABLED"}
