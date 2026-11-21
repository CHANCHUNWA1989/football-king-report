"""Pre-match side-by-side A/B audit: ORIGINAL Poisson vs canonical identity repair.

The same immutable normalized fixture rows and exact UTC prediction clock are
passed to both frozen engines. No outcomes, bookmaker lines, EV or model tuning.
A missing prediction is counted as missing, NEVER quietly omitted or scored.
This evaluates *changes*, NOT whether the new model is more accurate.
"""
import argparse
import copy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re

try:
    from . import identity_ab_legacy_poisson as frozen
    from .shadow_forecast import predict_league as candidate_predict
    from .role_history_quality import verify as verify_role
    from .team_identity import team_id
    from .home_favourite_sentinel import assess as home_bias_cohort
except ImportError:
    import identity_ab_legacy_poisson as frozen
    from shadow_forecast import predict_league as candidate_predict
    from role_history_quality import verify as verify_role
    from team_identity import team_id
    from home_favourite_sentinel import assess as home_bias_cohort

LEAGUES = frozenset(("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1"))
SCHEMA = "football-king-identity-ab-prekickoff-v1"
INPUT_SCHEMA = "football-king-identity-ab-input-v1"
MAX_ROWS = 4000
MAX_FORECASTS = 1000


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _instant(value):
    _require(type(value) is str and len(value) <= 60, "INVALID_AB_CLOCK")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(dt.tzinfo is not None and dt.utcoffset() is not None,
                 "INVALID_AB_CLOCK")
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("INVALID_AB_CLOCK") from None


def _canonical(rows):
    try:
        result = json.dumps(rows, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False)
        if len(result.encode("utf-8")) > 5_000_000:
            raise ValueError("OVERSIZED_AB_INPUT")
        return result.encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ValueError("INVALID_AB_INPUT") from None


def _check_input(rows, league, as_of):
    _require(type(rows) is list and len(rows) <= MAX_ROWS
             and type(league) is str and league in LEAGUES,
             "INVALID_AB_INPUT")
    hk_today = as_of.astimezone(frozen.HK).date()
    for row in rows:
        _require(type(row) is dict and row.get("status") in
                 ("FINISHED", "SCHEDULED"), "INVALID_AB_INPUT")
        _require(type(row.get("home")) is str and type(row.get("away")) is str
                 and row["home"] != row["away"], "INVALID_AB_INPUT")
        try:
            match_day = date.fromisoformat(row["date"])
        except (ValueError, TypeError, KeyError):
            raise ValueError("INVALID_AB_INPUT") from None
        if row["status"] == "FINISHED":
            score = row.get("score_ft")
            _require(match_day < hk_today and type(score) is list
                     and len(score) == 2 and all(type(n) is int
                     and 0 <= n <= 20 for n in score),
                     "RESULT_LEAKAGE_OR_INVALID_HISTORICAL_SCORE")
            # A fixture's historical finishing status is an input assertion,
            # not proof of an independent FT result.
        else:
            _require(row.get("score_ft") is None,
                     "POST_KICKOFF_OR_FUTURE_RESULT_LEAKAGE")
            _require(type(row.get("kickoff_utc")) is str,
                     "INVALID_AB_INPUT")
            if "outcome" in row or "settlement" in row:
                raise ValueError("POST_KICKOFF_OR_FUTURE_RESULT_LEAKAGE")
    return _canonical(rows)


def _validate_forecasts(items, *, league, as_of, candidate):
    _require(type(items) is list and len(items) <= MAX_FORECASTS,
             "INVALID_AB_FORECAST_LIST")
    checked = {}
    for row in items:
        _require(type(row) is dict and row.get("league") == league
                 and row.get("calibrated") is False
                 and row.get("verified_market_odds") is False
                 and row.get("production_recommendations") == "DISABLED",
                 "AB_FORECAST_UNSAFE")
        event_id = row.get("event_id")
        _require(type(event_id) is str and 0 < len(event_id) <= 260,
                 "AB_EVENT_ID_UNSAFE")
        ko = _instant(row.get("kickoff_utc"))
        forecast_time = _instant(row.get("prediction_utc"))
        _require(forecast_time == as_of and ko > as_of+timedelta(minutes=10),
                 "AB_TIME_WINDOW_UNSAFE")
        try:
            cutoff = date.fromisoformat(row["training_cutoff_local_day"])
        except (ValueError, TypeError, KeyError):
            raise ValueError("AB_TRAINING_CUTOFF_UNSAFE") from None
        _require(cutoff < as_of.astimezone(frozen.HK).date(),
                 "AB_TRAINING_CUTOFF_UNSAFE")
        p = [row.get(field) for field in ("p_home", "p_draw", "p_away")]
        _require(all(type(v) in (float, int) and math.isfinite(v)
                 and 0 <= v <= 1 for v in p) and abs(sum(p)-1) <= 3e-6,
                 "AB_PROBABILITY_INVALID")
        if candidate:
            _require(row.get("training_identity_method") ==
                     "league_scoped_curated_alias_or_exact_fold_v1",
                     "AB_CANDIDATE_IDENTITY_MISSING")
            verify_role(row.get("role_sample_quality"))
        key = (event_id, ko.isoformat())
        _require(key not in checked, "AB_DUPLICATE_FORECAST")
        checked[key] = row
    return checked


def compare(rows, *, league, as_of_utc, source_commit=None):
    """Outcome-blind, immutable pairwise comparison; absent rows remain visible."""
    now = _instant(as_of_utc)
    raw = _check_input(rows, league, now)
    if source_commit is not None:
        _require(type(source_commit) is str and
                 re.fullmatch("[0-9a-f]{40}", source_commit) is not None,
                 "INVALID_AB_SOURCE_COMMIT")
    # Disjoint copies ensure even a future mutating engine sees independent
    # identical serialized source values. Independently compare original digest.
    legacy_rows, new_rows = copy.deepcopy(rows), copy.deepcopy(rows)
    legacy = frozen.predict_league(legacy_rows, league, now)
    challenger = candidate_predict(new_rows, league, now)
    _require(_canonical(legacy_rows) == raw and _canonical(new_rows) == raw,
             "AB_INPUT_MUTATED_BY_MODEL")
    old = _validate_forecasts(legacy, league=league, as_of=now, candidate=False)
    new = _validate_forecasts(challenger, league=league, as_of=now, candidate=True)
    common = sorted(set(old) & set(new))
    legacy_only = sorted(set(old)-set(new))
    challenger_only = sorted(set(new)-set(old))
    observations = []
    for key in common:
        a, b = old[key], new[key]
        _require(team_id(league, a["home"]) == team_id(league, b["home"])
                 and team_id(league, a["away"]) == team_id(league, b["away"]),
                 "AB_FIXTURE_IDENTITY_MISMATCH")
        pa = [a["p_home"], a["p_draw"], a["p_away"]]
        pb = [b["p_home"], b["p_draw"], b["p_away"]]
        role = verify_role(b["role_sample_quality"])
        observations.append({
            "event_id": key[0], "kickoff_utc": key[1],
            "home": b["home"], "away": b["away"],
            "legacy_1x2": pa, "candidate_1x2": pb,
            "candidate_minus_legacy": [round(pb[i]-pa[i], 7) for i in range(3)],
            "absolute_home_delta": round(abs(pb[0]-pa[0]), 7),
            "legacy_top_index": max(range(3), key=lambda i: pa[i]),
            "candidate_top_index": max(range(3), key=lambda i: pb[i]),
            "candidate_role_sample_sufficient": role["role_sample_sufficient_for_research"],
            "training_cutoff_local_day": b["training_cutoff_local_day"],
            "comparison_has_result_outcome": False,
            "source_identity_authenticated": False,
        })
    counts = {
        "legacy": len(old), "candidate": len(new),
        "paired": len(common), "legacy_only": len(legacy_only),
        "candidate_only": len(challenger_only),
        "changed_top_direction": sum(
            p["legacy_top_index"] != p["candidate_top_index"] for p in observations),
        "mean_abs_home_probability_delta": (
            round(sum(p["absolute_home_delta"] for p in observations)
                  / len(observations), 7) if observations else None),
        "legacy_home_top": sum(
            max(range(3), key=lambda i: [x["p_home"],x["p_draw"],x["p_away"]][i])
            == 0 for x in old.values()),
        "candidate_home_top": sum(
            max(range(3), key=lambda i: [x["p_home"],x["p_draw"],x["p_away"]][i])
            == 0 for x in new.values()),
    }
    return {
        "schema": SCHEMA,
        "status": "RESEARCH_ONLY" if common else "HOLD",
        "league": league, "as_of_utc": now.isoformat(),
        "input_row_count": len(rows),
        "input_canonical_sha256": hashlib.sha256(raw).hexdigest(),
        "frozen_legacy_source_blob_sha1": frozen.SOURCE_BLOB,
        "candidate_source_commit": source_commit,
        "same_input_and_as_of_for_both_models": True,
        "source_capture_independently_authenticated": False,
        "original_fixture_identity_independently_authenticated": False,
        "future_result_input_used": False,
        "model_accuracy_improved_proven": False,
        "market_benchmark_beaten": False,
        "positive_ev_verified": False,
        "certified_case_count": 0,
        "production_recommendations": "DISABLED",
        "counts": counts,
        "home_favourite_cohort_risk": home_bias_cohort(list(new.values())),
        "paired": observations,
        "legacy_only": [{"event_id": k[0], "kickoff_utc": k[1]} for k in legacy_only],
        "candidate_only": [{"event_id": k[0], "kickoff_utc": k[1]} for k in challenger_only],
    }


def _pairs(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("DUPLICATE_AB_JSON_KEY")
        seen[key] = value
    return seen


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--source-commit", default=None)
    args = parser.parse_args(argv)
    try:
        if args.input.stat().st_size > 5_000_000:
            raise ValueError("OVERSIZED_AB_INPUT")
        payload = json.loads(args.input.read_text(encoding="utf-8"),
                             object_pairs_hook=_pairs,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 ValueError("INVALID_AB_JSON_CONSTANT")))
        _require(type(payload) is dict and payload.get("schema") == INPUT_SCHEMA
                 and set(payload) == {"schema", "league", "as_of_utc", "rows"},
                 "INVALID_AB_INPUT_SCHEMA")
        report = compare(payload["rows"], league=payload["league"],
                         as_of_utc=payload["as_of_utc"],
                         source_commit=args.source_commit)
    except (ValueError, KeyError, OSError, OverflowError, RecursionError):
        print(json.dumps({"status":"HOLD","reason":"AB_INPUT_OR_ENGINE_REJECTED",
                          "model_accuracy_improved_proven":False,
                          "certified_case_count":0,
                          "production_recommendations":"DISABLED"}))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
