"""Fail-closed research-only audit of manually supplied in-play evidence.

Does not fetch bookmaker prices, calculate EV, publish picks or unlock production.
Fresh capture time alone does not prove upstream freshness or source authenticity.
"""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("TIMESTAMP_MISSING")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMEZONE_MISSING")
    return dt.astimezone(timezone.utc)


def audit_live_snapshot(snapshot, *, max_age_seconds=90):
    """Audit one consistent evidence cut; never certify positive EV.

    Required quote line is the signed handicap on the selected side, or the
    total-goals threshold. This validator checks only structure and timing,
    NOT the vendor's licence, true bookability or probability calibration.
    """
    out = {
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "certified_positive_ev": False,
        "source_authenticity_verified": False,
        "market_executable_verified": False,
        "probability_calibrated": False,
        "reasons": [],
    }
    if not isinstance(snapshot, dict):
        out["reasons"].append("INVALID_SNAPSHOT")
        return out
    try:
        if (type(max_age_seconds) not in (int, float)
                or not math.isfinite(max_age_seconds)
                or not 0 < max_age_seconds <= 300):
            raise ValueError("INVALID_AGE_LIMIT")
        event_id = snapshot["event_id"]
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("EVENT_ID_MISSING")
        now = _utc(snapshot["decision_utc"])
        kickoff = _utc(snapshot["kickoff_utc"])
        if now < kickoff:
            raise ValueError("NOT_IN_PLAY")
        records = {key: snapshot[key] for key in ("score", "stats", "quote")}
        if not all(isinstance(r, dict) for r in records.values()):
            raise ValueError("INVALID_RECORD")
        upstream_times = {}
        for key, record in records.items():
            if record.get("event_id") != event_id:
                raise ValueError("EVENT_ID_MISMATCH")
            if not isinstance(record.get("source"), str) or not record["source"].strip():
                raise ValueError("SOURCE_MISSING")
            updated = _utc(record["upstream_updated_utc"])
            captured = _utc(record["captured_utc"])
            if not kickoff <= updated <= captured <= now:
                raise ValueError("INVALID_TIME_ORDER")
            if (now - updated).total_seconds() > max_age_seconds:
                raise ValueError("STALE_UPSTREAM")
            upstream_times[key] = updated

        # Fail closed when the apparent current score is newer than the
        # statistical state or bookmaker quote. A quote before the latest
        # score update could be priced for the previous score.
        if not upstream_times["score"] <= upstream_times["stats"]:
            raise ValueError("STATS_BEFORE_SCORE")
        if not upstream_times["stats"] <= upstream_times["quote"]:
            raise ValueError("QUOTE_BEFORE_STATS_OR_SCORE")

        score = records["score"]
        if (type(score.get("home_goals")) is not int
                or type(score.get("away_goals")) is not int
                or min(score["home_goals"], score["away_goals"]) < 0):
            raise ValueError("INVALID_SCORE")

        stats = records["stats"]
        for key in ("home_xg", "away_xg"):
            value = stats.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("INVALID_XG")

        quote = records["quote"]
        market = quote.get("market")
        selection = quote.get("selection")
        if market == "totals":
            if selection not in ("over", "under"):
                raise ValueError("TOTAL_SELECTION_MISSING")
        elif market == "asian_handicap":
            if selection not in ("home", "away"):
                raise ValueError("HANDICAP_SELECTION_MISSING")
        else:
            raise ValueError("UNSUPPORTED_MARKET")
        if quote.get("in_play") is not True:
            raise ValueError("NOT_LIVE_QUOTE")
        line, price = quote.get("line"), quote.get("decimal_price")
        if (type(line) not in (float, int) or not math.isfinite(line)
                or type(price) not in (float, int) or not math.isfinite(price)
                or price <= 1 or abs(line * 4 - round(line * 4)) > 1e-9):
            raise ValueError("INVALID_QUOTE")
        if market == "totals" and line < 0:
            raise ValueError("INVALID_TOTAL_LINE")
        if not isinstance(quote.get("bookmaker"), str) or not quote["bookmaker"].strip():
            raise ValueError("BOOKMAKER_MISSING")

        out["status"] = "RESEARCH_ONLY"
        out["reasons"] = ["TIMING_CHECK_PASSED_NOT_VERIFIED_EV"]
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        reason = str(exc).strip("'") if str(exc) else "INVALID_DATA"
        out["reasons"].append(reason)
    return out


def main(argv=None):
    """Standalone offline check of authorized JSON evidence; no network calls."""
    parser = argparse.ArgumentParser(description="In-play research input safety check; never a betting signal")
    parser.add_argument("snapshot", type=Path, help="Local JSON with score, stats and in-play market evidence")
    args = parser.parse_args(argv)
    try:
        if args.snapshot.stat().st_size > 512_000:
            raise ValueError("INPUT_TOO_LARGE")
        with args.snapshot.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        # Always evaluate freshness relative to the actual execution clock.
        # A snapshot must not arbitrarily claim an earlier decision clock.
        if not isinstance(payload, dict):
            raise ValueError("INVALID_SNAPSHOT")
        payload["decision_utc"] = datetime.now(timezone.utc).isoformat()
        result = audit_live_snapshot(payload)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        result = {
            "status": "HOLD",
            "production_recommendations": "DISABLED",
            "certified_positive_ev": False,
            "reasons": [str(exc) if str(exc) else "INPUT_READ_FAILED"],
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "RESEARCH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
