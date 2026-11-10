"""Connect actual validated odds snapshots to unified match safety diagnostics.

Consumes a The Odds API v4 JSON payload and a screenshot/fixture case JSON.
No remote calls, no fake odds, no automatic bet recommendation.
"""
import argparse
import json
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

from market_quote_gate import extract
from unified_match_gate import evaluate
from live_market_research import utc

SCHEMA="football-king-verified-market-pipeline-v1"


def _complete_prematch_groups(matched, *, home, away, now):
    """Only complete same-bookmaker/market/line/timestamp groups may validate.

    Quote presence alone is NOT a complete opposing-side market. This is a
    research-only *structural* check, not proof of source independence, live
    executability, or calibrated EV. The underlying extractor already rejects
    ambiguous duplicate side/line scopes.
    """
    groups = defaultdict(list)
    for q in matched:
        if q.get("quote_pre_match_at_capture") is not True:
            continue
        try:
            # No provider last_update can post-date this collection, even when
            # generic market_quote_gate tolerates a small vendor clock skew.
            if utc(q["market_last_update_utc"]) > now:
                continue
            market = q["market"]
            side = q["outcome"]
            units = int(round(q["point"] * 4)) if market in ("spreads", "totals") else None
            signed_home_line = (-units if side == away else units
                                ) if market == "spreads" else units
            scope = (q["event_id"], q["bookmaker"], market,
                     signed_home_line, q["market_last_update_utc"], q["kickoff_utc"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        groups[scope].append(q)
    complete = []
    for scope, quotes in groups.items():
        market = scope[2]
        required = ({"h2h": {home, "Draw", away},
                     "totals": {"Over", "Under"},
                     "spreads": {home, away}}).get(market)
        if (required is None or len(quotes) != len(required)
                or {q["outcome"] for q in quotes} != required):
            continue
        # Both opposite sides must carry equal totals or inverse handicap.
        if market in ("spreads", "totals"):
            points = {q["outcome"]: int(round(q["point"] * 4)) for q in quotes}
            if market == "totals" and points["Over"] != points["Under"]:
                continue
            if market == "spreads" and points[home] != -points[away]:
                continue
        complete.append(quotes)
    return complete



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
    # A supplied scheduled kickoff is part of the requested fixture identity.
    # Absence retains the legacy research path; invalid explicit values must
    # never silently downgrade to that path. Matching is not actual-KO proof.
    kickoff_binding="NOT_PROVIDED_LEGACY_RESEARCH_ONLY"
    fixture_kickoff=None
    if "kickoff_utc" in fixture:
        try:
            fixture_kickoff=utc(fixture["kickoff_utc"])
        except (ValueError,TypeError,OverflowError):
            kickoff_binding="INVALID"
        else:
            kickoff_binding="NO_MATCHING_QUOTES"
    if not all(isinstance(x,str) and x.strip() for x in (league,home,away,event_id)):
        # Do not query or attribute a quote to an unidentified screenshot.
        result_case=dict(case)
        result_case["market"]={}
        decision=evaluate(result_case,now=now)
        return {"schema":SCHEMA,"status":"HOLD","market_quote_audit":None,
                "decision":decision,"matched_verified_quotes":0,
                "complete_atomic_prematch_groups":0,
                "complete_requested_market_groups":0,
                "same_bookmaker_side_pairing_required":True,
                "structural_grouping_does_not_prove_execution":True,
                "research_quotes":[],"reason":"UNVERIFIED_FIXTURE_ID",
                "fixture_kickoff_binding":kickoff_binding,
                "production_recommendations":"DISABLED"}
    audit=extract(odds_events,captured_utc=now.isoformat(),
                  league=league,home=home,away=away)
    # The market gate verifies sport/team identity but its event id may
    # originate in another namespace. Require the exact same trusted id;
    # never silently equate unrelated providers' fixture ids.
    matched=[q for q in audit["quotes"]
             if kickoff_binding!="INVALID" and q["event_id"]==event_id
             and (fixture_kickoff is None or utc(q["kickoff_utc"])==fixture_kickoff)]
    if fixture_kickoff is not None and matched:
        kickoff_binding="MATCHED"
    # A supplied exact kickoff is mandatory for the *complete* market gate;
    # legacy research rows without it remain visible but never self-certify.
    # Screenshot minute/score claims indicating a live game also cannot be
    # silently combined with an allegedly pre-match market.
    screenshot = case.get("screenshot")
    screenshot = screenshot if isinstance(screenshot, dict) else {}
    appears_live = (
        type(screenshot.get("minute")) in (int, float)
        and screenshot["minute"] > 0
    ) or (
        type(screenshot.get("home_goals")) is int
        and type(screenshot.get("away_goals")) is int
        and (screenshot["home_goals"] > 0 or screenshot["away_goals"] > 0)
    )
    complete = (
        _complete_prematch_groups(matched, home=home, away=away, now=now)
        if kickoff_binding == "MATCHED" and not appears_live else []
    )
    result_case=dict(case)
    if complete:
        # Select a COMPLETE atomic bookmaker group, never a single surviving
        # side or quotes assembled across vendors, timestamps, or lines.
        # If a model specifies a market, do not silently substitute another.
        model = case.get("model")
        requested_market = model.get("supported_market") if isinstance(model, dict) else None
        same_market = [group for group in complete if group[0]["market"] == requested_market]
        chosen = same_market if requested_market else complete
        if not chosen:
            chosen = []  # Requested model market not represented by complete quotes.
    else:
        chosen = []
    if chosen:
        selected=max((q for group in chosen for q in group),
                     key=lambda q:q["market_last_update_utc"])
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
            else "NO_ATOMIC_PREMATCH_LINE_WITH_BOUND_KICKOFF" if not chosen
            else "RESEARCH_ONLY_NO_EXECUTABLE_PRICE_OR_APPROVED_MODEL")
    return {"schema":SCHEMA,"status":"HOLD",
            "market_quote_audit":{k:v for k,v in audit.items() if k!="quotes"},
            "decision":decision,
            "matched_verified_quotes":len(matched),
            "complete_atomic_prematch_groups":len(complete),
            "complete_requested_market_groups":len(chosen),
            "same_bookmaker_side_pairing_required":True,
            "structural_grouping_does_not_prove_execution":True,
            "fixture_kickoff_binding":kickoff_binding,
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
