"""Historical sealed-ledger stress diagnostics; NEVER an authenticated backtest.

Read old frozen A/B/C and historical no-vig market consensus without mutation.
Score only same-fixture rows. The records lack independent final-result proof,
verified forecast attestation, historical executable prices, and verified
forecast/market same-as-of equivalence. Consequently ALL output is descriptive
and cannot train/promote a model, prove EV or authorize betting.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import math

from ops.calibration_evidence_readiness import _prob, _utc, audit, read_archive

SCHEMA = "football-king-historical-research-stress-v1"
MARKET_FRESHNESS_HOURS = 4.0
MODEL_KEYS = {"A": "p", "B": "ab", "C": "c", "market": "m"}


def _score(rows, model):
    if not rows:
        return None
    briers = []
    logs = []
    correct = 0
    sum_draws = 0.0
    actual_draws = 0
    for row in rows:
        p, y = row[model], row["y"]
        briers.append(math.fsum((v - (1 if idx == y else 0)) ** 2
                                for idx, v in enumerate(p)))
        logs.append(-math.log(p[y]))
        correct += int(p.index(max(p)) == y)
        sum_draws += p[1]
        actual_draws += int(y == 1)
    n = len(rows)
    return {
        "n": n,
        "brier": round(math.fsum(briers) / n, 7),
        "log_loss": round(math.fsum(logs) / n, 7),
        "argmax_correct": correct,
        "argmax_accuracy": round(correct / n, 7),
        "predicted_draw_rate": round(sum_draws / n, 7),
        "observed_draw_rate": round(actual_draws / n, 7),
    }


def _pair(rows, left, right):
    shared = [x for x in rows if left in x and right in x]
    a = _score(shared, left)
    b = _score(shared, right)
    if a is None or b is None:
        return {
            "n": 0,
            "left": left,
            "right": right,
            "left_scores": None,
            "right_scores": None,
            "brier_left_minus_right": None,
            "log_loss_left_minus_right": None,
        }
    return {
        "n": len(shared),
        "left": left,
        "right": right,
        "left_scores": a,
        "right_scores": b,
        "brier_left_minus_right": round(a["brier"] - b["brier"], 7),
        "log_loss_left_minus_right": round(
            a["log_loss"] - b["log_loss"], 7),
    }


def stress(payload):
    readiness = audit(payload)
    result = {
        "schema": SCHEMA,
        "archive_checked_utc": readiness["source_checked_utc"],
        "status": "HOLD",
        "reason": "UNVERIFIED_RESULTS_AND_FORECAST_PROVENANCE",
        "archive_rows": readiness["archive_rows"],
        "unique_scored_research_rows": 0,
        "skipped_rows": 0,
        "duplicate_case_keys": readiness["duplicate_case_keys"],
        "time_invalid_rows": 0,
        "market_snapshot_older_than_4h_before_kickoff": 0,
        "market_age_hours_median": None,
        "forecast_to_market_gap_hours_median": None,
        "scores": {},
        "paired": {},
        "by_league": {},
        "by_month": {},
        "favorite_A_gte_70pct": {},
        "calibration_gate": {
            "certified_rows": readiness["certified_forward_rows"],
            "minimum_certified_rows": 300,
            "calibration_candidate_generated": False,
            "eligible_for_model_training": False,
        },
        "performance_scores_are_exploratory": True,
        "actual_real_odd_quotes_verified": False,
        "forecast_market_same_cutoff_verified": False,
        "external_provenance_verified": False,
        "verified_oos_improvement": False,
        "verified_positive_ev": False,
        "production_recommendations": "DISABLED",
    }
    if not isinstance(payload, dict) or type(payload.get("samples")) is not list:
        result["reason"] = "INVALID_ARCHIVE_FORMAT"
        return result
    seen = set()
    usable = []
    market_ages = []
    gaps = []
    for raw in payload["samples"]:
        if type(raw) is not dict:
            result["skipped_rows"] += 1
            continue
        key = raw.get("key")
        if type(key) is not str or not key or len(key) > 512:
            result["skipped_rows"] += 1
            continue
        if key in seen:
            result["skipped_rows"] += 1
            continue
        seen.add(key)
        y, league = raw.get("y"), raw.get("league")
        if (type(y) is not int or y not in (0, 1, 2)
                or type(league) is not str or not league or len(league) > 80
                or not _prob(raw.get("p")) or not _prob(raw.get("m"))
                or raw.get("production_recommendations") != "DISABLED"):
            result["skipped_rows"] += 1
            continue
        kickoff = _utc(raw.get("kickoff_utc"))
        forecast = _utc(raw.get("forecast_utc"))
        market = _utc(raw.get("market_utc"))
        if not all((kickoff, forecast, market)) or not (
                forecast < kickoff and market < kickoff):
            result["time_invalid_rows"] += 1
            result["skipped_rows"] += 1
            continue
        row = {
            "key": key, "league": league, "y": y,
            "kickoff": kickoff,
            "A": list(raw["p"]), "market": list(raw["m"]),
        }
        for model, source in (("B", "ab"), ("C", "c")):
            if source in raw:
                if not _prob(raw[source]):
                    result["skipped_rows"] += 1
                    # Do not score a partially malformed event.
                    row = None
                    break
                row[model] = list(raw[source])
        if row is None:
            continue
        usable.append(row)
        age = (kickoff - market).total_seconds() / 3600.0
        gap = (forecast - market).total_seconds() / 3600.0
        market_ages.append(age)
        gaps.append(gap)
        if age > MARKET_FRESHNESS_HOURS:
            result["market_snapshot_older_than_4h_before_kickoff"] += 1
    result["unique_scored_research_rows"] = len(usable)
    if not usable:
        result["reason"] = "NO_TIME_VALID_RESEARCH_ROWS"
        return result
    market_ages.sort()
    gaps.sort()
    size = len(usable)
    result["market_age_hours_median"] = round(
        (market_ages[(size - 1) // 2] + market_ages[size // 2]) / 2, 3)
    result["forecast_to_market_gap_hours_median"] = round(
        (gaps[(size - 1) // 2] + gaps[size // 2]) / 2, 3)
    result["scores"] = {
        model: _score([r for r in usable if model in r], model)
        for model in MODEL_KEYS
    }
    result["paired"] = {
        "A_vs_market": _pair(usable, "A", "market"),
        "B_vs_A": _pair(usable, "B", "A"),
        "B_vs_market": _pair(usable, "B", "market"),
        "C_vs_A": _pair(usable, "C", "A"),
        "C_vs_market": _pair(usable, "C", "market"),
    }
    leagues = defaultdict(list)
    months = defaultdict(list)
    for row in usable:
        leagues[row["league"]].append(row)
        months[row["kickoff"].strftime("%Y-%m")].append(row)
    result["by_league"] = {
        name: _pair(group, "A", "market")
        for name, group in sorted(leagues.items())
    }
    result["by_month"] = {
        name: _pair(group, "A", "market")
        for name, group in sorted(months.items())
    }
    favorites = [
        row for row in usable if max(row["A"]) >= 0.7
    ]
    result["favorite_A_gte_70pct"] = {
        "n": len(favorites),
        "A_scores": _score(favorites, "A"),
        "market_scores_on_same_matches": _score(favorites, "market"),
        "avg_A_confidence": round(
            math.fsum(max(r["A"]) for r in favorites) / len(favorites), 7)
        if favorites else None,
    }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Replay archived research pairs; NO predictive or EV certificate")
    parser.add_argument("--input", default="evidence/settled.json")
    args = parser.parse_args(argv)
    try:
        result = stress(read_archive(args.input))
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        result = stress(None)
        result["read_error_class"] = type(exc).__name__
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
