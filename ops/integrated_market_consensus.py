"""One-call verified odds, independent bookmaker consensus and safety decision.

Offline audit; never asserts executable quotes or validated model EV.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from market_consensus import analyze as consensus
from verified_market_pipeline import analyze as pipeline

SCHEMA="football-king-integrated-market-consensus-v1"


def analyze(case, odds_events, *, now=None, min_bookmakers=2):
    if not isinstance(case,dict):
        raise ValueError("INVALID_CASE")
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    p=pipeline(case,odds_events,now=now)
    c=consensus({"quotes":p["research_quotes"]},min_bookmakers=min_bookmakers)
    fixture=case.get("fixture")
    fixture=fixture if isinstance(fixture,dict) else {}
    event_id=fixture.get("event_id")
    # Consensus must use only the quote lines matched by the exact event ID.
    rows=[x for x in c["groups"] if x["event_id"]==event_id]
    return {"schema":SCHEMA,"status":"HOLD",
            "fixture_event_id":event_id if isinstance(event_id,str) else None,
            "market_audit":p["market_quote_audit"],
            "research_quotes":p["research_quotes"],
            "consensus_groups":rows,
            "research_consensus_groups":sum(
                x["consensus_status"]=="RESEARCH_CONSENSUS" for x in rows),
            "decision":p["decision"],
            "blockers":p["decision"]["blockers"],
            "recommendation":None,
            "production_recommendations":"DISABLED",
            "can_execute_bet":False,
            "independent_source_confirmed":False}


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--case",required=True)
    parser.add_argument("--odds",required=True)
    parser.add_argument("--output",default="integrated-market-consensus.json")
    args=parser.parse_args(argv)
    case=json.loads(Path(args.case).read_text(encoding="utf-8"))
    odds=json.loads(Path(args.odds).read_text(encoding="utf-8"))
    result=analyze(case,odds)
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],
                      "consensus_groups":result["research_consensus_groups"],
                      "blockers":result["blockers"]},ensure_ascii=False))


if __name__=="__main__":
    main()
