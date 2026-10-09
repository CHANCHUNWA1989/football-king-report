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

LABELS = ("主勝", "和局", "客勝")
LEAGUES = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")
MAX_MARKET_AGE_HOURS = 16
MAX_MODEL_AGE_HOURS = 10
MAX_DAYS_AHEAD = 7
MIN_KICKOFF_BUFFER_MINUTES = 60
MIN_TOP_PROBABILITY = 0.46
MIN_TOP_MARGIN = 0.09
MAX_RESEARCH_SELECTIONS = 8


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
        "excluded_reasons": excluded or {},
        "model_is_uncalibrated": True,
        "market_prices_are_not_executable": True,
        "validated_positive_expected_value": False,
        "estimated_roi": None,
        "automatic_bets": False,
        "production_recommendations": "DISABLED",
        "warning": "研究選向非下注建議；任何模型/市場差距都不是可執行正EV證據。",
    }


def build(shadow, pairing, status, *, now=None):
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
    return result


def publish(site):
    site = Path(site)
    shadow = json.loads((site / "shadow.json").read_text(encoding="utf-8"))
    paired = json.loads((site / "market_comparison.json").read_text(encoding="utf-8"))
    state = json.loads((site / "status.json").read_text(encoding="utf-8"))
    result = build(shadow, paired, state)
    (site / "research_selections.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "status": result["status"], "selected_count": result["selected_count"],
        "review_count": result["review_count"], "paired_count": result["paired_count"],
        "reason": result["reason"], "production_recommendations": "DISABLED",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="app/site")
    args = parser.parse_args()
    print(json.dumps(publish(args.site), ensure_ascii=False))
