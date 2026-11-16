"""Pre-registered two-fixture postmatch scorer of ORIGINAL 2026-11-17 five-model freeze.

Reads only the exact, already-committed forecast Git blob (SHA-1 computed as
Git blob bytes) and separately supplied, concordant 2-publisher FT records.
Does not fetch scores, change forecasts, trust user-claimed source ownership,
verify odds, place bets, certify time/independence or promote any model.

The two November 21 fixtures are NOT yet played at 2026-11-17. The preflight
can run now; actual postmatch scoring MUST fail closed until both finish.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path

from .postmatch_result_status_guard import reconcile_two_published_results
from .asian_handicap_research import TYPES, grade as handicap_grade
from .real_2026_three_market_oos import total_grade

SCHEMA = "football-king-five-model-pinned-postmatch-audit-v1"
RESULT_SCHEMA = "football-king-five-model-two-publisher-ft-input-v1"
FORECAST_SCHEMA = "football-king-local-five-model-prekickoff-run-freeze-v1"
PINNED_MANIFEST = "ops/research_manifests/dynamic_five_model_forward_local_20261117_pinned.json"
PINNED_BLOB_SHA1 = "087a3c3277dc07b0f7936b06dbcfac2f2df8d738"
PINNED_FIRST_COMMIT = "24e95a63b1f54cfa64b2ccd34705183aa6d2c816"
PINNED_FORECAST_RUN = "https://github.com/CHANCHUNWA1989/football-king-report/actions/runs/43912691040"
EXPECTED_IDS = ("openligadb:83237", "openligadb:83238")
MODEL_NAMES = ("original_a", "poisson", "dixon_coles",
               "bivariate_poisson", "dynamic_score_poisson")
GRADE_NAMES = tuple(name.lower() for name in TYPES)
MAX_INPUT_BYTES = 180_000


def _hold(reason, **extra):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED",
        "positive_ev_verified": False, "model_promoted": False,
        "certified_prospective_samples": 0,
        "two_publisher_source_independence_certified": False,
        "result_publisher_authenticity_verified": False,
        "forecast_independent_timestamp_attested": False,
        "bookmaker_quotes_or_ev_verified": False,
        "real_money_roi_verified": False,
        **extra,
    }


def _unique(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[name] = value
    return result


def _json(raw):
    if type(raw) is not bytes or len(raw) > MAX_INPUT_BYTES:
        raise ValueError("INVALID_OR_OVERSIZE_JSON_INPUT")
    return json.loads(
        raw.decode("utf-8"), object_pairs_hook=_unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")),
    )


def _git_blob_sha(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def _time(value):
    if type(value) is not str or len(value) > 65:
        raise ValueError("INVALID_TIMESTAMP")
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return moment.astimezone(timezone.utc)


def _probabilities(values):
    return (type(values) is list and len(values) == 3
            and all(type(x) in (float, int) and
                    math.isfinite(x) and 0 <= x <= 1 for x in values)
            and abs(sum(values) - 1) <= 0.00001)


def _grades(values):
    return (type(values) is dict and set(values) == set(GRADE_NAMES)
            and all(type(x) in (float, int) and
                    math.isfinite(x) and 0 <= x <= 1 for x in values.values())
            and abs(sum(values.values()) - 1) <= 0.00001)


def _valid_sha(value):
    return (type(value) is str and len(value) == 64 and
            all(c in "0123456789abcdef" for c in value))


def freeze_preflight(manifest_bytes, *, expected_blob_sha=PINNED_BLOB_SHA1):
    """Require byte-for-byte original Git blob; caller cannot edit forecast."""
    if (_git_blob_sha(manifest_bytes) != expected_blob_sha
            or expected_blob_sha != PINNED_BLOB_SHA1):
        return _hold("PINNED_FORECAST_GIT_BLOB_CHANGED")
    try:
        m = _json(manifest_bytes)
        if (type(m) is not dict
                or m.get("schema") != FORECAST_SCHEMA
                or m.get("evidence_status") != "LOCAL_RESEARCH_UNATTESTED_HOLD"
                or m.get("original_github_run_url") != PINNED_FORECAST_RUN
                or m.get("original_run_head_sha") != "f48945a8934c6de0d224defd25ca2900f8b8008a"
                or m.get("one_response_provider") != "OpenLigaDB"
                or not _valid_sha(m.get("one_response_source_sha256_unattested"))
                or m.get("original_finished_training_matches") != 81
                or m.get("production_recommendations") != "DISABLED"
                or m.get("positive_ev_verified") is not False
                or m.get("certified_prospective_samples") != 0
                or m.get("model_promoted") is not False
                or m.get("available_genuine_offered_bookmaker_odds") is not False):
            raise ValueError("UNTRUSTED_OR_NOT_ORIGINAL_FORECAST")
        f = m.get("fixtures")
        if type(f) is not list or len(f) != 2 or tuple(
                row.get("event_id") for row in f if type(row) is dict) != EXPECTED_IDS:
            raise ValueError("CHANGED_OR_INCOMPLETE_TWO_FIXTURES")
        source_seen = _time(m["original_source_http_completed_utc"])
        original_run_finished = _time(m["actual_original_run_completion_utc"])
        if not source_seen <= original_run_finished:
            raise ValueError("INVALID_SOURCE_OR_RUN_ORDER")
        for row in f:
            kickoff = _time(row["kickoff_utc"])
            first_seen = _time(row["local_cutoff_source_first_seen_utc"])
            last_fit = _time(row["local_fifth_finished_utc"])
            if not (source_seen == first_seen <= last_fit <= original_run_finished
                    < kickoff - timedelta(minutes=10)):
                raise ValueError("FORECAST_NOT_BEFORE_KICKOFF")
            if (row.get("historical_matches_from_same_response") != 81
                    or row.get("same_a_and_challenger_training_event_ids") is not True
                    or row.get("bookmaker_lines_or_prices_verified") is not False
                    or row.get("positive_ev_verified") is not False
                    or not _valid_sha(row.get("local_previous_three_sha256_unattested"))):
                raise ValueError("MISSING_SOURCE_OR_HOLD_FLAGS")
            if (type(row.get("home")) is not str or not row["home"]
                    or type(row.get("away")) is not str or not row["away"]
                    or row["home"] == row["away"]):
                raise ValueError("INVALID_FROZEN_FIXTURE_TEAMS")
            vectors = row.get("model_1x2_home_draw_away")
            if (type(vectors) is not dict or set(vectors) != set(MODEL_NAMES)
                    or not all(_probabilities(v) for v in vectors.values())):
                raise ValueError("INVALID_FROZEN_FIVE_MODEL_PROBABILITIES")
            for model in ("bivariate", "dynamic"):
                if not _grades(row.get(model + "_over_2_75_settlement")):
                    raise ValueError("INVALID_FROZEN_OVER_2_75")
                if not _grades(row.get(model + "_home_ah_minus_0_25_settlement")):
                    raise ValueError("INVALID_FROZEN_AH_MINUS_0_25")
            if (abs(row["bivariate_home_ah_minus_0_25_settlement"]["full_win"]
                     - vectors["bivariate_poisson"][0]) > 1e-6
                    or abs(row["dynamic_home_ah_minus_0_25_settlement"]["full_win"]
                           - vectors["dynamic_score_poisson"][0]) > 1e-6):
                raise ValueError("FROZEN_1X2_AND_AH_SCORE_CONFLICT")
        return _hold(
            "PINNED_TWO_FIXTURES_PREGAME_BYTE_FREEZE_PASSED",
            preflight_passed=True, locked_git_blob_sha1=PINNED_BLOB_SHA1,
            first_seal_commit=PINNED_FIRST_COMMIT,
            original_run_url=PINNED_FORECAST_RUN,
            fixture_ids=list(EXPECTED_IDS),
            kickoff_utc=[row["kickoff_utc"] for row in f],
            scored_matches=0,
            official_results_not_yet_authenticated=True,
            note="Git byte integrity and recorded local pre-kickoff order, NOT external TSA or source authentication",
        )
    except (KeyError, ValueError, TypeError, AttributeError, UnicodeError):
        return _hold("PINNED_FORECAST_INTERNAL_VALIDATION_FAILED")


def _score_vector(probs, index):
    brier = sum((value - int(i == index)) ** 2 for i, value in enumerate(probs))
    logloss = -math.log(max(probs[index], 1e-15))
    top = max(range(3), key=lambda i: probs[i])
    return (brier, logloss, int(top == index))


def _score_grade(dist, observed):
    brier = sum((value - int(key == observed)) ** 2
                for key, value in dist.items())
    logloss = -math.log(max(dist[observed], 1e-15))
    return (brier, logloss)


def score_pinned(manifest_bytes, result_bytes, *, now=None):
    """Only score the exact precommitted TWO fixtures, with two FT hosts each.

    Matching user-supplied HTTPS publisher metadata is NOT authenticated
    provenance. Always HOLD and never assert market-grade ROI or true EV.
    """
    preflight = freeze_preflight(manifest_bytes)
    if preflight.get("preflight_passed") is not True:
        return preflight
    try:
        document = _json(result_bytes)
        if (type(document) is not dict
                or set(document) != {"schema", "observations"}
                or document["schema"] != RESULT_SCHEMA
                or type(document["observations"]) is not list
                or len(document["observations"]) != 2):
            return _hold("REQUIRES_BOTH_PINNED_FT_FIXTURES")
        instant = (datetime.now(timezone.utc) if now is None else now)
        if type(instant) is not datetime or instant.tzinfo is None:
            raise ValueError("INVALID_SCORE_CLOCK")
        instant = instant.astimezone(timezone.utc)
        freeze = _json(manifest_bytes)
        by_id = {row["event_id"]: row for row in freeze["fixtures"]}
        seen = set()
        scores = {}
        for item in document["observations"]:
            if (type(item) is not dict
                    or set(item) != {"event_id", "publishers"}
                    or type(item["event_id"]) is not str
                    or item["event_id"] not in by_id
                    or item["event_id"] in seen
                    or type(item["publishers"]) is not list
                    or len(item["publishers"]) != 2):
                return _hold("DUPLICATE_UNKNOWN_OR_MISSING_FIXTURE")
            event_id = item["event_id"]
            seen.add(event_id)
            fixture = by_id[event_id]
            kickoff = _time(fixture["kickoff_utc"])
            if instant < kickoff + timedelta(minutes=90):
                return _hold("MATCH_NOT_MATURE_FOR_FULL_TIME_REVIEW")
            publisher_rows = []
            for row in item["publishers"]:
                if (type(row) is not dict
                        or set(row) != {
                            "publisher", "source_url", "league", "home",
                            "away", "kickoff_utc", "home_goals", "away_goals",
                            "match_status", "observed_utc",
                        }
                        or row["league"] != "bundesliga"
                        or row["home"] != fixture["home"]
                        or row["away"] != fixture["away"]
                        or _time(row["kickoff_utc"]) != kickoff):
                    return _hold("PROVIDER_FIXTURE_IDENTITY_MISMATCH")
                observed = _time(row["observed_utc"])
                if not kickoff + timedelta(minutes=90) <= observed <= instant:
                    return _hold("INVALID_PUBLISHER_OBSERVATION_TIME")
                publisher_rows.append({
                    key: val for key, val in row.items() if key != "observed_utc"
                })
            agreement = reconcile_two_published_results(publisher_rows)
            if (agreement.get("status") != "RESEARCH_ONLY"
                    or agreement.get("score_agreement") is not True
                    or agreement.get("upstream_independence_certified") is not False):
                return _hold("TWO_PUBLISHER_FT_NOT_RECONCILED",
                             source_reason=agreement.get("reason"))
            scores[event_id] = (
                agreement["home_goals"], agreement["away_goals"])
        if set(scores) != set(EXPECTED_IDS):
            return _hold("INCOMPLETE_FIXED_PAIRED_COHORT")
        observed_1x2 = []
        metrics = {model: [] for model in MODEL_NAMES}
        market_metrics = {
            model: {"OVER_2.75": [], "HOME_AH_-0.25": []}
            for model in ("bivariate", "dynamic")
        }
        for fixture in freeze["fixtures"]:
            h, a = scores[fixture["event_id"]]
            outcome = 0 if h > a else (1 if h == a else 2)
            observed_1x2.append({"fixture_id": fixture["event_id"],
                                 "home_goals": h, "away_goals": a,
                                 "result": ("HOME", "DRAW", "AWAY")[outcome]})
            for model in MODEL_NAMES:
                metrics[model].append(_score_vector(
                    fixture["model_1x2_home_draw_away"][model], outcome))
            total_outcome = total_grade(h, a, "OVER", 2.75).lower()
            ah_outcome = handicap_grade(h, a, "HOME", -0.25).lower()
            for model in market_metrics:
                for label, actual, distkey in (
                    ("OVER_2.75", total_outcome, model + "_over_2_75_settlement"),
                    ("HOME_AH_-0.25", ah_outcome,
                     model + "_home_ah_minus_0_25_settlement"),
                ):
                    market_metrics[model][label].append(
                        _score_grade(fixture[distkey], actual))
        summary = {
            model: {
                "n": len(values), "mean_brier": round(sum(x[0] for x in values) / 2, 6),
                "mean_logloss": round(sum(x[1] for x in values) / 2, 6),
                "direction_hits": sum(x[2] for x in values),
            } for model, values in metrics.items()
        }
        market_summary = {
            model: {
                market: {
                    "n": 2, "mean_five_grade_brier": round(
                        sum(x[0] for x in records) / 2, 6),
                    "mean_five_grade_logloss": round(
                        sum(x[1] for x in records) / 2, 6),
                } for market, records in markets.items()
            } for model, markets in market_metrics.items()
        }
        return _hold(
            "TWO_SOURCE_METADATA_CONCORDANT_RESEARCH_SCORE_NOT_CERTIFIED",
            preflight_passed=True, fixed_match_count=2, scored_matches=2,
            original_forecast_blob_sha1=PINNED_BLOB_SHA1,
            original_freeze_commit=PINNED_FIRST_COMMIT,
            full_time_observations=observed_1x2,
            original_five_model_1x2_scores=summary,
            pinned_two_model_market_grade_scores=market_summary,
            result_source_metadata_agreement=True,
            source_independence_authenticated=False,
            statistical_superiority_proven=False,
            confidence_intervals_valid_for_two_matches=False,
            commentary="Two-source URL/FT agreement is metadata only; score-only small n=2, no money/EV",
        )
    except (ValueError, KeyError, TypeError, AttributeError,
            UnicodeError, OverflowError):
        return _hold("INVALID_RESULT_EVIDENCE_OR_TIMESTAMPS")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=PINNED_MANIFEST)
    parser.add_argument("--results", help="After BOTH fixtures FT, provide two publisher records each")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.results and Path(args.results).resolve() == Path(args.output).resolve():
        raise ValueError("OUTPUT_ALIASES_RESULT_EVIDENCE")
    manifest_path = Path(args.manifest)
    if manifest_path.is_symlink():
        raise ValueError("SYMLINK_MANIFEST_REFUSED")
    manifest = manifest_path.read_bytes()
    if args.results:
        results_path = Path(args.results)
        if results_path.is_symlink():
            raise ValueError("SYMLINK_RESULT_REFUSED")
        report = score_pinned(manifest, results_path.read_bytes())
    else:
        report = freeze_preflight(manifest)
    dest = Path(args.output)
    if dest.exists() or dest.is_symlink():
        raise ValueError("NO_OVERWRITE_OR_SYMLINK_OUTPUT")
    encoded = (json.dumps(report, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False) + "\n").encode()
    fd = os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    print("FIVE_MODEL_PINNED_AUDIT", encoded.decode().strip())
    return 0 if report.get("preflight_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
