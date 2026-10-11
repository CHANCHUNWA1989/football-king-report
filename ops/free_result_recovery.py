"""Reuse already archived no-cost result observations for forward research.

No new API queries. This is an additional SINGLE-SOURCE provisional final
candidate; neither archival provenance nor two-provider independent proof
is inferred. All rows are validated against the public free-source snapshot
contract and exact UTC times. The settlement index must continue to quarantine
any disagreement with the original result gateway.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from source_publish_guard import verify as verify_free_source

MAX_FREE_SOURCE_AGE = timedelta(hours=48)
MAX_OBSERVATIONS = 150
RESEARCH_LEAGUES = frozenset((
    "epl", "championship", "bundesliga", "laliga", "seriea", "ligue1",
))


def parse_utc(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_FINISHED_KICKOFF")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("NAIVE_FINISHED_KICKOFF")
    return stamp.astimezone(timezone.utc)


def candidates(snapshot, now):
    """Return (sanitized finished rows, diagnostics) for trusted cached input.

    Fail closed on invalid/expired audit data. Scores are explicitly *not*
    independently verified and never authorize any recommendation. Finished
    rows with no actual kickoff UTC cannot be assigned to a forecast.
    """
    result = {
        "status": "HOLD",
        "input_free_score_observations": 0,
        "accepted_free_score_candidates": 0,
        "reason": "NO_VALID_FREE_SOURCE_SNAPSHOT",
        "independently_verified": False,
        "production_recommendations": "DISABLED",
    }
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("NAIVE_OR_INVALID_AUDIT_CLOCK")
    now = now.astimezone(timezone.utc)
    if not isinstance(snapshot, dict):
        return [], result
    try:
        captured = verify_free_source(snapshot, now=now)
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        return [], result
    age = now - captured
    if not timedelta(0) <= age <= MAX_FREE_SOURCE_AGE:
        result["reason"] = "FREE_SOURCE_TOO_OLD_OR_FUTURE"
        return [], result
    rows = snapshot["sampled_fixtures"]
    if len(rows) > MAX_OBSERVATIONS:
        return [], result
    good = []
    for row in rows:
        if row["status"] != "FINISHED" or row.get("score_ft") is None:
            continue
        result["input_free_score_observations"] += 1
        try:
            kickoff = parse_utc(row["kickoff_utc"])
            score = row["score_ft"]
            # A score cannot be accepted before even the normal 90-minute
            # football match would have finished. Delay *settlement* for
            # at least 120 minutes after original kickoff.
            if (row["league"] not in RESEARCH_LEAGUES
                    or type(score) is not list or len(score) != 2
                    or not all(type(goal) is int and 0 <= goal <= 30 for goal in score)
                    or captured < kickoff + timedelta(minutes=100)
                    or now < kickoff + timedelta(minutes=120)):
                continue
            good.append({
                "league": row["league"],
                "home": row["home"], "away": row["away"],
                "kickoff_utc": kickoff.isoformat(),
                "score_ft": list(score), "status": "FINISHED",
                "source_provider": row["provider"],
                "independently_verified": False,
            })
        except (ValueError, TypeError, OverflowError):
            continue
    result["status"] = "RESEARCH_ONLY"
    result["reason"] = "SANITIZED_SINGLE_SOURCE_FINAL_CANDIDATES"
    result["accepted_free_score_candidates"] = len(good)
    return good, result


def read_candidates(path, now):
    """Refuse large, partial or malformed audit snapshots."""
    if not path:
        return candidates(None, now)
    source = Path(path)
    try:
        if not source.is_file() or source.stat().st_size > 500_000:
            return candidates(None, now)
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return candidates(None, now)
    return candidates(value, now)
