"""Independent, deliberately non-promoting audit of replay risk and drift.

Consumes a real public historical date-only retrospective report. Research
observations may prioritize prospective Shadow monitoring, but must never
establish deployable betting value or a calibrated win probability.
"""
import argparse
import json
import math
from pathlib import Path

SCHEMA = "football-king-retrospective-stability-audit-v1"
HISTORICAL = "football-king-historical-date-replay-v1"
THRESHOLD = 0.60
MIN_HIGH_CONFIDENCE_SAMPLES = 40
MAX_SEASON_CHANGE = 0.12


def valid_num(n):
    return type(n) in (int, float) and math.isfinite(n)


def fixed_bin(scope, threshold=THRESHOLD):
    values = scope.get("coverage_at_confidence_cutoffs") if isinstance(scope, dict) else None
    if not isinstance(values, list):
        return None
    matches = [x for x in values if isinstance(x, dict)
               and x.get("minimum_model_probability") == threshold]
    if len(matches) != 1:
        return None
    row = matches[0]
    n, hit, ci = row.get("selected"), row.get("hit_rate"), row.get("hit_rate_wilson95")
    if (type(n) is not int or not 0 <= n <= 10000
            or not valid_num(hit) or not 0 <= hit <= 1
            or not isinstance(ci, list) or len(ci) != 2
            or not all(valid_num(v) and 0 <= v <= 1 for v in ci)
            or ci[0] > hit or hit > ci[1]):
        return None
    return {"n": n, "hit_rate": hit, "wilson95": ci,
            "minimum_probability": threshold}


def audit(report):
    result = {
        "schema": SCHEMA, "status": "HOLD",
        "reason": "NO_VALID_HISTORICAL_REPLAY",
        "evaluation_type": "RETROSPECTIVE_SHADOW_STABILITY_AUDIT_ONLY",
        "historical_source_revisions_possible": True,
        "model_probabilities_not_certified": True,
        "market_beat_unverified": True,
        "executable_prices_absent": True,
        "automatic_probability_calibration": False,
        "automatic_model_promotion": False,
        "can_generate_bet_recommendations": False,
        "production_recommendations": "DISABLED",
        "prespecified_high_confidence_threshold": THRESHOLD,
        "leagues": [],
    }
    if not isinstance(report, dict):
        return result
    if (report.get("schema") != HISTORICAL
            or report.get("evaluation_type") != "RETROSPECTIVE_DATE_ONLY_REPLAY"
            or report.get("live_point_in_time_forecasts_verified") is not False
            or report.get("betting_roi_estimable") is not False
            or report.get("market_baseline_available") is not False
            or report.get("automatic_model_promotion") is not False
            or report.get("production_recommendations") != "DISABLED"
            or not isinstance(report.get("by_league"), dict)
            or report.get("development_season") != "2024-25"
            or report.get("holdout_season") != "2025-26"):
        return result
    risk_count = 0
    for league, details in sorted(report["by_league"].items()):
        if not isinstance(league, str) or not isinstance(details, dict):
            continue
        dev = details.get("2024-25")
        hold = details.get("2025-26")
        a = (dev.get("statistics", {}) if isinstance(dev, dict) else {})
        b = (hold.get("statistics", {}) if isinstance(hold, dict) else {})
        development, holdout = fixed_bin(a), fixed_bin(b)
        if development is None or holdout is None:
            assessment = "INSUFFICIENT_REPLAY_EVIDENCE"
            delta = None
        else:
            delta = round(holdout["hit_rate"] - development["hit_rate"], 4)
            stable_sample = min(development["n"], holdout["n"]) >= MIN_HIGH_CONFIDENCE_SAMPLES
            stable_drift = abs(delta) <= MAX_SEASON_CHANGE
            # A chance of sub-50% accuracy still requires careful caution.
            lower_bound = holdout["wilson95"][0] >= .50
            assessment = ("SHADOW_MONITOR_ONLY"
                          if stable_sample and stable_drift and lower_bound
                          else "SHADOW_CAUTION")
            if assessment == "SHADOW_CAUTION":
                risk_count += 1
        metrics = b.get("original") if isinstance(b, dict) else None
        top_gap = (metrics.get("top_choice_calibration_gap")
                   if isinstance(metrics, dict) else None)
        result["leagues"].append({
            "league": league, "development_high_probability": development,
            "holdout_high_probability": holdout,
            "high_probability_hit_rate_year_over_year_change": delta,
            "all_match_holdout_top_choice_calibration_gap": (
                top_gap if valid_num(top_gap) else None),
            "assessment": assessment,
            "recommendation": "PAPER_SHADOW_ONLY_NOT_EXECUTABLE_BET",
            "real_time_market_edge_verified": False,
            "live_predictive_stability_proven": False,
        })
    result["status"] = "RESEARCH_ONLY" if result["leagues"] else "HOLD"
    result["reason"] = ("DATE_ONLY_OBSERVATIONAL_LEAGUE_DRIFT"
                        if result["leagues"] else "NO_LEAGUES_WITH_HOLDOUT_EVIDENCE")
    result["league_count"] = len(result["leagues"])
    result["caution_league_count"] = risk_count
    result["source_coverage_count"] = len(report.get("upstream_archives", []))
    return result


def publish(input_path, output_path):
    try:
        p = Path(input_path)
        if p.stat().st_size > 1_000_000:
            raise ValueError("OVERSIZE_REPORT")
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        data = None
    result = audit(data)
    Path(output_path).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"], "league_count": result.get("league_count", 0),
        "caution_league_count": result.get("caution_league_count", 0),
        "can_generate_bet_recommendations": False,
        "production_recommendations": "DISABLED",
    }, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="retrospective_backtest.json")
    parser.add_argument("--output", default="retrospective_stability.json")
    args = parser.parse_args()
    publish(args.input, args.output)
