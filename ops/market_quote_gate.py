"""Validate externally obtained The Odds API market-level quotes; no API calls.

Do not infer current tradability, bookmaker independence or calibrated EV.
This is a zero-credit ingestion gate for any supported football league.
"""
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from live_market_research import utc, quarter_legs

SCHEMA="football-king-quote-freshness-v1"
MAX_EVENTS=200
MAX_BOOKS=60
MAX_AGE_SECONDS=120
ALLOWED_MARKETS={"h2h","totals","spreads"}


def _valid_id(value):
    return isinstance(value,str) and bool(value.strip()) and len(value)<=128


def _valid_price(value):
    try:
        return type(value) in (int,float) and math.isfinite(value) and 1.01<=value<=100
    except OverflowError:
        return False


def _outcome_scope(outcome, market, home, away):
    """Price-independent side identity and signed home-line group, or invalid.

    Preserve raw output values; quarter units only identify the group accepted
    by the existing line validator. Invalid/unhashable source data never enters
    a Counter and will receive the usual row-level rejection below.
    """
    if not isinstance(outcome,dict) or not isinstance(outcome.get("name"),str):
        return None
    name,point=outcome["name"],outcome.get("point")
    if market=="h2h":
        if name not in (home,away,"Draw") or point is not None:
            return None
        return (name,None),None
    if ((market=="totals" and name not in ("Over","Under"))
            or (market=="spreads" and name not in (home,away))):
        return None
    try:
        quarter_legs(point)
        units=int(round(point*4))
    except (ValueError,TypeError,OverflowError):
        return None
    line=units if market=="totals" or name==home else -units
    return (name,units),line


def extract(payload, *, captured_utc, league, home, away, max_age_seconds=MAX_AGE_SECONDS):
    captured=utc(captured_utc)
    if (not isinstance(league,str) or not league or
            not isinstance(home,str) or not isinstance(away,str) or
            home.casefold()==away.casefold()):
        raise ValueError("INVALID_FIXTURE_IDENTITY")
    if type(max_age_seconds) is not int or not 30<=max_age_seconds<=900:
        raise ValueError("INVALID_FRESHNESS_POLICY")
    if not isinstance(payload,list) or len(payload)>MAX_EVENTS:
        raise ValueError("INVALID_ODDS_EVENTS")
    report={"schema":SCHEMA,"captured_utc":captured.isoformat(),
            "league":league,"home":home,"away":away,
            "max_market_age_seconds":max_age_seconds,
            "matched_events":0,"quotes_accepted":0,
            "quotes_rejected":0,"reject_reasons":{},
            "quotes":[],"market_snapshot_research_only":True,
            "pre_match_quote_observations":0,
            "in_play_or_too_late_quote_observations":0,
            "quote_origin_does_not_prove_executability":True,
            "executable_bookmaker_price_verified":False,
            "independent_source_confirmed":False,
            "probability_model_calibrated_for_league":False,
            "recommendation":None,"production_recommendations":"DISABLED"}
    rejects=report["reject_reasons"]
    def reject(reason):
        report["quotes_rejected"]+=1
        rejects[reason]=rejects.get(reason,0)+1
    # Count the full native source scope before filtering or accepting a copy.
    event_counts=Counter(event.get("id") for event in payload
                         if isinstance(event,dict) and _valid_id(event.get("id")))
    for event in payload:
        if not isinstance(event,dict):
            reject("INVALID_EVENT")
            continue
        if (event.get("home_team")!=home or event.get("away_team")!=away):
            continue
        if event.get("sport_key")!=league:
            reject("WRONG_SPORT_KEY")
            continue
        # All copies of an ambiguous native identity are quarantined.
        event_id=event.get("id")
        if not _valid_id(event_id):
            reject("INVALID_EVENT_ID")
            continue
        if event_counts[event_id]!=1:
            reject("DUPLICATE_EVENT_ID")
            continue
        report["matched_events"]+=1
        try:
            kickoff=utc(event["commence_time"])
        except (KeyError,TypeError,ValueError,OverflowError):
            reject("INVALID_KICKOFF")
            continue
        books=event.get("bookmakers",[])
        if not isinstance(books,list) or len(books)>MAX_BOOKS:
            reject("INVALID_BOOKMAKERS")
            continue
        book_counts=Counter(book.get("key") for book in books
                            if isinstance(book,dict) and _valid_id(book.get("key")))
        for book in books:
            if not isinstance(book,dict) or not _valid_id(book.get("key")):
                reject("INVALID_BOOKMAKER")
                continue
            if book_counts[book["key"]]!=1:
                reject("DUPLICATE_BOOKMAKER")
                continue
            markets=book.get("markets",[])
            if not isinstance(markets,list) or len(markets)>30:
                reject("INVALID_MARKETS")
                continue
            market_counts=Counter(market.get("key") for market in markets
                                  if isinstance(market,dict) and isinstance(market.get("key"),str)
                                  and market["key"] in ALLOWED_MARKETS)
            for market in markets:
                if (not isinstance(market,dict)
                        or not isinstance(market.get("key"),str)
                        or market["key"] not in ALLOWED_MARKETS):
                    reject("UNSUPPORTED_MARKET")
                    continue
                if market_counts[market["key"]]!=1:
                    reject("DUPLICATE_MARKET")
                    continue
                # Critical: use market-level last_update, not deprecated book-level time.
                try:
                    updated=utc(market["last_update"])
                except (KeyError,ValueError,TypeError,OverflowError):
                    reject("MISSING_MARKET_LAST_UPDATE")
                    continue
                age=(captured-updated).total_seconds()
                if not -10<=age<=max_age_seconds:
                    reject("STALE_OR_FUTURE_MARKET")
                    continue
                outcomes=market.get("outcomes",[])
                if not isinstance(outcomes,list) or len(outcomes)>40:
                    reject("INVALID_OUTCOMES")
                    continue
                # A duplicate side poisons the whole corresponding line, even
                # if the duplicate's price is invalid. Never select first-wins
                # or clean an ambiguous raw block into an apparently full pair.
                scopes=[_outcome_scope(outcome,market["key"],home,away)
                        for outcome in outcomes]
                side_counts=Counter(scope[0] for scope in scopes if scope is not None)
                poisoned_lines={scope[1] for scope in scopes
                                if scope is not None and side_counts[scope[0]]>1}
                for outcome,scope in zip(outcomes,scopes):
                    if scope is not None and scope[1] in poisoned_lines:
                        reject("DUPLICATE_QUOTE")
                        continue
                    if not isinstance(outcome,dict):
                        reject("INVALID_OUTCOME")
                        continue
                    name=outcome.get("name")
                    price=outcome.get("price")
                    if (not isinstance(name,str) or not name or
                            not _valid_price(price)):
                        reject("INVALID_DECIMAL_PRICE")
                        continue
                    point=outcome.get("point")
                    if market["key"] in ("totals","spreads"):
                        try:
                            quarter_legs(point)
                        except (ValueError,TypeError,OverflowError):
                            reject("INVALID_ASIAN_POINT")
                            continue
                    elif point is not None:
                        reject("UNEXPECTED_H2H_POINT")
                        continue
                    if market["key"]=="totals" and name not in ("Over","Under"):
                        reject("INVALID_TOTALS_SIDE")
                        continue
                    if market["key"]=="spreads" and name not in (home,away):
                        reject("INVALID_SPREAD_SIDE")
                        continue
                    if market["key"]=="h2h" and name not in (home,away,"Draw"):
                        reject("INVALID_H2H_SIDE")
                        continue
                    pre_match=(kickoff-captured).total_seconds()>600
                    report["quotes"].append({
                        "quote_pre_match_at_capture":pre_match,
                        "market_phase_at_capture":(
                            "PREMATCH" if pre_match else "IN_PLAY_OR_TOO_LATE"),
                        "event_id":event_id,"bookmaker":book["key"],
                        "market":market["key"],"outcome":name,"point":point,
                        "decimal_odds":price,"market_last_update_utc":updated.isoformat(),
                        "age_seconds":round(age,2),
                        "kickoff_utc":kickoff.isoformat(),
                        "source":"the_odds_api_v4",
                        "status":"FRESH_OBSERVATION_NOT_EXECUTABLE",
                    })
    report["pre_match_quote_observations"]=sum(
        row["quote_pre_match_at_capture"] for row in report["quotes"])
    report["in_play_or_too_late_quote_observations"]=(
        len(report["quotes"])-report["pre_match_quote_observations"])
    report["quotes_accepted"]=len(report["quotes"])
    report["status"]="RESEARCH_ONLY" if report["quotes_accepted"] else "HOLD"
    return report


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",required=True)
    parser.add_argument("--captured-utc",required=True)
    parser.add_argument("--sport-key",required=True)
    parser.add_argument("--home",required=True)
    parser.add_argument("--away",required=True)
    parser.add_argument("--output",default="market-quote-audit.json")
    args=parser.parse_args(argv)
    payload=json.loads(Path(args.input).read_text(encoding="utf-8"))
    result=extract(payload,captured_utc=args.captured_utc,
                   league=args.sport_key,home=args.home,away=args.away)
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",
                                 encoding="utf-8")
    print(json.dumps({"status":result["status"],
                      "quotes_accepted":result["quotes_accepted"],
                      "quotes_rejected":result["quotes_rejected"],
                      "production_recommendations":"DISABLED"}))


if __name__=="__main__":
    main()
