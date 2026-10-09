"""Validate externally obtained The Odds API market-level quotes; no API calls.

Do not infer current tradability, bookmaker independence or calibrated EV.
This is a zero-credit ingestion gate for any supported football league.
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from live_market_research import utc, quarter_legs

SCHEMA="football-king-quote-freshness-v1"
MAX_EVENTS=200
MAX_BOOKS=60
MAX_AGE_SECONDS=120
ALLOWED_MARKETS={"h2h","totals","spreads"}


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
            "executable_bookmaker_price_verified":False,
            "independent_source_confirmed":False,
            "probability_model_calibrated_for_league":False,
            "recommendation":None,"production_recommendations":"DISABLED"}
    rejects=report["reject_reasons"]
    def reject(reason):
        report["quotes_rejected"]+=1
        rejects[reason]=rejects.get(reason,0)+1
    seen=set()
    for event in payload:
        if not isinstance(event,dict):
            reject("INVALID_EVENT")
            continue
        if (event.get("home_team")!=home or event.get("away_team")!=away):
            continue
        if event.get("sport_key")!=league:
            reject("WRONG_SPORT_KEY")
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
        for book in books:
            if not isinstance(book,dict) or not isinstance(book.get("key"),str):
                reject("INVALID_BOOKMAKER")
                continue
            markets=book.get("markets",[])
            if not isinstance(markets,list) or len(markets)>30:
                reject("INVALID_MARKETS")
                continue
            for market in markets:
                if not isinstance(market,dict) or market.get("key") not in ALLOWED_MARKETS:
                    reject("UNSUPPORTED_MARKET")
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
                for outcome in outcomes:
                    if not isinstance(outcome,dict):
                        reject("INVALID_OUTCOME")
                        continue
                    name=outcome.get("name")
                    price=outcome.get("price")
                    if (not isinstance(name,str) or not name or
                            type(price) not in (int,float) or not math.isfinite(price)
                            or not 1.01<=price<=100):
                        reject("INVALID_DECIMAL_PRICE")
                        continue
                    point=outcome.get("point")
                    if market["key"] in ("totals","spreads"):
                        try:
                            quarter_legs(point)
                        except (ValueError,TypeError):
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
                    key=(event.get("id"),book["key"],market["key"],name,point)
                    if key in seen:
                        reject("DUPLICATE_QUOTE")
                        continue
                    seen.add(key)
                    report["quotes"].append({
                        "event_id":event.get("id"),"bookmaker":book["key"],
                        "market":market["key"],"outcome":name,"point":point,
                        "decimal_odds":price,"market_last_update_utc":updated.isoformat(),
                        "age_seconds":round(age,2),
                        "kickoff_utc":kickoff.isoformat(),
                        "source":"the_odds_api_v4",
                        "status":"FRESH_OBSERVATION_NOT_EXECUTABLE",
                    })
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
