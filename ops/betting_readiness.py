"""Independent paper-only 1X2 betting readiness and abstention audit.

The existing 1X2 market field is a derived consensus *probability*, not a
bookmaker's executable price. Even if two models agree on the favourite, this
does not create positive EV. This file never fabricates an odds quote, ROI,
Kelly stake, calibrated confidence bound or actionable bet.
"""
import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = "football-king-betting-readiness-audit-v1"
MAX_PAPERS = 12
MAX_HORIZON = timedelta(days=7)
MIN_KICKOFF = timedelta(minutes=60)
MAX_SELECTION_AGE = timedelta(hours=10)


def parse_utc(v):
    if not isinstance(v, str):
        raise ValueError("MISSING_RESEARCH_TIMESTAMP")
    obj = datetime.fromisoformat(v.replace("Z", "+00:00"))
    if obj.tzinfo is None:
        raise ValueError("RESEARCH_TIMESTAMP_WITHOUT_TIMEZONE")
    return obj.astimezone(timezone.utc)


def collect(production_gate, research, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_AUDIT_TIME")
    data = {
        "schema": SCHEMA, "as_of_utc": now.isoformat(),
        "status": "HOLD", "reason": "MISSING_OR_UNSAFE_RECOMMENDATION_EVIDENCE",
        "production_recommendations": "DISABLED",
        "bookmaker_executable_1x2_price_available": False,
        "calibrated_lower_probability_bound_available": False,
        "independent_forward_validation_complete": False,
        "genuine_positive_expected_value_verified": False,
        "bet_recommendations": [], "bet_recommendation_count": 0,
        "suggested_stakes": [], "paper_watchlist": [],
        "paper_watchlist_is_not_betting_advice": True,
        "never_infer_decimal_odds_from_consensus_probabilities": True,
        "release_requires_independent_manual_approval": True,
        "missing_evidence": [
            "INDEPENDENT_FORWARD_MODEL_CALIBRATION",
            "AUTHENTICATED_EXECUTABLE_BOOKMAKER_1X2_ODDS_AT_DECISION_TIME",
            "POSITIVE_CONSERVATIVE_EV_AFTER_MARKET_COSTS",
            "INDEPENDENTLY_CHECKED_RESULTS_AND_MARKET_BENCHMARK",
            "INDEPENDENT_RISK_APPROVAL",
        ],
    }
    if (not isinstance(production_gate, dict) or not isinstance(research, dict)
            or production_gate.get("schema") != "football-king-production-qualification-1"
            or production_gate.get("status") != "HOLD"
            or production_gate.get("production_recommendations") != "DISABLED"
            or production_gate.get("ready_for_independent_review") is not False
            or research.get("schema") != "football-king-explainable-research-selections-v1"
            or research.get("production_recommendations") != "DISABLED"
            or research.get("model_is_uncalibrated") is not True
            or research.get("market_prices_are_not_executable") is not True
            or research.get("value_recommendation_count") != 0
            or not isinstance(research.get("selections"), list)):
        return data
    try:
        age = now - parse_utc(research["as_of_utc"])
        if not timedelta(minutes=-5) <= age <= MAX_SELECTION_AGE:
            data["reason"] = "STALE_RESEARCH_CANDIDATES"
            return data
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
        data["reason"] = "INVALID_RESEARCH_TIMESTAMP"
        return data
    checks = production_gate.get("conditions")
    if not isinstance(checks, dict):
        return data
    data["failed_production_checks"] = sorted(
        k for k, passing in checks.items() if passing is not True)
    data["settled_samples"] = production_gate.get("settled_samples")
    for case in research["selections"][:100]:
        if not isinstance(case, dict):
            continue
        try:
            if (case.get("production_recommendations") != "DISABLED"
                    or case.get("value_bet_verified") is not False
                    or case.get("executable_market_odds_available") is not False
                    or case.get("market_direction_agrees") is not True
                    or case.get("qualifies_for_research_shortlist") is not True
                    or not isinstance(case.get("case_id"), str)
                    or not isinstance(case.get("league"), str)
                    or not all(isinstance(case.get(x), str) and 0 < len(case[x]) <= 110
                               for x in ("home", "away"))):
                continue
            kickoff = parse_utc(case["kickoff_utc"])
            predicted = parse_utc(case["prediction_utc"])
            if not predicted <= now < kickoff - MIN_KICKOFF:
                continue
            if kickoff - now > MAX_HORIZON:
                continue
            p = case.get("research_probability")
            if type(p) not in (float, int) or not math.isfinite(p) or not 0 <= p <= 1:
                continue
            caseid = case["case_id"]
            if len(caseid) > 150:
                continue
            data["paper_watchlist"].append({
                "case_id": caseid,
                "league": case["league"],
                "home": case["home"], "away": case["away"],
                "kickoff_utc": kickoff.isoformat(),
                "model_top_direction": case.get("direction"),
                "uncalibrated_model_top_probability": round(p, 6),
                "historical_replay_60pct_research_band": p >= .60,
                "market_direction_agrees_only": True,
                "model_probabilities_certified": False,
                "estimated_ev": None,
                "required_licensed_bookmaker_price": None,
                "bet_eligible": False,
                "reason": "NO_CALIBRATED_LOWER_BOUND_OR_EXECUTABLE_QUOTE",
            })
        except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
            continue
    data["paper_watchlist"] = sorted(
        data["paper_watchlist"], key=lambda x: (
            not x["historical_replay_60pct_research_band"],
            -x["uncalibrated_model_top_probability"],
            x["kickoff_utc"], x["case_id"]))[:MAX_PAPERS]
    data["paper_watchlist_count"] = len(data["paper_watchlist"])
    data["high_probability_paper_count"] = sum(
        x["historical_replay_60pct_research_band"]
        for x in data["paper_watchlist"])
    data["reason"] = "RESEARCH_SHORTLIST_VISIBLE_BETTING_GATE_STILL_HOLD"
    return data


def publish(site):
    site = Path(site)
    def load(file):
        try:
            return json.loads((site / file).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return None
    report = collect(load("production_gate.json"), load("research_selections.json"))
    (site / "betting_readiness.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"], "reason": report["reason"],
        "paper_research_cases": report.get("paper_watchlist_count", 0),
        "value_bets": report["bet_recommendation_count"],
        "production_recommendations": report["production_recommendations"],
    }, ensure_ascii=False))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="app/site")
    args = p.parse_args()
    publish(args.site)
