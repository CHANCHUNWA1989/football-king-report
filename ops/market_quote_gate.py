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
    seen=set()
    # Reject every occurrence of an ambiguous fixture ID, including the
    # first. This prevents a conflicting payload order choosing the quote.
    event_counts={}
    for candidate in payload:
        if (isinstance(candidate,dict)
                and candidate.get("home_team")==home
                and candidate.get("away_team")==away
                and candidate.get("sport_key")==league
                and isinstance(candidate.get("id"),str)):
            key=candidate["id"]
            event_counts[key]=event_counts.get(key,0)+1
    for event in payload:
        if not isinstance(event,dict):
            reject("INVALID_EVENT")
            continue
        if (event.get("home_team")!=home or event.get("away_team")!=away):
            continue
        if event.get("sport_key")!=league:
            reject("WRONG_SPORT_KEY")
            continue
        # Ignore source events with no stable ID and duplicates that
        # would otherwise inflate the number of observed market quotes.
        event_id=event.get("id")
        if (not isinstance(event_id,str) or not event_id.strip()
                or len(event_id)>128):
            reject("INVALID_EVENT_ID")
            continue
        if event_counts[event_id]>1:
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
        # Duplicate bookmaker records can carry conflicting market updates.
        # Quarantine every occurrence rather than trusting payload order.
        book_counts={}
        for candidate in books:
            if isinstance(candidate,dict) and isinstance(candidate.get("key"),str):
                key=candidate["key"]
                book_counts[key]=book_counts.get(key,0)+1
        for book in books:
            if (not isinstance(book,dict) or not isinstance(book.get("key"),str)
                    or not book["key"].strip() or len(book["key"])>128):
                reject("INVALID_BOOKMAKER")
                continue
            if book_counts[book["key"]]>1:
                reject("DUPLICATE_BOOKMAKER_CONFLICT")
                continue
            markets=book.get("markets",[])
            if not isinstance(markets,list) or len(markets)>30:
                reject("INVALID_MARKETS")
                continue
            # A bookmaker may list several different markets, but repeated
            # instances of the same market are ambiguous even if timestamps differ.
            market_counts={}
            for candidate in markets:
                if isinstance(candidate,dict) and isinstance(candidate.get("key"),str):
                    key=candidate["key"]
                    market_counts[key]=market_counts.get(key,0)+1
            for market in markets:
                if (not isinstance(market,dict)
                        or not isinstance(market.get("key"),str)
                        or market["key"] not in ALLOWED_MARKETS):
                    reject("UNSUPPORTED_MARKET")
                    continue
                if market_counts[market["key"]]>1:
                    reject("DUPLICATE_MARKET_CONFLICT")
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
                # Repeated side+line entries can carry conflicting prices.
                # Quarantine all copies rather than choosing by input order.
                outcome_counts={}
                for candidate in outcomes:
                    if isinstance(candidate,dict):
                        identity=(candidate.get("name"),candidate.get("point"))
                        try:
                            outcome_counts[identity]=outcome_counts.get(identity,0)+1
                        except TypeError:
                            # Malformed unhashable values are rejected below.
                            pass
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
                    if outcome_counts.get((name,point),0)>1:
                        reject("DUPLICATE_OUTCOME_CONFLICT")
                        continue
                    key=(event_id,book["key"],market["key"],name,point)
                    if key in seen:
                        reject("DUPLICATE_QUOTE")
                        continue
                    seen.add(key)
                    pre_match=(kickoff-captured).total_seconds()>600
                    report["quotes"].append({
                        "quote_pre_match_at_capture":pre_match,
                        "quote_updated_before_kickoff":updated < kickoff,
                        "quote_updated_no_later_than_capture":updated <= captured,
                        "quote_eligible_as_prematch_evidence":(
                            pre_match and updated <= captured and updated < kickoff),
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
    # Research-only cross-bookmaker sanity check. Compare exact bet identities
    # only, with at least two other agreeing bookmaker observations.
    # This is not independent price verification or probability calibration.
    grouped={}
    for row in report["quotes"]:
        identity=(row["event_id"],row["market"],row["outcome"],row["point"])
        row["cross_bookmaker_price_outlier"]=False
        # In-play, post-kickoff or future-dated quotes cannot corroborate
        # a genuine pre-match price anomaly.
        if row["quote_eligible_as_prematch_evidence"]:
            grouped.setdefault(identity,[]).append(row)
    for rows in grouped.values():
        if len({row["bookmaker"] for row in rows})<3:
            continue
        for candidate in rows:
            candidate_time=utc(candidate["market_last_update_utc"])
            peer_rows=[row for row in rows
                       if row["bookmaker"]!=candidate["bookmaker"]
                       and abs((utc(row["market_last_update_utc"])
                                -candidate_time).total_seconds())<=30]
            # A distant timestamp from an unrelated bookmaker must not
            # suppress comparisons between three near-synchronous quotes.
            if len(peer_rows)<2:
                continue
            peers=sorted(row["decimal_odds"] for row in peer_rows)
            middle=len(peers)//2
            median=(peers[middle] if len(peers)%2
                    else (peers[middle-1]+peers[middle])/2)
            # The corroborating peer quotes must also agree in time.
            peer_times=[utc(row["market_last_update_utc"]) for row in peer_rows]
            if (max(peer_times)-min(peer_times)).total_seconds()>30:
                continue
            if (max(peers)-min(peers)<=median*0.15
                    and (candidate["decimal_odds"]>median*1.5
                         or candidate["decimal_odds"]<median/1.5)):
                candidate["cross_bookmaker_price_outlier"]=True
                candidate["quote_eligible_as_prematch_evidence"]=False
    report["cross_bookmaker_price_outliers"]=sum(
        row["cross_bookmaker_price_outlier"] for row in report["quotes"])
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
