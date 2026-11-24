"""Strict intake for separately sourced scored historical fixtures.

No external fetch, no data fabrication, no claims of independent authentication.
Designed for private ephemeral runner use; never publish raw fixture history.
"""
import json
from pathlib import Path
from ops.penaltyblog_research_bridge import _fixture, _MATCH_FIELDS, _timestamp

SCHEMA = "football-king-private-history-v1"


def validate(payload):
    if (not isinstance(payload, dict) or set(payload) !=
            {"schema", "production_recommendations", "source", "matches"}
            or payload.get("schema") != SCHEMA
            or payload.get("production_recommendations") != "DISABLED"
            or not isinstance(payload.get("source"), str)
            or not payload["source"].strip()
            or not isinstance(payload.get("matches"), list)
            or not 30 <= len(payload["matches"]) <= 2500):
        raise ValueError("INVALID_HISTORY_CONTRACT")
    seen = set()
    for row in payload["matches"]:
        kickoff = _fixture(row, _MATCH_FIELDS)
        result_time = _timestamp(row["result_recorded_utc"])
        if not kickoff < result_time:
            raise ValueError("INVALID_RESULT_CHRONOLOGY")
        for k in ("home_goals", "away_goals"):
            if type(row[k]) is not int or not 0 <= row[k] <= 20:
                raise ValueError("INVALID_GOALS")
        key = (row["source_namespace"], row["event_id"])
        if key in seen:
            raise ValueError("DUPLICATE_HISTORY")
        seen.add(key)
    return payload["matches"]


def load(path):
    p = Path(path)
    if not p.is_file() or p.stat().st_size > 2_000_000:
        raise ValueError("MISSING_OR_OVERSIZE_HISTORY")
    with p.open(encoding="utf-8") as fh:
        payload = json.load(fh, object_pairs_hook=_unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
    return validate(payload)


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("DUPLICATE_JSON_KEY")
        out[key] = value
    return out
