"""Research-only in-play total-goals line audit.

A market threshold is NOT a Poisson expected-goal mean. The time-only
reference below is a rough movement diagnostic, not a probability, EV,
or proof of bookmaker intent. Single-bookmaker paired snapshots only.
No provider queries, keys, wagering or production recommendations.
"""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "football-king-inplay-total-decay-v1"
MAX_QUOTE_AGE_SECONDS = 300


def _utc(value):
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.astimezone(timezone.utc) if stamp.tzinfo else None


def _line(value):
    return (type(value) in (int, float) and math.isfinite(value)
            and 0.25 <= value <= 15
            and abs(value * 4 - round(value * 4)) < 1e-9)


def _id(value):
    return isinstance(value, str) and 1 <= len(value.strip()) <= 128


def analyze(payload):
    """Fail closed for mismatched, expired or untraceable price snapshots."""
    out = {
        "schema": SCHEMA,
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "betting_recommendation": False,
        "positive_ev_verified": False,
        "market_signal_verified": False,
        "line_is_expected_goals": False,
        "time_only_reference_is_predictive": False,
        "reasons": [],
    }
    if not isinstance(payload, dict):
        out["reasons"].append("INVALID_INPUT")
        return out
    if not (_id(payload.get("fixture_id")) and _id(payload.get("bookmaker_id"))
            and payload.get("market") == "full_time_total_goals"
            and payload.get("source_kind") == "MANUALLY_TRANSCRIBED"):
        out["reasons"].append("MISSING_SAME_BOOKMAKER_MARKET_IDENTITY")
    opening, current = payload.get("opening"), payload.get("current")
    if not isinstance(opening, dict) or not isinstance(current, dict):
        out["reasons"].append("MISSING_PAIRED_QUOTES")
        return out
    if not (_line(opening.get("line")) and _line(current.get("line"))):
        out["reasons"].append("INVALID_QUARTER_GOAL_LINE")
    if (opening.get("fixture_id", payload.get("fixture_id")) != payload.get("fixture_id")
            or current.get("fixture_id", payload.get("fixture_id")) != payload.get("fixture_id")
            or opening.get("bookmaker_id", payload.get("bookmaker_id")) != payload.get("bookmaker_id")
            or current.get("bookmaker_id", payload.get("bookmaker_id")) != payload.get("bookmaker_id")):
        out["reasons"].append("MISMATCHED_QUOTE_IDENTITY")
    minute, goals = current.get("match_minute"), current.get("goals_scored")
    if (type(minute) not in (int, float) or not math.isfinite(minute)
            or minute < 0 or minute > 90
            or type(goals) is not int or goals < 0 or goals > 20):
        out["reasons"].append("INVALID_LIVE_SCORE_OR_CLOCK")
    checked = _utc(payload.get("checked_at_utc"))
    kickoff = _utc(payload.get("kickoff_utc"))
    before = _utc(opening.get("quoted_at_utc"))
    after = _utc(current.get("quoted_at_utc"))
    if not all((checked, kickoff, before, after)):
        out["reasons"].append("MISSING_TIMEZONE_AWARE_TIMESTAMPS")
    else:
        age = (checked - after).total_seconds()
        if not (before < kickoff <= after <= checked and 0 <= age <= MAX_QUOTE_AGE_SECONDS):
            out["reasons"].append("STALE_OR_NONCHRONOLOGICAL_QUOTE")
        # Wall time and match clock diverge at half-time; only reject impossible clocks.
        if after < kickoff or (after - kickoff).total_seconds() / 60 + 3 < (
                minute if type(minute) in (int, float) else 0):
            out["reasons"].append("IMPOSSIBLE_MATCH_CLOCK")
    if opening.get("goals_scored") != 0:
        out["reasons"].append("OPENING_QUOTE_NOT_PREGAME")
    if out["reasons"]:
        return out

    # A quoted totals line is a threshold, not estimated goals. This is
    # strictly an informal clock-adjusted comparison, NEVER fair odds.
    reference = goals + float(opening["line"]) * (90.0 - float(minute)) / 90.0
    delta = float(current["line"]) - float(opening["line"])
    residual = float(current["line"]) - reference
    out.update({
        "status": "RESEARCH_ONLY",
        "reasons": ["LINE_THRESHOLD_NOT_A_GOAL_EXPECTATION",
                    "CLOCK_REFERENCE_NOT_EVIDENCE_OF_SMART_MONEY"],
        "fixture_id": payload["fixture_id"],
        "bookmaker_id": payload["bookmaker_id"],
        "quoted_at_utc": after.isoformat(),
        "match_minute": float(minute),
        "goals_scored": goals,
        "opening_line": float(opening["line"]),
        "current_line": float(current["line"]),
        "raw_line_change": round(delta, 3),
        "time_only_line_reference": round(reference, 3),
        "line_minus_reference": round(residual, 3),
        "diagnostic": ("CLOCK_ONLY_REFERENCE_CLOSE" if abs(residual) < 0.50
                       else "REQUIRES_INDEPENDENT_REVIEW"),
        "independent_bookmaker_consensus_verified": False,
        "model_calibrated": False,
        "executable_odds_verified": False,
    })
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="Offline in-play totals research audit")
    p.add_argument("--input", required=True, help="Paired single-bookmaker quote JSON")
    p.add_argument("--output")
    args = p.parse_args(argv)
    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        payload = None
    out = analyze(payload)
    serial = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(serial, encoding="utf-8")
    print(serial, end="")
    return 0 if out["status"] == "RESEARCH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
