"""Historical date-cutoff replay of the EXACT published Shadow Poisson model.

This is a RETROSPECTIVE, source-revisable, date-only model diagnostic. There
are no genuine stored as-of-day fixtures/quotes here; the synthetic clock is
strictly an adapter to predict_league, NEVER evidence of forecast timestamp.
This must NEVER authorize bets, quote profits, certify forward calibration,
or substitute for immutable pre-match evaluation.
"""
import argparse
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from zoneinfo import ZoneInfo

from shadow_forecast import predict_league

HK = ZoneInfo("Asia/Hong_Kong")
SCHEMA = "football-king-historical-date-replay-v1"
LEAGUE_FILES = {
    "epl": "en.1.json",
    "championship": "en.2.json",
    "bundesliga": "de.1.json",
    "laliga": "es.1.json",
    "seriea": "it.1.json",
    "ligue1": "fr.1.json",
}
DEVELOPMENT = "2024-25"
HOLDOUT = "2025-26"
SOURCE = "https://raw.githubusercontent.com/openfootball/football.json/master/"
MAX_BYTES = 500_000
MAX_MATCHES = 650
STATIC_BASELINE = (0.45, 0.27, 0.28)
PRIOR_WEIGHT = 20
DRAW_BOOST = 0.03
CONFIDENCE_CUTOFFS = (0.50, 0.55, 0.60, 0.65)
PRIOR_BLEND_GRID = (0.0, 0.10, 0.20, 0.30, 0.40)  # Chosen only using development season
MIN_HOLDOUT = 300
MIN_WEEKS = 12


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, url):
        raise ValueError("UNEXPECTED_HISTORICAL_SOURCE_REDIRECT")


def get_archive(season, league):
    if season not in (DEVELOPMENT, HOLDOUT) or league not in LEAGUE_FILES:
        raise ValueError("UNAPPROVED_ARCHIVE")
    path = season + "/" + LEAGUE_FILES[league]
    req = Request(SOURCE + path, headers={
        "Accept": "application/json", "User-Agent": "FootballKingResearchReplay/1.0"})
    with build_opener(NoRedirect()).open(req, timeout=15) as response:
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError("HISTORICAL_ARCHIVE_TOO_LARGE")
    return json.loads(payload.decode("utf-8")), hashlib.sha256(payload).hexdigest()


def parse_archive(doc):
    """A date-only, finished-result dataset. Never infer real kickoff time."""
    if not isinstance(doc, dict) or not isinstance(doc.get("matches"), list):
        raise ValueError("INVALID_HISTORY_SCHEMA")
    if len(doc["matches"]) > MAX_MATCHES:
        raise ValueError("HISTORICAL_MATCH_LIMIT")
    parsed, seen, rejected = [], set(), Counter()
    for row in doc["matches"]:
        if not isinstance(row, dict):
            rejected["malformed"] += 1
            continue
        h, a = row.get("team1"), row.get("team2")
        if not all(isinstance(x, str) and 0 < len(x) < 110 for x in (h, a)) or h == a:
            rejected["team"] += 1
            continue
        result = row.get("score")
        score = result.get("ft") if isinstance(result, dict) else result
        if (not isinstance(score, list) or len(score) != 2
                or not all(type(x) is int and 0 <= x <= 20 for x in score)):
            rejected["no_finished_result"] += 1
            continue
        try:
            day = date.fromisoformat(row["date"])
        except (KeyError, TypeError, ValueError):
            rejected["invalid_date"] += 1
            continue
        if not 2023 <= day.year <= 2026:
            rejected["out_of_period"] += 1
            continue
        key = (day.isoformat(), h, a)
        if key in seen:
            rejected["duplicate"] += 1
            continue
        seen.add(key)
        parsed.append({"date": day, "home": h, "away": a,
                       "score_ft": score, "status": "FINISHED"})
    parsed.sort(key=lambda x: (x["date"], x["home"], x["away"]))
    if len(parsed) < 100:
        raise ValueError("INSUFFICIENT_FINISHED_HISTORY_ARCHIVE")
    return parsed, dict(rejected)


def draw_adjust(p):
    """Predeclared Shadow challenger: move 3pp from wins toward draws."""
    q = [float(x) for x in p]
    factor = max(0.0, (1.0 - q[1] - DRAW_BOOST) / (1.0 - q[1]))
    return [q[0] * factor, 1.0 - (q[0] + q[2]) * factor, q[2] * factor]


def frequency_baseline(history):
    outcomes = Counter(
        0 if x["score_ft"][0] > x["score_ft"][1]
        else 1 if x["score_ft"][0] == x["score_ft"][1] else 2
        for x in history
    )
    n = len(history)
    return [(outcomes[i] + PRIOR_WEIGHT * STATIC_BASELINE[i]) /
            (n + PRIOR_WEIGHT) for i in range(3)]


def replay(matches, league, season):
    """Evaluate only same-season earlier calendar days, not future matches.

    The invented 23:00 local hour is a scoring-adapter field ONLY; never
    published as a fixture kickoff, market snapshot or authentic prediction.
    """
    if not ((league in LEAGUE_FILES and season in (DEVELOPMENT, HOLDOUT))
            or (league == "japan_j1" and season == "2025")):
        raise ValueError("UNSUPPORTED_REPLAY_SCOPE")
    grouped = defaultdict(list)
    for x in matches:
        grouped[x["date"]].append(x)
    earlier, scored, exclusions = [], [], Counter()
    for day in sorted(grouped):
        today = grouped[day]
        date_cutoff = datetime.combine(day, time.min, tzinfo=HK).astimezone(timezone.utc)
        # The model's actual API requires a timezone-aware upcoming timestamp.
        # This synthetic 23:00 local time is ONLY a historical adapter.
        adapter_time = datetime.combine(day, time(23, 0), tzinfo=HK).astimezone(timezone.utc)
        future = []
        targets = {}
        for n, match in enumerate(today):
            case_id = league + "|" + season + "|" + day.isoformat() + "|" + str(n)
            targets[case_id] = match
            future.append({
                "date": day.isoformat(),
                "home": match["home"], "away": match["away"],
                "status": "SCHEDULED", "score_ft": None,
                "kickoff_utc": adapter_time.isoformat(),
                "event_id": case_id,
            })
        training = [{"date": m["date"].isoformat(), "home": m["home"],
                     "away": m["away"], "score_ft": m["score_ft"],
                     "status": "FINISHED"} for m in earlier]
        prior = frequency_baseline(earlier)
        if len(earlier) >= 30:
            preds = predict_league(training + future, league, date_cutoff)
            for pred in preds:
                actual = targets.get(pred["event_id"])
                if actual is None or pred["training_games"] != len(earlier):
                    raise ValueError("INCORRECT_REPLAY_DATE_CUTOFF")
                p = [pred["p_home"], pred["p_draw"], pred["p_away"]]
                y = (0 if actual["score_ft"][0] > actual["score_ft"][1]
                     else 1 if actual["score_ft"][0] == actual["score_ft"][1] else 2)
                scored.append({
                    "league": league, "season": season, "date": day.isoformat(),
                    "y": y, "original": p, "draw_adjust": draw_adjust(p),
                    "league_frequency": prior[:], "uniform": [1/3]*3,
                    "training_games": len(earlier),
                    # Used only for retrospective settlement diagnostics,
                    # NEVER as a training feature or input to this match model.
                    "score_ft": actual["score_ft"][:],
                    "expected_home_goals": pred["expected_home_goals"],
                    "expected_away_goals": pred["expected_away_goals"],
                })
            exclusions["not_predicted_with_prior_history"] += len(future) - len(preds)
        else:
            exclusions["initial_less_than_30_games"] += len(future)
        earlier.extend(today)
    return scored, dict(exclusions)


def blend_with_prior(p, baseline, weight):
    """Cautious 1X2 shrinkage toward a past-only league result frequency."""
    if (type(weight) not in (int, float) or not math.isfinite(weight)
            or not 0 <= weight <= .5):
        raise ValueError("BAD_PRIOR_BLEND_WEIGHT")
    if (not isinstance(p, list) or not isinstance(baseline, list)
            or len(p) != 3 or len(baseline) != 3):
        raise ValueError("BAD_BLEND_INPUT")
    if not all(type(v) in (int, float) and math.isfinite(v) and
               0 <= v <= 1 for v in p + baseline):
        raise ValueError("BAD_BLEND_PROBABILITIES")
    if abs(sum(p) - 1) > .003 or abs(sum(baseline) - 1) > .003:
        raise ValueError("BAD_BLEND_SUM")
    return [(1 - weight) * p[i] + weight * baseline[i] for i in range(3)]


def choose_prior_blend(development_rows):
    """No 2025/26 targets or outcomes may influence the mixing coefficient."""
    if not development_rows:
        return {"weight": 0.0, "scores": [], "basis": "NO_DEVELOPMENT_ROWS"}
    scores = []
    for weight in PRIOR_BLEND_GRID:
        total = 0.0
        for row in development_rows:
            probs = blend_with_prior(row["original"], row["league_frequency"], weight)
            total -= math.log(max(probs[row["y"]], 1e-12))
        scores.append({"weight": weight,
                       "development_mean_log_loss": round(total / len(development_rows), 6)})
    winner = min(scores, key=lambda r: (r["development_mean_log_loss"], r["weight"]))
    return {"weight": winner["weight"], "scores": scores,
            "basis": "2024_25_DEVELOPMENT_LOG_LOSS_ONLY"}


def _outcome_metric(p, y):
    if not (len(p) == 3 and all(math.isfinite(v) and 0 < v <= 1 for v in p)
            and abs(sum(p) - 1) < .003):
        raise ValueError("INVALID_REPLAY_PROBABILITIES")
    top = max(range(3), key=lambda i: p[i])
    return (int(top == y), -math.log(max(p[y], 1e-12)),
            sum((p[k] - int(y == k))**2 for k in range(3)))


def wilson(hits, n):
    if not n:
        return None
    z = 1.96
    p = hits / n
    center = (p + z*z/(2*n))/(1 + z*z/n)
    radius = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/(1 + z*z/n)
    return [round(center - radius, 4), round(center + radius, 4)]


def summary(rows, key):
    n = len(rows)
    if not n:
        return None
    values = [_outcome_metric(r[key], r["y"]) for r in rows]
    hits = sum(x[0] for x in values)
    return {
        "n": n, "hits": hits, "hit_rate": round(hits/n, 4),
        "hit_rate_wilson95": wilson(hits, n),
        # Multiclass top-choice calibration is different from 1X2 accuracy:
        # confidence must track realized hit-rate within comparable bins.
        "mean_top_probability": round(sum(max(r[key]) for r in rows)/n, 5),
        "top_choice_calibration_gap": round(
            sum(max(r[key]) for r in rows)/n - hits/n, 5),
        "mean_log_loss": round(sum(x[1] for x in values)/n, 5),
        "mean_three_class_brier": round(sum(x[2] for x in values)/n, 5),
        "observed_draw_fraction": round(sum(r["y"] == 1 for r in rows)/n, 4),
        "forecast_draw_fraction": round(sum(r[key][1] for r in rows)/n, 4),
        "draw_calibration_gap": round(
            sum(r[key][1] - (r["y"] == 1) for r in rows)/n, 4),
        "draw_recall": (
            round(sum(max(range(3), key=lambda i: r[key][i]) == 1
                      for r in rows if r["y"] == 1)
                  / sum(r["y"] == 1 for r in rows), 4)
            if any(r["y"] == 1 for r in rows) else None),
    }


def block_ci(rows, challenger, *, seed=20261010, repetitions=1000):
    """Paired weekly bootstrap of hit-rate and log-loss gains, challenger vs v4.1."""
    weeks = defaultdict(lambda: [0, 0, 0.0])
    for r in rows:
        d = date.fromisoformat(r["date"])
        week = d.isocalendar()
        old = _outcome_metric(r["original"], r["y"])
        new = _outcome_metric(r[challenger], r["y"])
        aggregate = weeks[(week.year, week.week)]
        aggregate[0] += 1
        aggregate[1] += new[0] - old[0]
        aggregate[2] += old[1] - new[1]
    if len(weeks) < MIN_WEEKS:
        return None
    # Compute point-in-time paired outcomes once per match. Bootstrap fixed
    # weekly sufficient statistics, not millions of repeated log-loss calls.
    groups = list(weeks.values())
    rng = random.Random(seed)
    accuracy, loggain = [], []
    for _ in range(repetitions):
        sampled = [groups[rng.randrange(len(groups))] for _ in groups]
        n = sum(x[0] for x in sampled)
        if not n:
            continue
        accuracy.append(sum(x[1] for x in sampled) / n)
        loggain.append(sum(x[2] for x in sampled) / n)
    if not accuracy:
        return None
    accuracy.sort()
    loggain.sort()
    return {
        "hit_rate_gain_95pct_ci": [round(accuracy[25], 5), round(accuracy[974], 5)],
        "log_loss_gain_95pct_ci": [round(loggain[25], 5), round(loggain[974], 5)],
        "independent_calendar_weeks": len(weeks),
    }


def evaluate_cohort(rows):
    res = {
        "n": len(rows),
        "original": summary(rows, "original"),
        "draw_adjust": summary(rows, "draw_adjust"),
        "league_frequency": summary(rows, "league_frequency"),
        "uniform": summary(rows, "uniform"),
    }
    res["coverage_at_confidence_cutoffs"] = []
    for threshold in CONFIDENCE_CUTOFFS:
        selected = [r for r in rows if max(r["original"]) >= threshold]
        baseline = summary(selected, "original")
        res["coverage_at_confidence_cutoffs"].append({
            "minimum_model_probability": threshold,
            "selected": len(selected),
            "coverage": round(len(selected)/len(rows), 4) if rows else 0,
            "hit_rate": baseline["hit_rate"] if baseline else None,
            "hit_rate_wilson95": baseline["hit_rate_wilson95"] if baseline else None,
        })
    res["paired_week_bootstrap_draw_adjust_vs_original"] = block_ci(rows, "draw_adjust") if rows else None
    res["paired_week_bootstrap_frequency_vs_original"] = block_ci(rows, "league_frequency") if rows else None
    return res


def build(docs):
    """docs[(season,league)] = (parsed JSON, SHA256 upstream content)."""
    output = {
        "schema": SCHEMA, "evaluation_type": "RETROSPECTIVE_DATE_ONLY_REPLAY",
        "live_point_in_time_forecasts_verified": False,
        "authentic_kickoff_times_used": False,
        "replay_adapter_time_is_not_a_real_kickoff": True,
        "market_baseline_available": False,
        "betting_roi_estimable": False,
        "model_calibration_certified": False,
        "production_recommendations": "DISABLED",
        "automatic_model_promotion": False,
        "development_season": DEVELOPMENT, "holdout_season": HOLDOUT,
        "model_under_test": "poisson-shrinkage-unvalidated-v4.1",
        "prespecified_candidates": {
            "development_only_prior_blend_grid": list(PRIOR_BLEND_GRID),
            "draw_adjust": "Add 0.03 absolute draw probability, proportionally reduce win sides",
            "league_frequency": "Expanding earlier-date league 1X2 frequency, fixed prior weight 20",
            "high_confidence": list(CONFIDENCE_CUTOFFS),
        },
        "upstream_archives": [],
        "missing_archive_scopes": [],
        "cohorts": {},
    }
    cohorts = defaultdict(list)
    source_errors = []
    byleague = defaultdict(dict)
    for season in (DEVELOPMENT, HOLDOUT):
        for league in LEAGUE_FILES:
            source = docs.get((season,league))
            if source is None:
                output["missing_archive_scopes"].append(season+"/"+league)
                continue
            document, content_hash = source
            try:
                matches, invalid = parse_archive(document)
                # Date-only retrospective data may contain later corrections.
                cohort, excluded = replay(matches, league, season)
            except (ValueError, TypeError, KeyError) as exc:
                source_errors.append(season+"/"+league+":"+type(exc).__name__)
                output["missing_archive_scopes"].append(season+"/"+league)
                continue
            cohorts[season].extend(cohort)
            byleague[league][season] = {
                "source_finished_matches": len(matches), "predicted": len(cohort),
                "excluded": excluded, "invalid_source_records": invalid,
                "statistics": evaluate_cohort(cohort),
            }
            output["upstream_archives"].append({
                "season": season, "league": league,
                "path": season+"/"+LEAGUE_FILES[league],
                "source_sha256": content_hash,
                "source_contains_verified_as_of_timestamps": False,
            })
    # Select blending only on 2024/25. 2025/26 is evaluated as a locked,
    # previously inspected retrospective test, NOT fresh prospective evidence.
    tuned = choose_prior_blend(cohorts[DEVELOPMENT])
    for season in (DEVELOPMENT, HOLDOUT):
        for row in cohorts[season]:
            row["prior_blend"] = blend_with_prior(
                row["original"], row["league_frequency"], tuned["weight"])
    output["development_only_prior_blend"] = tuned
    output["prior_blend_uses_holdout_labels_for_tuning"] = False
    output["holdout_has_already_been_inspected_previously"] = True
    output["prior_blend_automatic_promotion_permitted"] = False
    output["archive_validation_errors"] = source_errors
    output["by_league"] = dict(byleague)
    for season in (DEVELOPMENT, HOLDOUT):
        output["cohorts"][season] = evaluate_cohort(cohorts[season])
    development, holdout = (output["cohorts"][s] for s in (DEVELOPMENT,HOLDOUT))
    output["prior_blend_holdout"] = summary(cohorts[HOLDOUT], "prior_blend")
    output["prior_blend_holdout_paired_week_ci"] = block_ci(
        cohorts[HOLDOUT], "prior_blend") if cohorts[HOLDOUT] else None
    output["prior_blend_development"] = summary(cohorts[DEVELOPMENT], "prior_blend")
    output["holdout_season_samples"] = holdout["n"]
    weeks = set()
    for r in cohorts[HOLDOUT]:
        d = date.fromisoformat(r["date"])
        w = d.isocalendar()
        weeks.add((w.year, w.week))
    output["holdout_calendar_weeks"] = len(weeks)
    output["interpretation"] = (
        "RETROSPECTIVE_DIAGNOSTIC_NOT_PROSPECTIVE_EVIDENCE"
        if holdout["n"] >= MIN_HOLDOUT and len(weeks) >= MIN_WEEKS
        else "INSUFFICIENT_RETROSPECTIVE_HOLDOUT_COVERAGE"
    )
    output["historical_model_beat_simple_frequency_by_log_loss"] = (
        holdout["original"] is not None and holdout["league_frequency"] is not None
        and holdout["original"]["mean_log_loss"] <
            holdout["league_frequency"]["mean_log_loss"]
    )
    output["draw_adjust_improved_holdout_hit_rate"] = (
        holdout["original"] is not None and holdout["draw_adjust"] is not None
        and holdout["draw_adjust"]["hit_rate"] >
            holdout["original"]["hit_rate"]
    )
    output["reported_accuracy_is_not_forward_prediction_accuracy"] = True
    return output


def publish(path):
    documents = {}
    errors = []
    for season in (DEVELOPMENT, HOLDOUT):
        for league in LEAGUE_FILES:
            try:
                documents[(season,league)] = get_archive(season,league)
            except (OSError, ValueError, UnicodeError, TimeoutError) as exc:
                errors.append({"season": season, "league": league,
                               "error": type(exc).__name__})
    result = build(documents)
    result["download_errors"] = errors
    Path(path).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "model": result["model_under_test"],
        "evaluation": result["evaluation_type"],
        "development": result["cohorts"][DEVELOPMENT]["n"],
        "holdout": result["cohorts"][HOLDOUT]["n"],
        "holdout_original": result["cohorts"][HOLDOUT]["original"],
        "holdout_draw_adjust": result["cohorts"][HOLDOUT]["draw_adjust"],
        "holdout_frequency": result["cohorts"][HOLDOUT]["league_frequency"],
        "prior_blend_tuned_only_on_development": result["development_only_prior_blend"]["weight"],
        "prior_blend_holdout": result["prior_blend_holdout"],
        "prior_blend_95pct_ci": result["prior_blend_holdout_paired_week_ci"],
        "holdout_ci": result["cohorts"][HOLDOUT][
            "paired_week_bootstrap_draw_adjust_vs_original"],
        "missing_scopes": result["missing_archive_scopes"],
        "interpretation": result["interpretation"],
        "production_recommendations": "DISABLED",
    }, ensure_ascii=False))
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--output", default="retrospective_backtest.json")
    args = cli.parse_args()
    publish(args.output)
