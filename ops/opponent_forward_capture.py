"""Capture paired A vs opponent-strength challenger in one public pre-match run.

Research only. This module obtains current *normalized* public fixture rows
through the existing no-key fixture gateway and computes both models from the
same in-memory input at one observed time. It NEVER scores results, ingests
bookmaker odds, reconstructs past as-of inputs, or labels an injected clock as
independent evidence. GitHub Actions artifacts have limited retention and are
not external immutability witnesses.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

from opponent_adjusted_goals_challenger import compare_shadow
from shadow_forecast import LEAGUES

HK = ZoneInfo("Asia/Hong_Kong")
SCHEMA = "football-king-opponent-paired-forward-observation-v1"
MAX_BATCH_SECONDS = 240
MAX_CAPTURE_AGE_SECONDS = 900
MIN_LEAD_SECONDS = 600
MAX_ROWS = 6000


def _utc(value):
    if type(value) is not str or len(value) > 45:
        raise ValueError("INVALID_CAPTURE_UTC")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        raise ValueError("INVALID_CAPTURE_UTC") from None
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("INVALID_CAPTURE_UTC")
    return dt.astimezone(timezone.utc)


def _clock(clock):
    value = clock()
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("INVALID_RUN_CLOCK")
    return value.astimezone(timezone.utc)


def _hold(league, reason):
    return {
        "schema": SCHEMA,
        "league": league,
        "status": "HOLD",
        "reason": reason,
        "candidates": [],
        "candidate_count": 0,
        "production_recommendations": "DISABLED",
        "source_capture_authenticated": False,
        "normalized_source_rows_cryptographically_attested": False,
        "model_clock_externally_attested": False,
        "historical_results_independently_verified": False,
        "eligible_for_formal_forward_scoring": False,
        "model_accuracy_improved": False,
        "positive_ev_verified": False,
        "market_quotes_queried": False,
        "original_forecasts_modified": False,
    }


def _season(clock):
    hkt = clock.astimezone(HK)
    first_year = hkt.year if hkt.month >= 7 else hkt.year - 1
    return f"{first_year}-{(first_year+1)%100:02d}"


def capture(league, getter, *, clock, commit_sha=None):
    """Fail-closed paired observation; explicit clock/getter used for tests only.

    No result is used. Provider's self-declared captured_utc is a consistency
    check, NOT an independent timestamp witness.
    """
    if type(league) is not str or league not in LEAGUES:
        return _hold(league, "UNSUPPORTED_LEAGUE")
    try:
        entered = _clock(clock)
    except (ValueError, TypeError):
        return _hold(league, "INVALID_RUN_CLOCK")
    try:
        response = getter(season=_season(entered), league=league, clock=clock)
        fetched = _clock(clock)
    except Exception:
        return _hold(league, "SOURCE_FETCH_FAILED")
    if (type(response) is not dict
            or response.get("status") != "READY_RESEARCH"
            or type(response.get("matches")) is not list
            or len(response["matches"]) > MAX_ROWS
            or type(response.get("source")) is not str
            or not response["source"]):
        return _hold(league, "SOURCE_MISSING_OR_INVALID")
    try:
        provider_claimed_capture = _utc(response.get("captured_utc"))
    except ValueError:
        return _hold(league, "SOURCE_CAPTURE_TIME_UNKNOWN")
    if not (entered <= fetched and provider_claimed_capture <= fetched
            and fetched - provider_claimed_capture <= timedelta(seconds=MAX_CAPTURE_AGE_SECONDS)
            and fetched - entered <= timedelta(seconds=MAX_BATCH_SECONDS)
            and entered.astimezone(HK).date() == fetched.astimezone(HK).date()):
        return _hold(league, "SOURCE_CAPTURE_STALE_OR_CLOCK_CONFLICT")
    # The same in-memory snapshot is provided to ORIGINAL A and challenger.
    try:
        paired = compare_shadow(response["matches"], league=league, now=fetched)
    except (ValueError, TypeError, OverflowError, ArithmeticError):
        return _hold(league, "PAIRED_MODEL_FAILED")
    try:
        completed = _clock(clock)
    except (ValueError, TypeError):
        return _hold(league, "FINAL_RUN_CLOCK_INVALID")
    if (not entered <= fetched <= completed
            or completed - entered > timedelta(seconds=MAX_BATCH_SECONDS)
            or entered.astimezone(HK).date() != completed.astimezone(HK).date()):
        return _hold(league, "COMPUTE_CLOCK_CROSSED_BOUNDARY")
    if (paired.get("status") != "RESEARCH_ONLY"
            or paired.get("production_recommendations") != "DISABLED"
            or paired.get("analysis_clock_is_supplied_not_attested") is not True
            or type(paired.get("comparisons")) is not list):
        result = _hold(league, "NO_SAFE_PAIRED_CANDIDATES")
        result["source_claimed_captured_utc"] = provider_claimed_capture.isoformat()
        result["snapshot_model_asof_utc"] = fetched.isoformat()
        result["base_challenger_reason"] = paired.get("reason")
        return result
    try:
        normalized_hash = hashlib.sha256(json.dumps(
            response["matches"], ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest()
    except (TypeError, ValueError, OverflowError):
        return _hold(league, "INVALID_NORMALIZED_SOURCE_ROWS")
    if type(commit_sha) is not str or not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        commit_sha = None
    candidates = []
    seen = set()
    for pair in paired["comparisons"]:
        if type(pair) is not dict:
            return _hold(league, "INVALID_PAIRED_RECORD")
        event_id = pair.get("event_id_unverified")
        if (type(event_id) is not str or not event_id
                or len(event_id) > 128 or event_id in seen):
            return _hold(league, "DUPLICATE_OR_MISSING_EVENT_ID")
        seen.add(event_id)
        try:
            kickoff = _utc(pair["kickoff_utc_source_claim"])
        except (KeyError, ValueError, TypeError):
            return _hold(league, "INVALID_CANDIDATE_KICKOFF")
        if not completed + timedelta(seconds=MIN_LEAD_SECONDS) < kickoff:
            # No partially mature forecast packets; this is all-or-nothing.
            return _hold(league, "CANDIDATE_KICKOFF_TOO_CLOSE")
        original, challenger = pair.get("original_shadow"), pair.get("candidate")
        if (type(original) is not dict or type(challenger) is not dict
                or challenger.get("betting_eligible") is not False
                or challenger.get("improvement_proven") is not False
                or pair.get("as_of_utc_self_declared") != fetched.isoformat()):
            return _hold(league, "UNSAFE_PAIRED_MODEL_RECORD")
        if any(type(obj.get(k)) not in (float, int)
               or not 0 < obj[k] < 1 for obj in (original, challenger)
               for k in ("p_home", "p_draw", "p_away")):
            return _hold(league, "INVALID_PAIRED_PROBABILITIES")
        if any(abs(sum(obj[k] for k in ("p_home", "p_draw", "p_away")) - 1) > 1e-5
               for obj in (original, challenger)):
            return _hold(league, "NONNORMALIZED_PAIRED_PROBABILITIES")
        if original.get("training_observations_sha256") != pair.get(
                "training_observations_sha256"):
            return _hold(league, "ORIGINAL_TRAINING_COHORT_MISMATCH")
        candidates.append({
            "league": league,
            "source_event_id_unverified": event_id,
            "home_source_name_unverified": pair.get("home_source_name_unverified"),
            "away_source_name_unverified": pair.get("away_source_name_unverified"),
            "kickoff_utc_source_claim": kickoff.isoformat(),
            "asof_utc": fetched.isoformat(),
            "computation_completed_utc": completed.isoformat(),
            "source_normalized_rows_sha256_not_raw_capture_proof": normalized_hash,
            "original_training_sha256": pair["training_observations_sha256"],
            "original_A": {k: original.get(k) for k in (
                "model", "p_home", "p_draw", "p_away",
                "expected_home_goals", "expected_away_goals")},
            "opponent_strength_candidate": {k: challenger.get(k) for k in (
                "model", "p_home", "p_draw", "p_away",
                "expected_home_goals", "expected_away_goals")},
            "result_or_settlement_included": False,
            "formal_forward_evidence_verified": False,
            "production_recommendations": "DISABLED",
        })
    if not candidates:
        return _hold(league, "NO_TIME_ELIGIBLE_CANDIDATES")
    return {
        **_hold(league, "UNAUTHENTICATED_RESEARCH_OBSERVATION"),
        "status": "RESEARCH_ONLY",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "source_provider_claim": response["source"],
        "source_claimed_captured_utc": provider_claimed_capture.isoformat(),
        "run_entered_utc": entered.isoformat(),
        "snapshot_model_asof_utc": fetched.isoformat(),
        "computation_completed_utc": completed.isoformat(),
        "normalized_input_sha256_not_raw_source_proof": normalized_hash,
        "git_commit_sha_unverified_metadata": commit_sha,
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--league", choices=LEAGUES, required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)
    # Original V4.1 package is unpacked by the separate research-only workflow.
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "app"))
    try:
        from fixture_gateway import get_fixtures
        report = capture(
            args.league, get_fixtures, clock=lambda: datetime.now(timezone.utc),
            commit_sha=os.environ.get("GITHUB_SHA"))
    except (ImportError, OSError):
        report = _hold(args.league, "FIXTURE_GATEWAY_NOT_AVAILABLE")
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                               sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "league": args.league,
        "status": report["status"],
        "candidates": report["candidate_count"],
        "reason": report["reason"],
        "production_recommendations": "DISABLED",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
