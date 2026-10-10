"""Audited 2025 J1 history and historical date-cutoff model feasibility.

Japan changed from a calendar-year league to an August-June competition for
2026/27, after a February-June transitional tournament. Only J1 2025
FINISHED match results are studied. Do NOT silently stitch transitional cup
results or 2026/27 fixtures to the old 2025 league model training set.

The retrospective replay uses artificial timestamps as a scoring adapter
only. It does not validate real pre-match prediction timestamps, outcome
updates, prices, EV, or actionable Japanese betting recommendations.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler

from retrospective_backtest import parse_archive, replay, evaluate_cohort

SCHEMA = "football-king-japan-j1-2025-audit-v1"
SOURCE = "https://raw.githubusercontent.com/openfootball/football.json/master/2025/jp.1.json"
MAX_SOURCE = 200_000
MIN_FINISHED_FOR_DIAGNOSTIC = 100
OFFICIAL_COMPETITION_SOURCE = "https://www.jleague.jp/en/j1/match/"
PRODUCTION = "DISABLED"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("UNEXPECTED_JLEAGUE_SOURCE_REDIRECT")


def retrieve():
    request = Request(SOURCE, headers={
        "Accept": "application/json",
        "User-Agent": "FootballKingJapanJ1SourceAudit/1.0"})
    with build_opener(NoRedirect()).open(request, timeout=12) as response:
        blob = response.read(MAX_SOURCE + 1)
    if len(blob) > MAX_SOURCE:
        raise ValueError("OVERSIZE_JLEAGUE_HISTORY_FILE")
    return json.loads(blob.decode("utf-8")), hashlib.sha256(blob).hexdigest()


def evaluate(doc, source_hash):
    report = {
        "schema": SCHEMA,
        "status": "HOLD",
        "reason": "J1_NOT_SUFFICIENTLY_VERIFIED_FOR_RECOMMENDATIONS",
        "source_name": "OpenFootball Japanese J1 calendar-year archive",
        "source_url": SOURCE,
        "upstream_sha256": source_hash,
        "calendar_year_archived": 2025,
        "official_current_season": "2026-27",
        "current_season_starts": "2026-08-07",
        "transition_tournament_not_merged": True,
        "current_season_live_results_available_from_this_archive": False,
        "source_contains_authentic_asof_forecast_snapshots": False,
        "replay_adapter_kickoff_is_not_real": True,
        "training_result_verification_independent": False,
        "licensed_live_1x2_prices_available": False,
        "market_comparison_available": False,
        "model_calibrated_for_2026_27": False,
        "forward_betting_win_rate_verified": False,
        "betting_roi_estimate": None,
        "bet_recommendation_count": 0,
        "production_recommendations": PRODUCTION,
        "official_fixture_reference": OFFICIAL_COMPETITION_SOURCE,
    }
    if (not isinstance(source_hash, str) or len(source_hash) != 64
            or not all(char in "0123456789abcdef" for char in source_hash)):
        report["reason"] = "INVALID_HISTORY_SOURCE_HASH"
        return report
    if (not isinstance(doc, dict) or not isinstance(doc.get("matches"), list)
            or len(doc["matches"]) > 650):
        report["reason"] = "INVALID_J1_HISTORICAL_SOURCE"
        return report
    report["source_schedule_rows"] = len(doc["matches"])
    try:
        finished, exclusions = parse_archive(doc)
    except (ValueError, TypeError, KeyError) as exc:
        report["reason"] = "J1_HISTORY_TOO_INCOMPLETE_" + type(exc).__name__
        return report
    if any(not (row["date"].year == 2025) for row in finished):
        report["reason"] = "FOREIGN_SEASON_IN_J1_TRAINING_DATA"
        return report
    report["finished_score_rows"] = len(finished)
    report["missing_or_invalid_score_rows"] = exclusions.get(
        "no_finished_result", 0)
    report["finished_score_coverage"] = round(
        len(finished) / len(doc["matches"]), 4) if doc["matches"] else 0.0
    if len(finished) < MIN_FINISHED_FOR_DIAGNOSTIC:
        report["reason"] = "INSUFFICIENT_FINISHED_J1_DATA"
        return report
    cases, dropped = replay(finished, "japan_j1", "2025")
    report["retrospective_evaluated_predictions"] = len(cases)
    report["replay_exclusions"] = dropped
    report["retrospective_2025_metrics"] = evaluate_cohort(cases)
    report["model_pretrained_on_previous_calendar_year"] = False
    report["development_and_untouched_holdout_seasons_available"] = False
    report["historical_draw_rate"] = (
        report["retrospective_2025_metrics"]["original"].get("observed_draw_fraction")
        if cases else None)
    report["historical_replay_is_not_out_of_sample_next_season"] = True
    report["status"] = "RESEARCH_ONLY" if cases else "HOLD"
    report["reason"] = ("PARTIAL_2025_DATE_ONLY_REPLAY_NOT_2026_27_VALIDATION"
                        if cases else "NO_QUALIFIED_DATE_ONLY_J1_PREDICTIONS")
    return report


def publish(out):
    result = None
    error = None
    try:
        doc, source_hash = retrieve()
        result = evaluate(doc, source_hash)
    except (OSError, ValueError, TimeoutError, UnicodeError, TypeError) as exc:
        error = type(exc).__name__
    if result is None:
        result = evaluate(None, "0" * 64)
        result["reason"] = "J1_HISTORY_FETCH_FAILED"
        result["source_fetch_failure"] = error
    result["audit_collected_utc"] = datetime.now(timezone.utc).isoformat()
    dest = Path(out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "2025_completed_scores": result.get("finished_score_rows", 0),
        "2025_total_schedule_rows": result.get("source_schedule_rows", 0),
        "date_only_replayed": result.get("retrospective_evaluated_predictions", 0),
        "historical_model_accuracy": (
            ((result.get("retrospective_2025_metrics") or {}).get("original") or {})
            .get("hit_rate")),
        "real_2026_27_recommendations": 0,
        "production_recommendations": PRODUCTION,
    }, ensure_ascii=False))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="jleague_j1_research.json")
    args = p.parse_args()
    publish(args.output)
