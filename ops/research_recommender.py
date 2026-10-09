"""Explainable football research selections from sealed pre-match forecasts.

This is a useful 1X2 direction shortlist, NOT a claim of calibrated
probabilities, actionable bookmaker odds, positive EV, CLV or betting ROI.
No fixture without strictly paired pre-prediction market data is selected.
All low-information and expired conditions abstain (never fabricate picks).
"""
import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from team_identity import team_id

LABELS = ("主勝", "和局", "客勝")
LEAGUES = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")
MAX_MARKET_AGE_HOURS = 16
MAX_MODEL_AGE_HOURS = 10
MAX_DAYS_AHEAD = 7
MIN_KICKOFF_BUFFER_MINUTES = 60
MIN_TOP_PROBABILITY = 0.46
MIN_TOP_MARGIN = 0.09
MAX_RESEARCH_SELECTIONS = 8
MAX_MODEL_ONLY_WATCHLIST = 5
MODEL_ONLY_MIN_TOP = 0.60
MODEL_ONLY_MIN_MARGIN = 0.18


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_TIME")
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return date.astimezone(timezone.utc)


def probabilities(value):
    if not isinstance(value, list) or len(value) != 3:
        return None
    if not all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1
               for v in value):
        return None
    if abs(sum(value) - 1) > .002:
        return None
    return [float(v) for v in value]


def empty(as_of, reason, eligible=0, excluded=None):
    return {
        "schema": "football-king-explainable-research-selections-v1",
        "as_of_utc": as_of.isoformat(),
        "status": "HOLD" if reason in ("REPORT_HOLD", "INVALID_SOURCES", "STALE_MODEL_SNAPSHOT")
                  else "RESEARCH_ONLY",
        "reason": reason, "selection_mode": "SHADOW_RESEARCH_ONLY",
        "selected_count": 0, "paired_count": eligible,
        "selections": [], "review_count": 0, "reviews": [],
        "fallback_mode": "NOT_NEEDED",
        "fallback_reason": None,
        "model_only_count": 0,
        "model_only_watchlist": [],
        "model_only_is_betting_advice": False,
        "excluded_reasons": excluded or {},
        "model_is_uncalibrated": True,
        "market_prices_are_not_executable": True,
        "validated_positive_expected_value": False,
        "estimated_roi": None,
        "automatic_bets": False,
        "production_recommendations": "DISABLED",
        "warning": "研究選向非下注建議；任何模型/市場差距都不是可執行正EV證據。",
    }


def build(shadow, pairing, status, *, now=None, market_status=None):
    """Return repeatable picks/reviews with reasons and strict abstention."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    result = empty(now, "NO_QUALIFIED_CANDIDATES")
    if (not all(isinstance(o, dict) for o in (shadow, pairing, status))
            or status.get("production_recommendations") != "DISABLED"
            or shadow.get("production_recommendations") != "DISABLED"
            or pairing.get("production_recommendations") != "DISABLED"):
        return empty(now, "INVALID_SOURCES")
    if status.get("status") != "RESEARCH_ONLY":
        return empty(now, "REPORT_HOLD")
    if (shadow.get("status") != "SHADOW_ONLY"
            or pairing.get("status") not in ("HOLD", "RESEARCH_ONLY")
            or not isinstance(pairing.get("comparisons"), list)):
        return empty(now, "INVALID_SOURCES")
    try:
        model_capture = timestamp(shadow["as_of_utc"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return empty(now, "INVALID_SOURCES")
    if not timedelta(minutes=-5) <= now - model_capture <= timedelta(hours=MAX_MODEL_AGE_HOURS):
        return empty(now, "STALE_MODEL_SNAPSHOT")
    comparisons = pairing["comparisons"]
    result["paired_count"] = len(comparisons)
    recommendations, reviews, rejected = [], [], {}
    ids = set()
    for row in comparisons:
        reason = None
        if not isinstance(row, dict):
            reason = "INVALID_PAIR"
        else:
            try:
                if (row.get("production_recommendations") != "DISABLED"
                        or row.get("available_for_betting") is not False
                        or row.get("historical_outcome") is not None
                        or row.get("result") is not None
                        or row.get("league") not in LEAGUES
                        or not row.get("case_id")):
                    raise ValueError("NOT_STRICT_UNSETTLED_PAIR")
                if row["case_id"] in ids:
                    raise ValueError("DUPLICATE_PAIR")
                ids.add(row["case_id"])
                p, market = probabilities(row.get("model")), probabilities(row.get("market"))
                if p is None or market is None:
                    raise ValueError("INVALID_PROBABILITIES")
                prediction = timestamp(row["prediction_utc"])
                collected = timestamp(row["market_snapshot_utc"])
                quote_at = timestamp(row["market_updated_utc"])
                kickoff = timestamp(row["kickoff_utc"])
                if abs((prediction - model_capture).total_seconds()) > 120:
                    raise ValueError("PREDICTION_CAPTURE_MISMATCH")
                if not (quote_at <= collected <= prediction < kickoff):
                    raise ValueError("MARKET_LATER_THAN_PREDICTION")
                if (now - quote_at).total_seconds() < -300:
                    raise ValueError("FUTURE_MARKET_TIMESTAMP")
                if (now - quote_at).total_seconds() > MAX_MARKET_AGE_HOURS * 3600:
                    raise ValueError("STALE_MARKET")
                minutes_to_kickoff = (kickoff - now).total_seconds() / 60
                if minutes_to_kickoff < MIN_KICKOFF_BUFFER_MINUTES:
                    raise ValueError("KICKOFF_TOO_CLOSE")
                if minutes_to_kickoff > MAX_DAYS_AHEAD * 24 * 60:
                    raise ValueError("FIXTURE_TOO_FAR_AHEAD")
                top_index = max(range(3), key=lambda i: p[i])
                ranked = sorted(p, reverse=True)
                gap = ranked[0] - ranked[1]
                market_top = max(range(3), key=lambda i: market[i])
                aligned = top_index == market_top
                qualified = (p[top_index] >= MIN_TOP_PROBABILITY
                             and gap >= MIN_TOP_MARGIN and aligned)
                # Rank by model separation and two-source directional agreement.
                # Never rank by model-minus-market as though it were EV.
                priority_score = round(p[top_index] * 100 + gap * 30, 2)
                note = []
                note.append("模型主選「" + LABELS[top_index] + "」；未校準機率 " +
                            f"{p[top_index]:.1%}")
                note.append("模型首選與次選差 " + f"{gap:.1%}")
                note.append("市場無水共識最高選項「" + LABELS[market_top] + "」" +
                            ("，方向一致" if aligned else "，同模型有分歧"))
                if not aligned:
                    note.append("市場方向有分歧，只供觀察，唔建議升級為研究首選")
                if p[top_index] < MIN_TOP_PROBABILITY:
                    note.append("模型最高機率未達研究篩選門檻")
                if gap < MIN_TOP_MARGIN:
                    note.append("首選同次選太接近，不宜強行推薦")
                case = {
                    "case_id": row["case_id"],
                    "league": row["league"], "home": row["home"], "away": row["away"],
                    "kickoff_utc": kickoff.isoformat(),
                    "prediction_utc": prediction.isoformat(),
                    "market_snapshot_utc": collected.isoformat(),
                    "market_updated_utc": quote_at.isoformat(),
                    "direction": ("HOME", "DRAW", "AWAY")[top_index],
                    "direction_zh": LABELS[top_index],
                    "research_probability": round(p[top_index], 6),
                    "model_probability_1x2": p,
                    "market_consensus_1x2": market,
                    "model_top_margin": round(gap, 6),
                    "market_direction_agrees": aligned,
                    "ranking_score_not_betting_edge": priority_score,
                    "reasons": note,
                    "reliability": "UNCALIBRATED_RESEARCH_ONLY",
                    "qualifies_for_research_shortlist": bool(qualified),
                    "executable_market_odds_available": False,
                    "value_bet_verified": False,
                    "suggested_stake": None,
                    "production_recommendations": "DISABLED",
                }
                (recommendations if qualified else reviews).append(case)
            except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as exc:
                reason = str(exc) if str(exc) in (
                    "DUPLICATE_PAIR", "INVALID_PROBABILITIES", "STALE_MARKET",
                    "FUTURE_MARKET_TIMESTAMP", "MARKET_LATER_THAN_PREDICTION",
                    "KICKOFF_TOO_CLOSE", "FIXTURE_TOO_FAR_AHEAD",
                    "NOT_STRICT_UNSETTLED_PAIR", "PREDICTION_CAPTURE_MISMATCH"
                ) else "INVALID_PAIR"
        if reason:
            rejected[reason] = rejected.get(reason, 0) + 1
    recommendations.sort(key=lambda r: (-r["ranking_score_not_betting_edge"],
                                        r["kickoff_utc"], r["case_id"]))
    reviews.sort(key=lambda r: (r["kickoff_utc"], r["case_id"]))
    result["selected_count"] = min(len(recommendations), MAX_RESEARCH_SELECTIONS)
    result["selections"] = recommendations[:MAX_RESEARCH_SELECTIONS]
    result["review_count"] = len(reviews)
    result["reviews"] = reviews[:15]
    result["excluded_reasons"] = rejected
    result["reason"] = ("EXPLAINABLE_RESEARCH_CANDIDATES_NOT_BETS"
                        if recommendations else "NO_RESEARCH_SHORTLIST_WITH_CURRENT_EVIDENCE")
    # Fail to low-evidence research-only observation when quota is exhausted,
    # the archived market has become old, or there are no strictly matched quotes.
    # Never present this independently as a validated betting recommendation.
    reason = None
    quota = market_status.get("quota") if isinstance(market_status, dict) else None
    if isinstance(quota, dict) and (
            type(quota.get("used")) is int and quota["used"] >= 360
            or type(quota.get("remaining")) is int and quota["remaining"] <= 141):
        reason = "FREE_ODDS_QUOTA_NEAR_LIMIT"
    elif isinstance(market_status, dict) and market_status.get("source_state") in (
            "HOLD", "NOT_YET_CONNECTED"):
        reason = "NO_CURRENT_FREE_MARKET_DATA"
    elif not comparisons:
        reason = "NO_STRICT_MARKET_MATCHES"
    # Exclusions caused by market freshness or timing are also reasons to
    # degrade if there is no first-class market-based selection remaining.
    elif not recommendations and any(k in rejected for k in (
            "STALE_MARKET", "MARKET_LATER_THAN_PREDICTION")):
        reason = "MARKET_TIME_VALIDITY_REJECTED"

    if reason:
        result["fallback_mode"] = "MODEL_ONLY_LOW_EVIDENCE"
        result["fallback_reason"] = reason
        models = shadow.get("predictions")
        if isinstance(models, list):
            valid_pair_ids = {
                (p.get("league"), team_id(p.get("league"), p.get("home")),
                 team_id(p.get("league"), p.get("away")), p.get("kickoff_utc"))
                for p in comparisons if isinstance(p, dict)
            }
            watchlist = []
            used_models = set()
            for pred in models:
                if not isinstance(pred, dict):
                    continue
                try:
                    if (pred.get("production_recommendations") != "DISABLED"
                            or pred.get("league") not in LEAGUES
                            or pred.get("status") in ("FINISHED", "CANCELLED")
                            or not all(isinstance(pred.get(n), str) and pred[n] for n in
                                       ("event_id", "home", "away", "kickoff_utc", "prediction_utc"))):
                        continue
                    kickoff = timestamp(pred["kickoff_utc"])
                    produced = timestamp(pred["prediction_utc"])
                    if (abs((produced - model_capture).total_seconds()) > 120
                            or produced > now + timedelta(minutes=5)
                            or not MIN_KICKOFF_BUFFER_MINUTES * 60 <=
                            (kickoff - now).total_seconds() <= MAX_DAYS_AHEAD * 86400):
                        continue
                    pv = probabilities([pred["p_home"], pred["p_draw"], pred["p_away"]])
                    if pv is None:
                        continue
                    best = max(range(3), key=lambda i: pv[i])
                    ranking = sorted(pv, reverse=True)
                    margin = ranking[0] - ranking[1]
                    if pv[best] < MODEL_ONLY_MIN_TOP or margin < MODEL_ONLY_MIN_MARGIN:
                        continue
                    identifier = (pred["league"], team_id(pred["league"], pred["home"]),
                                  team_id(pred["league"], pred["away"]), pred["kickoff_utc"])
                    # No duplication of market-confirmed observations in fallback.
                    if identifier in valid_pair_ids or identifier in used_models:
                        continue
                    used_models.add(identifier)
                    watchlist.append({
                        "event_id": pred["event_id"], "league": pred["league"],
                        "home": pred["home"], "away": pred["away"],
                        "kickoff_utc": kickoff.isoformat(),
                        "prediction_utc": produced.isoformat(),
                        "direction": ("HOME", "DRAW", "AWAY")[best],
                        "direction_zh": LABELS[best],
                        "research_probability": round(pv[best], 6),
                        "model_top_margin": round(margin, 6),
                        "reliability": "LOW_UNVALIDATED_NO_MARKET",
                        "market_confirmed": False,
                        "value_bet_verified": False,
                        "executable_market_odds_available": False,
                        "suggested_stake": None,
                        "qualifies_for_betting": False,
                        "production_recommendations": "DISABLED",
                        "reasons": [
                            "免費賠率未能提供可比較嘅當時市場基準",
                            "只按未校準模型篩選「" + LABELS[best] + "」",
                            "模型概率 " + f"{pv[best]:.1%}" +
                            "；首選與次選差 " + f"{margin:.1%}",
                            "低證據研究觀察，並非投注建議或價值投注"
                        ]
                    })
                except (KeyError, TypeError, ValueError, OverflowError):
                    continue
            watchlist.sort(key=lambda r: (-r["research_probability"],
                                         r["kickoff_utc"], r["event_id"]))
            result["model_only_watchlist"] = watchlist[:MAX_MODEL_ONLY_WATCHLIST]
            result["model_only_count"] = len(result["model_only_watchlist"])
    return result


def publish(site):
    site = Path(site)
    shadow = json.loads((site / "shadow.json").read_text(encoding="utf-8"))
    paired = json.loads((site / "market_comparison.json").read_text(encoding="utf-8"))
    state = json.loads((site / "status.json").read_text(encoding="utf-8"))
    market_summary = json.loads((site / "market_status.json").read_text(encoding="utf-8"))
    result = build(shadow, paired, state, market_status=market_summary)
    (site / "research_selections.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "status": result["status"], "selected_count": result["selected_count"],
        "review_count": result["review_count"], "paired_count": result["paired_count"],
        "fallback_mode": result["fallback_mode"],
        "model_only_count": result["model_only_count"],
        "reason": result["reason"], "production_recommendations": "DISABLED",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="app/site")
    args = parser.parse_args()
    print(json.dumps(publish(args.site), ensure_ascii=False))
