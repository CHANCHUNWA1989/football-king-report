"""Normalize real provider schema before validated match and consensus analysis."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from provider_schema_bridge import normalize
from integrated_market_consensus import analyze as integrated

SCHEMA="football-king-provider-ingestion-v1"


def analyze(case, payload, *, odds_format="american", now=None):
    if not isinstance(case,dict):
        raise ValueError("INVALID_CASE")
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    fixture=case.get("fixture")
    sport=fixture.get("league") if isinstance(fixture,dict) else None
    if not isinstance(sport,str) or not sport:
        return {"schema":SCHEMA,"status":"HOLD",
                "reason":"MISSING_SPORT_KEY","normalized_events":0,
                "production_recommendations":"DISABLED"}
    normalized=normalize(payload,sport_key=sport,odds_format=odds_format)
    result=integrated(case,normalized["events"],now=now)
    return {"schema":SCHEMA,"status":"HOLD",
            "provider_normalization":{"events_normalized":normalized["events_normalized"],
                                      "rejections":normalized["rejections"]},
            "analysis":result,"production_recommendations":"DISABLED",
            "recommendation":None}


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--case",required=True)
    p.add_argument("--odds",required=True)
    p.add_argument("--odds-format",choices=("american","decimal"),default="american")
    p.add_argument("--output",default="provider-ingestion.json")
    a=p.parse_args(argv)
    result=analyze(json.loads(Path(a.case).read_text(encoding="utf-8")),
                   json.loads(Path(a.odds).read_text(encoding="utf-8")),
                   odds_format=a.odds_format)
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",
                              encoding="utf-8")
    print(json.dumps({"status":result["status"],"production_recommendations":"DISABLED"}))


if __name__=="__main__":
    main()
