"""Connect actual validated odds snapshots to unified match safety diagnostics.

Consumes a The Odds API v4 JSON payload and a screenshot/fixture case JSON.
No remote calls, no fake odds, no automatic bet recommendation.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from market_quote_gate import extract
from unified_match_gate import evaluate
from live_market_research import utc

SCHEMA="football-king-verified-market-pipeline-v1"


def analyze(case, odds_events, *, now=None):
    if not isinstance(case,dict):
        raise ValueError("INVALID_CASE")
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    fixture=case.get("fixture")
    if not isinstance(fixture,dict):
        fixture={}
    league=fixture.get("league")
    home=fixture.get("home")
    away=fixture.get("away")
    event_id=fixture.get("event_id")
    if not all(isinstance(x,str) and x.strip() for x in (league,home,away,event_id)):
        # Do not query or attribute a quote to an unidentified screenshot.
        decision=evaluate(case,now=now)
        return {"schema":SCHEMA,"status":"HOLD","market_quote_audit":None,
                "decision":decision,"matched_verified_quotes":0,
                "research_quotes":[],"reason":"UNVERIFIED_FIXTURE_ID",
                "production_recommendations":"DISABLED"}
    audit=extract(odds_events,captured_utc=now.isoformat(),
                  league=league,home=home,away=away)
    # The market gate verifies sport/team identity but its event id may
    # originate in another namespace. Require the exact same trusted id;
    # never silently equate unrelated providers' fixture ids.
    matched=[q for q in audit["quotes"] if q["event_id"]==event_id]
    result_case=dict(case)
    if matched:
        # Select freshest validated quote only for diagnostics. Never infer
        # execution availability or independent model calibration.
        selected=max(matched,key=lambda q:q["market_last_update_utc"])
        market={"event_id":event_id,"league":league,
                "market_key":selected["market"],
                "last_update_utc":selected["market_last_update_utc"],
                "validated_by_market_quote_gate":True,
                "bookmaker_quote_executable_verified":False}
        result_case["market"]=market
    else:
        # Reject any market self-certification supplied in case JSON.
        result_case["market"]={}
    # All other case claims remain untrusted and cannot unlock approval.
    decision=evaluate(result_case,now=now)
    reason=("NO_MATCHING_VERIFIED_MARKET_QUOTES" if not matched
            else "RESEARCH_ONLY_NO_EXECUTABLE_PRICE_OR_APPROVED_MODEL")
    return {"schema":SCHEMA,"status":"HOLD",
            "market_quote_audit":{k:v for k,v in audit.items() if k!="quotes"},
            "decision":decision,
            "matched_verified_quotes":len(matched),
            "research_quotes":matched,
            "reason":reason,"production_recommendations":"DISABLED"}


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--case",required=True,help="Fixture and screenshot evidence JSON")
    p.add_argument("--odds",required=True,help="The Odds API v4 events JSON")
    p.add_argument("--output",default="verified-market-pipeline.json")
    args=p.parse_args(argv)
    case=json.loads(Path(args.case).read_text(encoding="utf-8"))
    odds=json.loads(Path(args.odds).read_text(encoding="utf-8"))
    result=analyze(case,odds)
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],
                      "matched_verified_quotes":result["matched_verified_quotes"],
                      "reason":result["reason"],
                      "blockers":result["decision"]["blockers"]},ensure_ascii=False))


if __name__=="__main__":
    main()
