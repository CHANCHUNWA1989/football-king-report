"""Read-only, no-bet, provenance-limited model-vs-market bias audit.

Use only timestamped archived *same fixture* forecasts and market vectors.
Source timestamps are self-reported metadata, not cryptographic proof of
an independently verified result or of bookmaker-price executability.
Do not train a challenger or change frozen A/B/C forecast weights here.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import math
import random

LEAGUES = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")
MIN_CASES = 300
MIN_WEEKS = 12
MIN_LEAGUES = 4
MIN_CASES_PER_LEAGUE = 40
BOOTSTRAP_REPEATS = 400


def _instant(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_ARCHIVED_TIMESTAMP")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise ValueError("INVALID_ARCHIVED_TIMESTAMP") from exc
    if instant.tzinfo is None:
        raise ValueError("NAIVE_ARCHIVED_TIMESTAMP")
    return instant.astimezone(timezone.utc)


def _vector(p):
    if (not isinstance(p, list) or len(p) != 3
            or any(type(v) not in (float, int) or not math.isfinite(v)
                   or v < 0 or v > 1 for v in p)
            or abs(sum(p) - 1) > 0.002):
        raise ValueError("INVALID_ARCHIVED_PROBABILITIES")
    return [v / sum(p) for v in p]


def _score(p, y):
    return (-math.log(max(p[y], 1e-15)),
            sum((v - int(i == y)) ** 2 for i, v in enumerate(p)))


def audit(rows, *, archived_at_utc):
    """Fail closed on duplicate, post-kickoff, future or malformed archive rows."""
    if not isinstance(rows, list) or len(rows) > 30000:
        raise ValueError("INVALID_ARCHIVED_ROWS")
    archive = _instant(archived_at_utc)
    out = {
        "schema": "football-king-model-market-bias-shadow-v1",
        "status": "HOLD" if not rows else "RESEARCH_ONLY",
        "sample_count": len(rows),
        "independent_result_authentication_count": 0,
        "archive_source_timestamps_independently_authenticated": False,
        "estimated_calibration_is_reliable": False,
        "model_market_advantage_proven": False,
        "betting_ev_verified": False,
        "recommended_bets": [],
        "production_recommendations": "DISABLED",
        "warning_zh": "樣本及來源未獲獨立驗證；此為回顧性診斷，不代表正式勝率、正EV或可下注賠率。",
        "diagnostics": None,
    }
    if not rows:
        return out

    seen = set()
    league_counts = Counter()
    groups = defaultdict(list)
    loss = {"model_log": 0.0, "market_log": 0.0,
            "model_brier": 0.0, "market_brier": 0.0}
    model_home_top = market_home_top = actual_home = 0
    model_home_sum = market_home_sum = 0.0
    model_hit = market_hit = 0
    source_claims = 0
    for row in rows:
        if (not isinstance(row, dict)
                or row.get("production_recommendations") != "DISABLED"
                or row.get("league") not in LEAGUES
                or type(row.get("y")) is not int or row["y"] not in (0, 1, 2)
                or not isinstance(row.get("key"), str) or not row["key"]):
            raise ValueError("INVALID_ARCHIVED_SAMPLE")
        identity = (row["league"], row["key"])
        if identity in seen:
            raise ValueError("DUPLICATE_ARCHIVED_SAMPLE")
        seen.add(identity)
        market_at = _instant(row.get("market_utc"))
        forecast_at = _instant(row.get("forecast_utc"))
        kickoff_at = _instant(row.get("kickoff_utc"))
        if not (market_at <= forecast_at < kickoff_at <= archive):
            raise ValueError("UNSAFE_ARCHIVED_TIME_ORDER")
        p, m, y = _vector(row.get("p")), _vector(row.get("m")), row["y"]
        a_ll, a_bs = _score(p, y)
        m_ll, m_bs = _score(m, y)
        loss["model_log"] += a_ll
        loss["market_log"] += m_ll
        loss["model_brier"] += a_bs
        loss["market_brier"] += m_bs
        mid = max(range(3), key=lambda i: p[i])
        market_id = max(range(3), key=lambda i: m[i])
        model_home_top += int(mid == 0)
        market_home_top += int(market_id == 0)
        actual_home += int(y == 0)
        model_hit += int(mid == y)
        market_hit += int(market_id == y)
        model_home_sum += p[0]
        market_home_sum += m[0]
        league_counts[row["league"]] += 1
        week = kickoff_at.strftime("%G-W%V")
        groups[week].append(m_ll - a_ll)
        source_claims += int(row.get("fixture_result_source_independently_verified") is True)

    n = len(rows)
    weeks = len(groups)
    enough = (n >= MIN_CASES and weeks >= MIN_WEEKS
              and sum(count >= MIN_CASES_PER_LEAGUE for count in league_counts.values()) >= MIN_LEAGUES)
    ci = None
    if enough:
        # Paired weekly-block resampling, not an iid fixture bootstrap.
        # CI is descriptive even if it excludes zero; never a promotion pass.
        rng = random.Random(20261012)
        blocks = [groups[k] for k in sorted(groups)]
        estimates = []
        for _ in range(BOOTSTRAP_REPEATS):
            chosen = [blocks[rng.randrange(weeks)] for _ in range(weeks)]
            vals = [v for week in chosen for v in week]
            estimates.append(sum(vals) / len(vals))
        estimates.sort()
        ci = [round(estimates[10], 6), round(estimates[390], 6)]
    out["diagnostics"] = {
        "model_log_loss": round(loss["model_log"] / n, 6),
        "market_log_loss": round(loss["market_log"] / n, 6),
        "model_brier": round(loss["model_brier"] / n, 6),
        "market_brier": round(loss["market_brier"] / n, 6),
        "market_minus_model_log_loss": round((loss["market_log"] - loss["model_log"]) / n, 6),
        "market_minus_model_brier": round((loss["market_brier"] - loss["model_brier"]) / n, 6),
        "model_home_top_count": model_home_top,
        "market_home_top_count": market_home_top,
        "actual_home_wins_count": actual_home,
        "mean_model_home_probability": round(model_home_sum / n, 6),
        "mean_market_home_probability": round(market_home_sum / n, 6),
        "actual_home_win_fraction": round(actual_home / n, 6),
        "model_top_choice_correct": model_hit,
        "market_top_choice_correct": market_hit,
        "claimed_independent_result_flags_not_authenticated": source_claims,
        "independent_week_blocks": weeks,
        "league_case_counts": {l: league_counts[l] for l in LEAGUES},
        "remaining_to_300": max(0, MIN_CASES - n),
        "remaining_week_blocks_to_12": max(0, MIN_WEEKS - weeks),
        "leagues_with_40_cases": sum(v >= MIN_CASES_PER_LEAGUE for v in league_counts.values()),
        "descriptive_coverage_thresholds_met": enough,
        "paired_week_block_bootstrap_95pct_ci": ci,
        "bootstrap_is_descriptive_and_not_result_authentication": True,
        "home_bias_is_a_small_sample_observation_not_a_calibrated_correction": True,
        "official_lineup_used_by_model_verified": False,
        "market_prices_are_executable": False,
    }
    return out
