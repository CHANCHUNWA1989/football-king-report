"""Normalize current TheOddsAPI /odds/ and legacy v4-style research payloads.

No API requests, no key handling, no guessing timestamps or prices.
"""
import math
from datetime import datetime, timezone
from live_market_research import utc

SCHEMA="football-king-provider-schema-bridge-v1"

def _decimal(price, fmt):
    if type(price) not in (int,float) or not math.isfinite(price):
        raise ValueError("INVALID_ODDS_PRICE")
    if fmt=="decimal":
        result=float(price)
    elif fmt=="american":
        if -100<price<100:
            raise ValueError("INVALID_AMERICAN_ODDS")
        result=1+price/100 if price>0 else 1+100/abs(price)
    else:
        raise ValueError("UNKNOWN_ODDS_FORMAT")
    if not 1.01<=result<=100:
        raise ValueError("INVALID_DECIMAL_ODDS")
    return round(result,6)


def normalize(payload, *, sport_key, odds_format="american"):
    if odds_format not in ("american","decimal"):
        raise ValueError("UNKNOWN_ODDS_FORMAT")
    if not isinstance(sport_key,str) or not sport_key:
        raise ValueError("INVALID_SPORT_KEY")
    if isinstance(payload,dict):
        events=payload.get("data")
    else:
        events=payload
    if not isinstance(events,list) or len(events)>200:
        raise ValueError("INVALID_EVENTS_PAYLOAD")
    out=[]
    errors={}
    def error(reason):
        errors[reason]=errors.get(reason,0)+1
    for event in events:
        if not isinstance(event,dict):
            error("INVALID_EVENT")
            continue
        home=event.get("home_team")
        away=event.get("away_team")
        key=event.get("sport_key",event.get("sport",event.get("league")))
        if key!=sport_key:
            error("SPORT_KEY_MISMATCH")
            continue
        if not all(isinstance(x,str) and x for x in (home,away)):
            error("MISSING_TEAMS")
            continue
        event_id=event.get("id",event.get("event_id"))
        start=event.get("commence_time",event.get("start_time"))
        if not isinstance(event_id,str) or not event_id:
            error("MISSING_EVENT_ID")
            continue
        try:
            kickoff=utc(start).isoformat()
        except (ValueError,TypeError,OverflowError):
            error("INVALID_KICKOFF")
            continue
        if "books" in event:
            books=event.get("books")
            if not isinstance(books,list) or len(books)>60:
                error("INVALID_BOOKS")
                continue
            bybook={}
            for item in books:
                if not isinstance(item,dict):
                    error("INVALID_BOOK")
                    continue
                book=item.get("book")
                market=item.get("market")
                updated=item.get("updated_at")
                outcomes=item.get("outcomes")
                if not isinstance(book,str) or not book or market not in ("h2h","spreads","totals"):
                    error("INVALID_BOOK_MARKET")
                    continue
                try:
                    ts=utc(updated).isoformat()
                except (ValueError,TypeError,OverflowError):
                    error("MISSING_MARKET_CLOCK")
                    continue
                if not isinstance(outcomes,list) or len(outcomes)>40:
                    error("INVALID_OUTCOMES")
                    continue
                valid=[]
                for o in outcomes:
                    if not isinstance(o,dict):
                        error("INVALID_OUTCOME")
                        continue
                    try:
                        price=_decimal(o.get("price"),odds_format)
                    except ValueError:
                        error("INVALID_PRICE")
                        continue
                    valid.append({"name":o.get("name"),"price":price,
                                  **({"point":o["point"]} if "point" in o else {})})
                bybook.setdefault(book,[]).append(
                    {"key":market,"last_update":ts,"outcomes":valid})
            normalized_books=[{"key":book,"markets":markets}
                              for book,markets in bybook.items()]
        else:
            # Existing v4 format: preserve market-level timestamps and
            # convert explicitly specified prices without mutating input.
            books=event.get("bookmakers")
            if not isinstance(books,list) or len(books)>60:
                error("INVALID_BOOKMAKERS")
                continue
            normalized_books=[]
            for book in books:
                if not isinstance(book,dict) or not isinstance(book.get("key"),str):
                    error("INVALID_BOOKMAKER")
                    continue
                markets=book.get("markets")
                if not isinstance(markets,list) or len(markets)>30:
                    error("INVALID_MARKETS")
                    continue
                converted=[]
                for m in markets:
                    if not isinstance(m,dict) or m.get("key") not in ("h2h","spreads","totals"):
                        error("INVALID_MARKET")
                        continue
                    if not isinstance(m.get("outcomes"),list):
                        error("INVALID_OUTCOMES")
                        continue
                    values=[]
                    for o in m["outcomes"][:40]:
                        if not isinstance(o,dict):
                            error("INVALID_OUTCOME")
                            continue
                        try:
                            price=_decimal(o.get("price"),odds_format)
                        except ValueError:
                            error("INVALID_PRICE")
                            continue
                        values.append({**o,"price":price})
                    converted.append({"key":m["key"],"last_update":m.get("last_update"),
                                      "outcomes":values})
                normalized_books.append({"key":book["key"],"markets":converted})
        out.append({"id":event_id,"sport_key":sport_key,"home_team":home,
                    "away_team":away,"commence_time":kickoff,
                    "bookmakers":normalized_books})
    return {"schema":SCHEMA,"events":out,"rejections":errors,
            "events_normalized":len(out),"recommendation":None,
            "production_recommendations":"DISABLED"}
