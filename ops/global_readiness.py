"""Unified, fail-closed global coverage and positive-EV readiness report.

Combines independent existing collector outputs without upgrading any source's
trust or confusing observed fixtures with independently verified picks.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA="football-king-global-readiness-v1"
MIN_ODDS=1.80
MIN_CONSERVATIVE_EV=0.03

def report(global_data=None,wide_data=None,market_data=None,settlement_data=None,*,now=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    g=global_data if isinstance(global_data,dict) else {}
    w=wide_data if isinstance(wide_data,dict) else {}
    m=market_data if isinstance(market_data,dict) else {}
    s=settlement_data if isinstance(settlement_data,dict) else {}
    global_ok=(g.get("schema")=="football-king-global-fixture-discovery-v1"
               and g.get("production_recommendations")=="DISABLED"
               and g.get("qualifies_for_betting") is False)
    if global_ok:
        from global_fixture_discovery import verify
        try:
            verify(g)
        except (ValueError,TypeError,KeyError,OverflowError):
            global_ok=False
    fixtures=g.get("fixture_count",0) if global_ok else 0
    leagues=g.get("observed_competition_count",0) if global_ok else 0
    # Wide and market are displayed as separate independent coverage sources:
    # no union count without verified cross-provider league identifiers.
    wide_ok=(w.get("schema")=="football-king-wide-free-leagues-v1"
             and w.get("production_recommendations")=="DISABLED")
    market_ok=(m.get("production_recommendations")=="DISABLED"
               and isinstance(m.get("events"),list))
    # A boolean claim in a self-authored JSON cannot authenticate settlements.
    # Independent provenance needs external verification and a frozen audit.
    candidate_settled=s.get("candidate_forward_samples",0)
    if type(candidate_settled) is not int or candidate_settled<0:
        candidate_settled=0
    blockers=[]
    if not global_ok or not fixtures:
        blockers.append("NO_VALIDATED_GLOBAL_FIXTURE_COVERAGE")
    if not wide_ok:
        blockers.append("WIDE_SOURCE_AUDIT_MISSING")
    if not market_ok:
        blockers.append("MARKET_AUDIT_MISSING")
    blockers.extend(["NO_INDEPENDENTLY_AUTHENTICATED_SETTLEMENTS",
                     "NO_INDEPENDENTLY_CALIBRATED_LEAGUE_PROBABILITIES",
                     "NO_VERIFIED_EXECUTABLE_BOOKMAKER_PRICES",
                     "NO_VALIDATED_FORWARD_POSITIVE_EV"])
    return {
        "schema":SCHEMA,"as_of_utc":now.astimezone(timezone.utc).isoformat(),
        "status":"HOLD","global_discovery_validated":global_ok,
        "global_fixture_count":fixtures,"global_observed_competitions":leagues,
        "wide_audit_present":wide_ok,"market_audit_present":market_ok,
        "candidate_settlement_records":candidate_settled,
        "independently_authenticated_settlements":0,
        "minimum_decimal_odds":MIN_ODDS,
        "minimum_conservative_ev":MIN_CONSERVATIVE_EV,
        "recommendation_count":0,"recommendations":[],
        "production_recommendations":"DISABLED",
        "blockers":blockers,
        "global_coverage_claim":"OBSERVED_ONLY_NOT_ALL_WORLD_FIXTURES",
        "note":"Research coverage is not independently calibrated positive EV."
    }

def main():
    p=argparse.ArgumentParser()
    for name in ("global","wide","market","settlement"):
        p.add_argument("--"+name)
    p.add_argument("--output",default="global-readiness.json")
    args=p.parse_args()
    def read(path):
        if not path:
            return None
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError,ValueError):
            return None
    doc=report(read(getattr(args,'global')),read(args.wide),read(args.market),
               read(args.settlement))
    Path(args.output).write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n",
                                 encoding="utf-8")
    print(json.dumps({"status":doc["status"],"fixtures":doc["global_fixture_count"],
                      "competitions":doc["global_observed_competitions"],
                      "blockers":doc["blockers"]},ensure_ascii=False))
if __name__=="__main__":
    main()
