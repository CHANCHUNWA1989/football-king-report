"""研究資料輸入驗收：僅檢查格式、時間與來源宣告，不替代獨立核實。"""
from datetime import datetime, timezone
from shadow_1x2_scoring import stamp


def inspect(forecasts, results):
    if not isinstance(forecasts, list) or not isinstance(results, list):
        raise ValueError("INVALID_INPUT")
    errors = []
    if not forecasts:
        errors.append({"dataset": "forecasts", "row": None, "reason": "NO_FORECAST_DATA"})
    if not results:
        errors.append({"dataset": "results", "row": None, "reason": "NO_RESULT_DATA"})
    now = datetime.now(timezone.utc)
    for kind, records in (("forecasts", forecasts), ("results", results)):
        if len(records) > 100000:
            raise ValueError("TOO_MANY_RECORDS")
        seen_ids = set()
        for i, row in enumerate(records):
            if not isinstance(row, dict):
                errors.append({"dataset": kind, "row": i, "reason": "NOT_OBJECT"})
                continue
            if not isinstance(row.get("event_id"), str) or not row["event_id"].strip():
                errors.append({"dataset": kind, "row": i, "reason": "MISSING_EVENT_ID"})
            elif row["event_id"] in seen_ids:
                errors.append({"dataset": kind, "row": i, "reason": "DUPLICATE_EVENT_ID"})
            else:
                seen_ids.add(row["event_id"])
            if kind == "forecasts":
                # Bookmaker consensus is a baseline, not an independent model forecast.
                if row.get("probabilities_are_no_vig_consensus") is True or row.get("prediction_or_value_bet") is False:
                    errors.append({"dataset": kind, "row": i, "reason": "MARKET_CONSENSUS_NOT_MODEL_FORECAST"})
            fields = ("forecast_utc", "kickoff_utc") if kind == "forecasts" else ("settled_utc",)
            for field in fields:
                try:
                    dt = stamp(row[field])
                    if dt > now:
                        errors.append({"dataset": kind, "row": i, "reason": "FUTURE_" + field.upper()})
                except (KeyError, TypeError, ValueError, OverflowError):
                    errors.append({"dataset": kind, "row": i, "reason": "INVALID_" + field.upper()})
            if kind == "results":
                if row.get("status") != "FINAL":
                    errors.append({"dataset": kind, "row": i, "reason": "NOT_FINAL"})
                if row.get("independently_verified") is not True:
                    errors.append({"dataset": kind, "row": i, "reason": "NOT_VERIFIED"})
    return {"status": "HOLD" if errors else "RESEARCH_ONLY",
            "forecast_count": len(forecasts), "result_count": len(results),
            "errors": errors[:200], "error_count": len(errors),
            "production_recommendations": "DISABLED"}
