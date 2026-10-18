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
    if not all(isinstance(x,str) and x.strip() and len(x)<=120
               for x in (league,home,away,event_id)) or home.strip().casefold()==away.strip().casefold():
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
    # A caller may request a specific market, but only provider-derived quotes
    # can satisfy that request. Never join totals/spreads/h2h implicitly.
    model=case.get("model") if isinstance(case.get("model"),dict) else {}
    requested_market=model.get("supported_market")
    market_matched=[q for q in matched if q["market"]==requested_market]
    # Optional exact selection constraints prevent a model for one outcome
    # or line from borrowing evidence from another outcome or line.
    if "requested_outcome" in model:
        market_matched=[q for q in market_matched
                        if q["outcome"]==model["requested_outcome"]]
    if "requested_point" in model:
        market_matched=[q for q in market_matched
                        if type(model["requested_point"]) in (int,float)
                        and type(q["point"]) in (int,float)
                        and q["point"]==model["requested_point"]]
    prematch_evidence=[q for q in market_matched if q["quote_eligible_as_prematch_evidence"]]
    # This snapshot has one capture clock and one fixture kickoff: eligible
    # pre-match observations cannot coexist with in-play capture observations.
    result_case=dict(case)
    selected_identity=None
    if market_matched:
        # Select freshest observed quote only for diagnostics. Never infer
        # execution availability or independent model calibration.
        # Prefer a qualifying pre-match observation; never let a later in-play
        # update override valid pre-match evidence in mixed snapshots.
        selection_pool=prematch_evidence if prematch_evidence else market_matched
        selected=max(selection_pool,key=lambda q:q["market_last_update_utc"])
        market={"event_id":event_id,"league":league,
                "market_key":selected["market"],
                "bookmaker_key":selected["bookmaker"],
                "outcome":selected["outcome"],
                "handicap_or_total_point":selected["point"],
                "decimal_odds_observed_not_executable":selected["decimal_odds"],
                "quote_market_identity":{
                    "event_id":selected["event_id"],
                    "bookmaker":selected["bookmaker"],
                    "market":selected["market"],
                    "outcome":selected["outcome"],
                    "point":selected["point"],
                    "market_last_update_utc":selected["market_last_update_utc"],
                },
                "last_update_utc":selected["market_last_update_utc"],
                "validated_by_market_quote_gate":bool(selected["quote_eligible_as_prematch_evidence"]),
                "bookmaker_quote_executable_verified":False}
        result_case["market"]=market
        selected_identity=market["quote_market_identity"]
    else:
        # Reject any market self-certification supplied in case JSON.
        result_case["market"]={}
    # All other case claims remain untrusted and cannot unlock approval.
    decision=evaluate(result_case,now=now)
    reason=("NO_MATCHING_VERIFIED_MARKET_QUOTES" if not matched
            else "NO_MATCHING_MODEL_MARKET_QUOTES" if not market_matched
            else "RESEARCH_ONLY_NO_EXECUTABLE_PRICE_OR_APPROVED_MODEL")
    return {"schema":SCHEMA,"status":"HOLD",
            "market_quote_audit":{k:v for k,v in audit.items() if k!="quotes"},
            "decision":decision,
            "matched_verified_quotes":len(matched),
            "matched_model_market_quotes":len(market_matched),
            "prematch_evidence_quotes":len(prematch_evidence),
            "prematch_evidence_available":bool(prematch_evidence),
            "selected_quote_identity":selected_identity,
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
