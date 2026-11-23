"""Research-only league-level O/U2.5 and BTTS calibration diagnostics.

Inputs are historical date-only reconstructed forecasts, NOT signed as-of
predictions. Fixed 75% A-Poisson + 25% league training-period prior blend
was explored using past scores and must not be promoted without a fresh,
independently attested future holdout. No live odds, EV or betting outputs.
"""
import argparse
from datetime import date
import json
import math
from pathlib import Path
import re

SCHEMA = "football-king-league-goal-blend-shadow-v1"
MIX_WEIGHT = 0.25
MIN_TRAIN = 30
MIN_TEST = 20
MAX_ROWS = 50000
FIELDS = ("OVER25", "BTTS")


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("INVALID_MATCH_DATE")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("INVALID_MATCH_DATE") from exc


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 140:
        raise ValueError("INVALID_MATCH_IDENTITY")
    return value


def _goals(value):
    if type(value) is not int or not 0 <= value <= 25:
        raise ValueError("INVALID_FULLTIME_SCORE")
    return value


def _rates(home, away):
    if (type(home) not in (int, float) or type(away) not in (int, float)
            or not math.isfinite(home) or not math.isfinite(away)
            or not 0.1 <= home <= 5.5 or not 0.1 <= away <= 5.5):
        raise ValueError("INVALID_ORIGINAL_GOAL_RATES")
    return float(home), float(away)


def _rows(rows, *, training, league):
    if not isinstance(rows, list) or not 0 < len(rows) <= MAX_ROWS:
        raise ValueError("INVALID_SAMPLE_SIZE")
    seen = set()
    output = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("INVALID_SAMPLE")
        if row.get("league") != league:
            raise ValueError("LEAGUE_IDENTITY_MISMATCH")
        fixture_id = _name(row.get("fixture_id"))
        identity = (league, fixture_id)
        if identity in seen:
            raise ValueError("DUPLICATE_FIXTURE")
        seen.add(identity)
        match_day = _date(row.get("match_date"))
        home, away = _goals(row.get("home_goals")), _goals(row.get("away_goals"))
        if training:
            output.append((identity, match_day, home, away))
        else:
            lh, la = _rates(row.get("expected_home_goals"), row.get("expected_away_goals"))
            output.append((identity, match_day, home, away, lh, la))
    return output


def _poisson_over25(home, away):
    total = home + away
    return 1.0 - math.exp(-total) * (1.0 + total + total * total / 2.0)


def _btts(home, away):
    return (1.0 - math.exp(-home)) * (1.0 - math.exp(-away))


def _empty():
    return {"n": 0, "model_brier_sum": 0.0, "blend_brier_sum": 0.0,
            "prior_brier_sum": 0.0, "model_logloss_sum": 0.0,
            "blend_logloss_sum": 0.0, "prior_logloss_sum": 0.0,
            "model_probability_sum": 0.0, "blend_probability_sum": 0.0,
            "actual_count": 0}


def _update(scores, model, blend, prior, y):
    scores["n"] += 1
    for name, p in (("model", model), ("blend", blend), ("prior", prior)):
        scores[name + "_brier_sum"] += (p - y) ** 2
        clipped = min(1.0 - 1e-15, max(1e-15, p))
        scores[name + "_logloss_sum"] -= (
            y * math.log(clipped) + (1 - y) * math.log(1 - clipped)
        )
    scores["model_probability_sum"] += model
    scores["blend_probability_sum"] += blend
    scores["actual_count"] += y


def _final(scores):
    n = scores["n"]
    if not n:
        raise ValueError("EMPTY_SCORING_COHORT")
    return {
        "sample_count": n,
        "model_brier": round(scores["model_brier_sum"] / n, 8),
        "fixed_blend_brier": round(scores["blend_brier_sum"] / n, 8),
        "training_only_prior_brier": round(scores["prior_brier_sum"] / n, 8),
        "model_logloss": round(scores["model_logloss_sum"] / n, 8),
        "fixed_blend_logloss": round(scores["blend_logloss_sum"] / n, 8),
        "training_only_prior_logloss": round(scores["prior_logloss_sum"] / n, 8),
        "mean_model_probability": round(scores["model_probability_sum"] / n, 8),
        "mean_blend_probability": round(scores["blend_probability_sum"] / n, 8),
        "observed_rate": round(scores["actual_count"] / n, 8),
        "blend_brier_better_than_model": (
            scores["blend_brier_sum"] < scores["model_brier_sum"]),
        "blend_brier_better_than_training_prior": (
            scores["blend_brier_sum"] < scores["prior_brier_sum"]),
    }


def audit(folds, *, source_revision):
    """Historical research with strict training-before-test date separation."""
    if not isinstance(source_revision, str) or not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        raise ValueError("INVALID_PINNED_SOURCE_REVISION")
    if not isinstance(folds, list) or not 1 <= len(folds) <= 60:
        raise ValueError("INVALID_FOLDS")
    observed_folds = set()
    global_seen = set()
    aggregate = {m: _empty() for m in FIELDS}
    details = []
    for fold in folds:
        if not isinstance(fold, dict):
            raise ValueError("INVALID_FOLD")
        league = _name(fold.get("league"))
        label = _name(fold.get("test_season"))
        if (league, label) in observed_folds:
            raise ValueError("DUPLICATE_LEAGUE_SEASON")
        observed_folds.add((league, label))
        train = _rows(fold.get("training"), training=True, league=league)
        test = _rows(fold.get("heldout"), training=False, league=league)
        if len(train) < MIN_TRAIN or len(test) < MIN_TEST:
            raise ValueError("INSUFFICIENT_FOLD_SIZE")
        if max(x[1] for x in train) >= min(x[1] for x in test):
            raise ValueError("TRAINING_DATA_OVERLAPS_TEST")
        # No fixture may appear in more than one test cohort.
        ids = {x[0] for x in test}
        if ids & global_seen:
            raise ValueError("DUPLICATE_HELDOUT_ACROSS_FOLDS")
        global_seen.update(ids)
        if ids & {x[0] for x in train}:
            raise ValueError("TRAINING_TEST_IDENTITY_OVERLAP")
        # Jeffreys-smoothed marginal rates, based on TRAINING outcomes only.
        prior = {
            "OVER25": (sum((h+a) > 2 for _, _, h, a in train) + 0.5) / (len(train) + 1),
            "BTTS": (sum(h > 0 and a > 0 for _, _, h, a in train) + 0.5) / (len(train) + 1),
        }
        fold_scores = {m: _empty() for m in FIELDS}
        for _, _, gh, ga, lh, la in test:
            values = {"OVER25": (_poisson_over25(lh, la), int(gh + ga > 2)),
                      "BTTS": (_btts(lh, la), int(gh > 0 and ga > 0))}
            for market in FIELDS:
                p, y = values[market]
                blend = (1 - MIX_WEIGHT) * p + MIX_WEIGHT * prior[market]
                _update(fold_scores[market], p, blend, prior[market], y)
                _update(aggregate[market], p, blend, prior[market], y)
        details.append({
            "league": league, "test_season": label,
            "training_samples": len(train), "heldout_samples": len(test),
            "training_last_day": str(max(x[1] for x in train)),
            "heldout_first_day": str(min(x[1] for x in test)),
            "prior_over25_from_training_only": round(prior["OVER25"], 8),
            "prior_btts_from_training_only": round(prior["BTTS"], 8),
            "markets": {m: _final(fold_scores[m]) for m in FIELDS},
        })
    return {
        "schema": SCHEMA,
        "source_revision_self_reported": source_revision,
        "status": "HOLD",
        "research_only": True,
        "fixed_training_prior_blend_weight": MIX_WEIGHT,
        "exploratory_candidate_seen_historical_results": True,
        "fresh_independent_forward_holdout_required": True,
        "historical_reconstructed_rates_not_sealed_original_forecasts": True,
        "source_identity_and_timestamps_independently_authenticated": False,
        "crosschecked_results_independently_authenticated": False,
        "available_bookmaker_quotes": False,
        "model_profitability_or_positive_ev_verified": False,
        "original_model_weights_or_records_modified": False,
        "eligible_for_model_promotion": False,
        "production_recommendations": "DISABLED",
        "folds": details,
        "pooled": {m: _final(aggregate[m]) for m in FIELDS},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="JSON with source_revision and complete folds")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    doc = json.loads(Path(args.input).read_text(encoding="utf-8"))
    report = audit(doc["folds"], source_revision=doc["source_revision"])
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    with dest.open("x", encoding="utf-8") as out:
        json.dump(report, out, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")
    print("LEAGUE_OU25_SHADOW", report["status"], report["pooled"]["OVER25"]["sample_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
