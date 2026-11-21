"""Regularized opponent-adjusted goals; shadow-only, no verified betting utility.

This independent challenger replaces *only* how expected goals are estimated
in research. Old sealed A/B/C/D, any published weights and archive are untouched.
The source-name team graph is NOT an authenticated native-ID join. Historical
finished score rows are unverified and the injected clock is not a third-party
timestamp attestation. No official xG, odds, lineups or future scores are used.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
import math
from zoneinfo import ZoneInfo

from shadow_forecast import LEAGUES, predict_league, poisson_1x2

HK = ZoneInfo("Asia/Hong_Kong")
MODEL = "opponent-adjusted-regularized-poisson-research-v1"
MIN_GAMES = 60
MIN_HOME_ROLE_MATCHES = 4
MIN_AWAY_ROLE_MATCHES = 4
RIDGE_EXPOSURE = 6.0
MAX_ITERATIONS = 80
MAX_PARAMETER_ABS = 1.5
MAX_ROWS = 6000


def _hold(reason="INVALID_INPUT"):
    return {
        "schema": "football-king-opponent-adjusted-goals-research-v1",
        "model": MODEL,
        "status": "HOLD",
        "reason": reason,
        "candidate_count": 0,
        "comparisons": [],
        "ridge_pseudo_exposure": RIDGE_EXPOSURE,
        "minimum_training_games": MIN_GAMES,
        "training_policy": "PRIOR_HK_LOCAL_DAY_ONLY",
        "original_sealed_predictions_modified": False,
        "original_shadow_unchanged": True,
        "analysis_clock_is_supplied_not_attested": True,
        "fixture_identity_authenticated": False,
        "source_capture_attested": False,
        "actual_score_sources_independently_verified": False,
        "official_xg_used": False,
        "real_odds_available": False,
        "probabilities_calibrated": False,
        "verified_oos_improvement": False,
        "positive_ev_verified": False,
        "eligible_for_formal_forward_scoring": False,
        "model_promoted": False,
        "production_recommendations": "DISABLED",
    }


def _history(rows, today, now):
    """Duplicate-safe parity with the legacy historical fixture cohort."""
    by_fixture = {}
    by_event = {}
    for row in rows:
        if type(row) is not dict or row.get("status") != "FINISHED":
            continue
        home, away = row.get("home"), row.get("away")
        if (type(home) is not str or type(away) is not str
                or not home or not away or len(home) >= 110
                or len(away) >= 110 or home == away):
            continue
        try:
            day = date.fromisoformat(row["date"])
        except (KeyError, ValueError, TypeError):
            continue
        if day >= today:
            continue
        score = row.get("score_ft")
        if (type(score) is not list or len(score) != 2
                or any(type(n) is not int or not 0 <= n <= 20 for n in score)):
            continue
        claimed_kickoff = row.get("kickoff_utc")
        if claimed_kickoff is not None:
            if type(claimed_kickoff) is not str or len(claimed_kickoff) > 45:
                raise ValueError("HISTORICAL_KICKOFF_TIME_CONFLICT")
            try:
                fixture_clock = datetime.fromisoformat(
                    claimed_kickoff.replace("Z", "+00:00"))
            except (ValueError, OverflowError):
                raise ValueError("HISTORICAL_KICKOFF_TIME_CONFLICT") from None
            if (fixture_clock.tzinfo is None
                    or fixture_clock.utcoffset() is None
                    or fixture_clock.astimezone(HK).date() != day
                    or fixture_clock >= now):
                raise ValueError("HISTORICAL_KICKOFF_TIME_CONFLICT")
        key = (day, home, away)
        value = (day, home, away, score[0], score[1])
        if key in by_fixture and by_fixture[key] != value:
            raise ValueError("CONFLICTING_HISTORICAL_RESULT")
        by_fixture[key] = value
        event_id = row.get("event_id")
        if event_id is not None:
            if type(event_id) is not str or not event_id or len(event_id) > 128:
                raise ValueError("INVALID_HISTORY_SOURCE_EVENT_ID")
            previous = by_event.get(event_id)
            if previous is not None and previous != value:
                raise ValueError("CONFLICTING_HISTORY_SOURCE_EVENT_ID")
            by_event[event_id] = value
    return sorted(by_fixture.values())


def _fit_one_channel(games, league_mean, which):
    """Cyclic Newton fit of Poisson log(lambda)=log(mean)+attack+concede.

    Ridge penalty on both role coefficients prevents unidentifiable strength
    inflation and controls tiny samples. Fixed parameters are research choices,
    NOT tuned on the held-out result or on this week's published market.
    """
    if not games or not math.isfinite(league_mean) or league_mean <= 0:
        raise ValueError("INVALID_LEAGUE_BASELINE")
    attack = {team: 0.0 for team in sorted({g[0] for g in games})}
    concede = {team: 0.0 for team in sorted({g[1] for g in games})}
    by_attack = defaultdict(list)
    by_concede = defaultdict(list)
    for team, opp, goals in games:
        by_attack[team].append((team, opp, goals))
        by_concede[opp].append((team, opp, goals))

    base = math.log(league_mean)
    iterations = 0
    max_change = 0.0
    for iteration in range(MAX_ITERATIONS):
        iterations = iteration + 1
        max_change = 0.0
        for params, indexed in ((attack, by_attack), (concede, by_concede)):
            for team in sorted(params):
                current = params[team]
                gradient = RIDGE_EXPOSURE * current
                hessian = RIDGE_EXPOSURE
                for h, a, observed in indexed[team]:
                    rate = math.exp(base + attack[h] + concede[a])
                    gradient += rate - observed
                    hessian += rate
                step = max(-0.3, min(0.3, gradient / hessian))
                updated = max(-MAX_PARAMETER_ABS,
                              min(MAX_PARAMETER_ABS, current - step))
                params[team] = updated
                max_change = max(max_change, abs(updated - current))
        if max_change < 1e-9:
            break
    return attack, concede, iterations, max_change


def _fit_goal_roles(history_games):
    """Return venue-specific attack and concede multipliers, no external data."""
    if type(history_games) is not list or len(history_games) < MIN_GAMES:
        raise ValueError("INSUFFICIENT_OPPONENT_TRAINING_GAMES")
    if any(type(gh) is not int or type(ga) is not int
           or not 0 <= gh <= 20 or not 0 <= ga <= 20
           for _, _, gh, ga in history_games):
        raise ValueError("INVALID_TRAINING_GOAL")
    n = len(history_games)
    baseline_h = max(0.3, math.fsum(g[2] for g in history_games) / n)
    baseline_a = max(0.3, math.fsum(g[3] for g in history_games) / n)
    # Home goals are supplied by home attackers and allowed by away defenses.
    home_attack, away_concede, it_h, residual_h = _fit_one_channel(
        [(h, a, gh) for h, a, gh, _ in history_games], baseline_h, "home")
    # Away goals are supplied by away attackers and allowed by home defenses.
    away_attack, home_concede, it_a, residual_a = _fit_one_channel(
        [(a, h, ga) for h, a, _, ga in history_games], baseline_a, "away")
    return {
        "league_home_goals": baseline_h,
        "league_away_goals": baseline_a,
        "home_attack": {k: math.exp(x) for k, x in home_attack.items()},
        "away_concede": {k: math.exp(x) for k, x in away_concede.items()},
        "away_attack": {k: math.exp(x) for k, x in away_attack.items()},
        "home_concede": {k: math.exp(x) for k, x in home_concede.items()},
        "iterations": max(it_h, it_a),
        "last_change": max(residual_h, residual_a),
    }


def _explicit_event(rows, base):
    matches = [
        r for r in rows if type(r) is dict
        and r.get("event_id") == base["event_id"]
    ]
    if len(matches) != 1:
        return False
    row = matches[0]
    return (
        type(row.get("event_id")) is str
        and 4 <= len(row["event_id"]) <= 128
        and row.get("status") == "SCHEDULED"
        and row.get("score_ft") is None
        and row.get("home") == base["home"]
        and row.get("away") == base["away"]
        and row.get("kickoff_utc") == base["kickoff_utc"]
    )


def compare_shadow(rows, *, league, now):
    """Produce side-by-side research forecasts only for original eligible events."""
    if (type(now) is not datetime or now.tzinfo is None
            or now.utcoffset() is None):
        raise ValueError("NAIVE_OR_INVALID_MODEL_CLOCK")
    out = _hold()
    out["as_of_utc_self_declared"] = now.astimezone(timezone.utc).isoformat()
    if type(league) is not str or league not in LEAGUES:
        out["reason"] = "LEAGUE_NOT_IN_ORIGINAL_SHADOW"
        return out
    if type(rows) is not list or len(rows) > MAX_ROWS:
        out["reason"] = "INVALID_OR_OVERSIZED_INPUT"
        return out
    today = now.astimezone(HK).date()
    try:
        history = _history(rows, today, now)
    except ValueError as error:
        out["reason"] = str(error)
        return out
    if len(history) < MIN_GAMES:
        out["reason"] = "INSUFFICIENT_OPPONENT_TRAINING_GAMES"
        return out
    try:
        baseline = predict_league(rows, league, now)
    except (ValueError, TypeError, KeyError, OverflowError):
        out["reason"] = "ORIGINAL_SHADOW_INPUT_REJECTED"
        return out
    if not baseline:
        out["reason"] = "NO_ELIGIBLE_ORIGINAL_SHADOW_FIXTURE"
        return out
    try:
        # Protect exact cohort identity with the unmodified original SHA.
        digest = hashlib.sha256(json.dumps(
            sorted(history), ensure_ascii=False, default=str).encode("utf-8")
        ).hexdigest()
        fit = _fit_goal_roles([
            (home, away, gh, ga)
            for _, home, away, gh, ga in history
        ])
    except (ValueError, TypeError, OverflowError, KeyError):
        out["reason"] = "INVALID_OR_CONFLICTING_OPPONENT_HISTORY"
        return out
    except ArithmeticError:
        out["reason"] = "NUMERIC_STRENGTH_FIT_FAILED"
        return out
    out["training_distinct_games"] = len(history)
    out["training_observations_sha256"] = digest
    out["strength_fit_iterations"] = fit["iterations"]
    out["strength_fit_last_change"] = round(fit["last_change"], 9)
    out["league_goal_baselines"] = {
        "home": round(fit["league_home_goals"], 6),
        "away": round(fit["league_away_goals"], 6),
    }

    roles_h, roles_a = Counter(), Counter()
    for _, home, away, _, _ in history:
        roles_h[home] += 1
        roles_a[away] += 1
    comparisons = []
    for old in baseline:
        if not _explicit_event(rows, old):
            continue
        if (old.get("training_games") != len(history)
                or old.get("training_observations_sha256") != digest
                or old.get("calibrated") is not False
                or old.get("production_recommendations") != "DISABLED"):
            out["reason"] = "ORIGINAL_COHORT_SHA_MISMATCH"
            return out
        h, a = old["home"], old["away"]
        if (roles_h[h] < MIN_HOME_ROLE_MATCHES
                or roles_a[a] < MIN_AWAY_ROLE_MATCHES):
            continue
        try:
            predicted_home = max(0.1, min(5.5,
                fit["league_home_goals"]
                * fit["home_attack"][h] * fit["away_concede"][a]))
            predicted_away = max(0.1, min(5.5,
                fit["league_away_goals"]
                * fit["away_attack"][a] * fit["home_concede"][h]))
            p = poisson_1x2(predicted_home, predicted_away)
        except (ValueError, OverflowError, KeyError, ArithmeticError):
            out["reason"] = "INVALID_OR_UNSEEN_TEAM_STRENGTH"
            return out
        comparisons.append({
            "league": league,
            "event_id_unverified": old["event_id"],
            "home_source_name_unverified": h,
            "away_source_name_unverified": a,
            "kickoff_utc_source_claim": old["kickoff_utc"],
            "as_of_utc_self_declared": out["as_of_utc_self_declared"],
            "training_observations_sha256": digest,
            "original_shadow": {
                "model": old["model"],
                "p_home": old["p_home"], "p_draw": old["p_draw"],
                "p_away": old["p_away"],
                "expected_home_goals": old["expected_home_goals"],
                "expected_away_goals": old["expected_away_goals"],
                "training_observations_sha256": old["training_observations_sha256"],
            },
            "candidate": {
                "model": MODEL,
                "p_home": p[0], "p_draw": p[1], "p_away": p[2],
                "expected_home_goals": round(predicted_home, 5),
                "expected_away_goals": round(predicted_away, 5),
                "betting_eligible": False,
                "official_xg_available": False,
                "improvement_proven": False,
            },
            "training_home_role_matches": roles_h[h],
            "training_away_role_matches": roles_a[a],
        })
    if not comparisons:
        out["reason"] = "NO_ORIGINAL_MATCH_WITH_SUFFICIENT_VENUE_ROLES"
        return out
    out["candidate_count"] = len(comparisons)
    out["comparisons"] = comparisons
    out["status"] = "RESEARCH_ONLY"
    out["reason"] = "RESEARCH_NOT_INDEPENDENTLY_AUTHENTICATED_OR_CALIBRATED"
    return out
