"""Actual current OpenLigaDB Bundesliga source -> original A + optional Penaltyblog.

NOT a historical backfill or synthetic trial. This opt-in research CI probes
the live, public 2026/27 Bundesliga source exactly ONCE. Original A's existing
poisson-shrinkage `predict_league` and both real upstream optional challengers
use earlier known final results from the same response. This does not certify
publisher identity, first-publication times of results, model accuracy, bets,
EV, or any third-party witness. No archived source bytes / API secrets leave
the runner; only limited future forecast probabilities and hashes are output.

At the first observation all historical final results are *known* by the
HTTP-response completion; `result_recorded_utc` in bridge inputs is explicitly
the local first-observed-on-this-run time, NOT a claim of first publication.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from .shadow_forecast import HK, _get_fixtures_with_native_inputs, predict_league
from .penaltyblog_a_dual_prematch_capture import A_MODEL, SCHEMA, capture
from .all_market_scenarios import ah_scenario, total_scenario

REPO_SOURCE = "https://www.openligadb.de/"
LICENSE = "OpenLigaDB community match data (ODbL 1.0)"
MAX_MATCHES = 3


def utc():
    return datetime.now(timezone.utc)


def _failing(reason, **extra):
    return {
        "status": "HOLD", "reason": reason,
        "research_only": True, "data": LICENSE,
        "source_authenticity_verified": False,
        "historical_result_publication_times_verified": False,
        "fixture_kickoff_independently_verified": False,
        "certified_prospective_samples": 0,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED", **extra,
    }


def _fail(out, message, **extra):
    report = _failing(message, **extra)
    _write(out, report)
    return 1


def _write(path, data):
    target = Path(path)
    if target.is_symlink() or target.exists():
        raise ValueError("INVALID_OR_EXISTING_PRIVATE_PROBE_OUTPUT")
    encoded = (json.dumps(data, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)+"\n").encode()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as fp:
        fp.write(encoded)
        fp.flush()
        os.fsync(fp.fileno())
    print("LIVE_RESEARCH_RESULT", encoded.decode().strip())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-targets", type=int, choices=(1,2,3), default=2)
    args = parser.parse_args(argv)
    try:
        # Fail if the original V4.1 package hasn't been cryptographically
        # pinned and unpacked in the calling research workflow.
        import fixture_gateway
    except ImportError:
        return _fail(args.output, "ORIGINAL_V41_GATEWAY_UNAVAILABLE")
    at_start = utc()
    hkt = at_start.astimezone(HK)
    season_year = hkt.year if hkt.month >= 7 else hkt.year - 1
    season = f"{season_year}-{(season_year+1)%100:02d}"
    try:
        # Same original gateway used by A, native IDs from EXACT same GET.
        original = _get_fixtures_with_native_inputs(
            season=season, league="bundesliga", clock=utc)
    except Exception as exc:
        return _fail(args.output, "LIVE_SOURCE_HTTP_OR_GATEWAY_FAILED",
                     exception_type=type(exc).__name__)

    seen_utc = utc()  # HTTP response received and normalized in THIS run
    if (original.get("status") != "READY_RESEARCH"
            or original.get("source") != "OpenLigaDB"
            or original.get("league") != "bundesliga"
            or original.get("season") != season
            or type(original.get("matches")) is not list):
        return _fail(args.output, "LIVE_BUNDESLIGA_SOURCE_NOT_READY")
    rows = original["matches"]
    source_sha = original.get("_same_response_source_sha256")
    if (type(source_sha) is not str or len(source_sha) != 64
            or source_sha != original.get("sha256")):
        return _fail(args.output, "ONE_GET_SOURCE_RESPONSE_SHA_MISSING")
    if not 1 <= len(rows) <= 1300:
        return _fail(args.output, "ORIGINAL_SOURCE_ROW_COUNT_INVALID",
                     row_count=len(rows))
    at_a = utc()
    a_rows = predict_league(rows, "bundesliga", at_a)
    if not a_rows:
        return _fail(args.output, "NO_LIVE_A_FORECAST_TARGETS",
                     source_raw_sha256_unattested=source_sha,
                     source_rows=len(rows))
    # Only history returned from THIS single real source snapshot. The time
    # label is the moment it became available to this process, not when the
    # result was originally published; this distinction stays explicit.
    hist_by_event = {}
    for row in rows:
        if type(row) is not dict or row.get("status") != "FINISHED":
            continue
        if row.get("date") >= hkt.date().isoformat():
            continue
        p = row.get("_same_response_native_fixture_input")
        score = row.get("score_ft")
        if (type(p) is not dict or
                p.get("source_response_sha256") != source_sha or
                p.get("league_shortcut") != "bl1"
                or type(row.get("event_id")) is not str or
                type(score) not in (list, tuple) or len(score) != 2
                or any(type(g) is not int or g < 0 or g > 20 for g in score)):
            continue
        from .penaltyblog_research_bridge import _timestamp
        try:
            ko = _timestamp(row["kickoff_utc"])
        except (KeyError, ValueError, TypeError):
            continue
        if ko >= seen_utc:
            continue
        key = row["event_id"]
        if key in hist_by_event:
            return _fail(args.output, "DUPLICATE_FINISHED_EVENT_IN_SOURCE")
        hist_by_event[key] = {
            "source_namespace": "openligadb",
            "event_id": key, "league_id": str(p["league_id"]),
            "home_team_id": str(p["home_team_id"]),
            "away_team_id": str(p["away_team_id"]),
            "kickoff_utc": ko.isoformat(),
            "result_recorded_utc": seen_utc.isoformat(),
            "home_goals": score[0], "away_goals": score[1],
        }
    history = list(hist_by_event.values())
    if len(history) < 30:
        return _fail(args.output, "INSUFFICIENT_REAL_SAME_RESPONSE_HISTORY",
                     real_finished_matches=len(history),
                     source_raw_sha256_unattested=source_sha)

    candidates = sorted(a_rows, key=lambda x:x["kickoff_utc"])
    outcomes = []
    for p in candidates:
        if len(outcomes) >= args.max_targets:
            break
        by_id = [r for r in rows if type(r) is dict
                 and r.get("event_id") == p["event_id"]]
        if len(by_id) != 1:
            continue
        native = by_id[0].get("_same_response_native_fixture_input")
        if (type(native) is not dict or
                native.get("source_response_sha256") != source_sha
                or native.get("league_shortcut") != "bl1"):
            continue
        selected_history = [r for r in history
                            if r["league_id"] == str(native["league_id"])]
        # A's own snapshot time must be earlier than kickoff and before the
        # optional challengers even begin. One UTC cutoff for both models.
        start = utc()
        cutoff = start + timedelta(minutes=6)
        if cutoff >= datetime.fromisoformat(p["kickoff_utc"]) - timedelta(minutes=10):
            continue
        payload = {
            "schema": SCHEMA,
            "production_recommendations": "DISABLED",
            "decision_cutoff_utc": cutoff.isoformat(),
            "original_a": {
                "source_namespace": "openligadb",
                "event_id": p["event_id"], "league_id": str(native["league_id"]),
                "home_team_id": str(native["home_team_id"]),
                "away_team_id": str(native["away_team_id"]),
                "kickoff_utc": p["kickoff_utc"],
                "produced_utc": at_a.isoformat(),
                "max_input_received_utc": seen_utc.isoformat(),
                "model_id": A_MODEL,
                "probabilities": [p["p_home"], p["p_draw"], p["p_away"]],
                "source_authenticity_verified": False,
                "independently_timestamped": False,
                "production_recommendations": "DISABLED",
            },
            "historical_matches": selected_history,
        }
        result = capture(payload)
        data = {
            "event_id": p["event_id"],
            "home": p["home"], "away": p["away"],
            "kickoff_utc": p["kickoff_utc"],
            "a_1x2": [p["p_home"],p["p_draw"],p["p_away"]],
            # Exactly the goal rates already emitted by original A, reused
            # by the pre-existing quarter-line AH / totals scenario engines.
            # Poisson/DC are compared only in 1X2 here: NO claim that
            # their goal-market probabilities were independently fitted.
            "original_a_expected_goals_home": p["expected_home_goals"],
            "original_a_expected_goals_away": p["expected_away_goals"],
            "three_market_scenario_method": "original_A_uncalibrated_goal_rates",
            "asian_handicap_hypothetical_scenarios": [
                ah_scenario(p["expected_home_goals"], p["expected_away_goals"],
                            "HOME", -0.25),
                ah_scenario(p["expected_home_goals"], p["expected_away_goals"],
                            "AWAY", 0.25),
            ],
            "over_under_hypothetical_scenarios": [
                total_scenario(p["expected_home_goals"],p["expected_away_goals"],
                               side=side,line=line)
                for side,line in (("OVER",2.5),("UNDER",2.5),
                                  ("OVER",2.75),("UNDER",2.75))
            ],
            "actual_bookmaker_lines_or_prices_verified": False,
            "ah_ou_calibrated_model_or_positive_ev_verified": False,
            "training_match_count_from_real_source": len(selected_history),
            "fit_status": result.get("reason"),
            "all_three_live_run": "unverified_triple_capture" in result,
        }
        if "unverified_triple_capture" in result:
            obs = result["unverified_triple_capture"]["challenger_observations"]
            data["poisson_1x2"] = obs[0]["probabilities"]
            data["dixon_coles_1x2"] = obs[1]["probabilities"]
            data["model_finished_utc"] = obs[-1]["local_model_finished_utc"]
            data["local_capture_sha256_unattested"] = (
                result["locally_reproducible_capture_sha256"])
        outcomes.append(data)
    completed = utc()
    completed_count = sum(1 for p in outcomes if p["all_three_live_run"])
    report = _failing(
        "LIVE_REAL_MATCH_PREMATCH_TRIAL_UNATTESTED"
        if completed_count else "LIVE_REAL_MATCH_PROSPECTIVE_MODELS_BLOCKED",
        source_url=REPO_SOURCE,
        public_source_provider="OpenLigaDB",
        source_license="ODbL 1.0",
        season=season, source_rows=len(rows),
        live_finished_matches_used=len(history),
        source_response_sha256_unattested=source_sha,
        actual_source_http_completed_utc=seen_utc.isoformat(),
        original_a_model_computed_utc=at_a.isoformat(),
        model_trial_finished_utc=completed.isoformat(),
        real_upcoming_fixtures_attempted=len(outcomes),
        real_upcoming_fixtures_with_three_model_predictions=completed_count,
        forecasts=outcomes,
        never_claim_results_after_kickoff_are_prematch=True,
        no_bookmaker_quotes_or_verified_ev=True,
        disclaimer=("Real OpenLigaDB read and real upstream model executions "
                    "in this runner, but neither raw source publisher nor "
                    "timestamp is independently signed. Zero certified "
                    "prospective model-performance samples."),
    )
    _write(args.output, report)
    return 0 if completed_count > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
