"""Strict CSV adapter for settled 1X2 forecasts. Offline, no odds API usage."""
import csv
from datetime import datetime, timezone
from ops.offline_1x2_validation import evaluate_1x2

def _utc(value):
    dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timezone required")
    return dt.astimezone(timezone.utc)

def review_csv(path):
    rows=[]
    columns=["event_id","forecast_at","kickoff_at","settled_at",
             "home_prob","draw_prob","away_prob","outcome"]
    with open(path,newline="",encoding="utf-8-sig") as handle:
        reader=csv.DictReader(handle)
        if reader.fieldnames!=columns:
            raise ValueError("Unexpected CSV schema")
        for row in reader:
            if len(rows)>=100000 or None in row or any(v is None or v=="" for v in row.values()):
                raise ValueError("Invalid or oversized CSV")
            if not _utc(row["forecast_at"]) < _utc(row["kickoff_at"]) < _utc(row["settled_at"]):
                raise ValueError("Forecast must precede kickoff and settlement")
            rows.append({"event_id":row["event_id"],
                         "probabilities":{"H":float(row["home_prob"]),
                                          "D":float(row["draw_prob"]),
                                          "A":float(row["away_prob"])},
                         "outcome":row["outcome"]})
    return evaluate_1x2(rows)
