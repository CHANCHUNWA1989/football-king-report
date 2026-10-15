"""研究模式：配對賽前封存預測與獨立賽後賽果，缺證據一律排除。"""
import argparse
import json
from pathlib import Path

from shadow_1x2_scoring import score, stamp


def reconcile(forecasts, results):
    if not isinstance(forecasts, list) or not isinstance(results, list):
        raise ValueError("INVALID_INPUT")
    result_by_id = {}
    duplicate_results = set()
    for item in results:
        if not isinstance(item, dict) or not isinstance(item.get("event_id"), str):
            continue
        key = item["event_id"]
        if key in result_by_id:
            duplicate_results.add(key)
        result_by_id[key] = item

    forecast_counts = {}
    for item in forecasts:
        if isinstance(item, dict) and isinstance(item.get("event_id"), str):
            key = item["event_id"]
            forecast_counts[key] = forecast_counts.get(key, 0) + 1

    rows = []
    reasons = {}
    def reject(reason):
        reasons[reason] = reasons.get(reason, 0) + 1

    for item in forecasts:
        if not isinstance(item, dict):
            reject("INVALID_FORECAST")
            continue
        key = item.get("event_id")
        if not isinstance(key, str) or not key.strip():
            reject("INVALID_EVENT_ID")
            continue
        if item.get("probabilities_are_no_vig_consensus") is True or item.get("prediction_or_value_bet") is False:
            reject("MARKET_CONSENSUS_NOT_MODEL_FORECAST")
            continue
        if forecast_counts.get(key) != 1:
            reject("DUPLICATE_FORECAST")
            continue
        if key in duplicate_results:
            reject("DUPLICATE_RESULT")
            continue
        result = result_by_id.get(key)
        if result is None:
            reject("NO_INDEPENDENT_RESULT")
            continue
        if result.get("independently_verified") is not True:
            reject("UNVERIFIED_RESULT")
            continue
        if not isinstance(result.get("source"), str) or not result["source"].strip():
            reject("MISSING_RESULT_SOURCE")
            continue
        if not isinstance(item.get("source"), str) or not item["source"].strip():
            reject("MISSING_FORECAST_SOURCE")
            continue
        # Reject explicitly identical forecast and settlement provenance.
        # This is a minimum separation check, NOT an external source audit.
        forecast_source = item.get("source")
        result_source = result.get("source")
        if isinstance(forecast_source, str) and forecast_source.strip() and (
            forecast_source.strip().casefold() == result_source.strip().casefold()
        ):
            reject("SAME_FORECAST_AND_RESULT_SOURCE")
            continue
        if result.get("status") != "FINAL":
            reject("NOT_FINAL_RESULT")
            continue
        if result.get("result") not in ("H", "D", "A"):
            reject("INVALID_RESULT")
            continue
        try:
            forecast_at = stamp(item["forecast_utc"])
            kickoff_at = stamp(item["kickoff_utc"])
            settled_at = stamp(result["settled_utc"])
            if not forecast_at < kickoff_at < settled_at:
                raise ValueError("TIME_LEAKAGE")
            if "kickoff_utc" in result and stamp(result["kickoff_utc"]) != kickoff_at:
                raise ValueError("KICKOFF_MISMATCH")
        except (KeyError, ValueError, TypeError, OverflowError):
            reject("INVALID_TIME_OR_KICKOFF")
            continue
        rows.append({**item, "settled_utc": result["settled_utc"],
                     "result": result["result"]})

    report = score(rows)
    report["matched_candidates"] = len(rows)
    report["unmatched_or_unverified"] = len(forecasts) - len(rows)
    report["reconciliation_reject_reasons"] = dict(sorted(reasons.items()))
    report["independent_result_proof"] = "DECLARED_NOT_AUDITED"
    report["production_recommendations"] = "DISABLED"
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--forecasts", required=True)
    p.add_argument("--results", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    forecasts = json.loads(Path(args.forecasts).read_text(encoding="utf-8"))
    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    report = reconcile(forecasts, results)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "accepted": report["accepted"],
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
