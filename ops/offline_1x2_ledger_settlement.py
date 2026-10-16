"""Match saved football 1X2 forecasts with separately supplied settled results.

Offline research only. Original forecast records are never overwritten.
"""
import csv
import json
import tempfile
from pathlib import Path
from ops.offline_1x2_csv import review_csv

def settle_ledger(ledger_path, results_path):
    with Path(ledger_path).open(encoding="utf-8") as source:
        forecasts=[json.loads(line) for line in source if line.strip()]
    if not forecasts:
        raise ValueError("No recorded forecasts")
    with Path(results_path).open(encoding="utf-8",newline="") as source:
        reader=csv.DictReader(source)
        if reader.fieldnames!=["event_id","settled_at","outcome"]:
            raise ValueError("Unexpected results CSV columns")
        results=list(reader)
    by_id={}
    for result in results:
        event_id=result["event_id"]
        if not event_id or event_id in by_id:
            raise ValueError("Invalid or duplicate result ID")
        by_id[event_id]=result
    matched=[]
    seen=set()
    for forecast in forecasts:
        event_id=forecast["event_id"]
        if event_id in seen:
            raise ValueError("Duplicate forecast ID")
        seen.add(event_id)
        if event_id not in by_id:
            continue
        result=by_id[event_id]
        matched.append({"event_id":event_id,
            "forecast_at":forecast["forecast_at"],
            "kickoff_at":forecast["kickoff_at"],
            "settled_at":result["settled_at"],
            "home_prob":forecast["probabilities"]["H"],
            "draw_prob":forecast["probabilities"]["D"],
            "away_prob":forecast["probabilities"]["A"],
            "outcome":result["outcome"]})
    if not matched:
        raise ValueError("No matched settled forecasts")
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/"review.csv"
        with path.open("w",newline="",encoding="utf-8") as output:
            writer=csv.DictWriter(output,fieldnames=["event_id","forecast_at",
                "kickoff_at","settled_at","home_prob","draw_prob","away_prob","outcome"])
            writer.writeheader()
            writer.writerows(matched)
        score=review_csv(path)
    return {"mode":"research","recorded_count":len(forecasts),
            "settled_count":len(matched),
            "unsettled_count":len(forecasts)-len(matched),
            "score":score,"real_betting_enabled":False}
