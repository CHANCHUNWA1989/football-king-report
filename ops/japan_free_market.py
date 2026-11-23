"""J1 free API SIDE-CAR: PropLine, TheRundown and existing The Odds API.

One bounded prematch observation per enabled provider. Extract only derived
coverage statistics and book-median no-vig PROBABILITY for cross-feed QA.
Neither raw odds nor bookmaker names nor commercial datasets are published,
stored in git, or made available to the Pages dashboard. Matching API names
are NOT independent bookmakers. Free delayed quotes are NOT live/executable.
Missing secrets, paid-tier responses, stale data and malformed timestamps HOLD.
No model predictions, betting recommendations, stakes, EV or ROI are created.
"""
import argparse
import json
import math
import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from odds_market import book_probabilities, may_spend, retrieve as odds_retrieve, APIProblem
from asian_handicap_research import quarter_units
from team_identity import team_id

SCHEMA = "football-king-japan-free-market-research-v1"
SPORT = "soccer_japan_j_league"
RUNDOWN_ID = 19
MAX_BLOB = 1_700_000
MAX_EVENTS = 120
MAX_BOOKS = 80
MAX_AGE = timedelta(minutes=20)
PREMATCH_BUFFER = timedelta(minutes=10)
FUTURE_WINDOW = timedelta(days=14)
PROPLINE_URL = "https://api.prop-line.com/v1/sports/" + SPORT + "/odds?markets=h2h,spreads,totals&bookmakers=pinnacle,bovada,fanduel,draftkings"
RUNDOWN_DATES_URL = "https://therundown.io/api/v2/sports/dates?sport_ids=19&format=epoch&exclude_canceled=true"
RUNDOWN_EVENT_PREFIX = "https://therundown.io/api/v2/sports/19/events/"
THE_ODDS_SPORTS = "/sports/"
THE_ODDS_J1 = "/sports/" + SPORT + "/odds/"
MAX_THE_ODDS_USED = 260  # Existing six-league 500-credit tier has priority.
MIN_THE_ODDS_LEFT = 220


def utc(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_TIMESTAMP")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return dt.astimezone(timezone.utc)


def fetch(url, headers):
    """Only caller-controlled fixed URLs, no URL query auth or error echo."""
    req=Request(url,headers={**headers,"Accept":"application/json",
                             "User-Agent":"FootballKingJ1FreeResearch/1.0"})
    try:
        with urlopen(req,timeout=15) as resp:
            content=resp.read(MAX_BLOB+1)
            meta=dict(resp.headers.items())
    except HTTPError as exc:
        if exc.code in (401,403):
            raise ValueError("AUTH_NOT_ALLOWED") from None
        if exc.code in (402,422):
            raise ValueError("PAID_SCOPE_NOT_ALLOWED") from None
        if exc.code==429:
            raise ValueError("RATE_LIMIT_REACHED") from None
        raise ValueError("UPSTREAM_HTTP_FAILURE") from None
    except (URLError,TimeoutError,OSError):
        raise ValueError("UPSTREAM_UNAVAILABLE") from None
    if len(content)>MAX_BLOB:
        raise ValueError("UPSTREAM_OVERSIZE")
    try:
        return json.loads(content),meta
    except (ValueError,UnicodeError):
        raise ValueError("UPSTREAM_INVALID_JSON") from None


def source(name, configured):
    return {"provider":name,"configured":bool(configured),
            "status":"HOLD" if configured else "NOT_CONFIGURED",
            "reason":"PENDING_SOURCE_CHECK" if configured else "PRIVATE_FREE_KEY_NOT_CONFIGURED",
            "requests_attempted":0,"upcoming_events":0,
            "fresh_3way_event_count":0,"fresh_spread_event_count":0,
            "fresh_totals_event_count":0,
            "free_stale_quote_rejects":0,
            "market_quotes_are_not_executable":True,
            "independently_calibrated_j1_model":False,
            "production_recommendations":"DISABLED"}


def _prematch(now, kickoff):
    return now + PREMATCH_BUFFER < kickoff <= now + FUTURE_WINDOW


def _price(o):
    # PropLine exposes American odds and price_decimal; prefer the explicit
    # decimal field if present. Never interpret +125 as decimal 125.
    d=o.get("price_decimal")
    if type(d) in (float,int) and math.isfinite(d) and 1.01<=d<=100:
        return float(d)
    a=o.get("price")
    if type(a) not in (float,int) or not math.isfinite(a):
        return None
    if a>=100:
        return 1+float(a)/100
    if a<=-100:
        return 1+100/abs(float(a))
    return None


def _side(o, home, away):
    value=o.get("side")
    name=o.get("name")
    named=("home" if name==home else "away" if name==away else
           "draw" if name=="Draw" else None)
    if value in ("home","away","draw"):
        # A contradictory known team name cannot silently override the
        # source's declared direction in a J1 1X2 bookmaker observation.
        return value if named is None or named==value else None
    return named


def _no_vig(prices):
    if set(prices)!={"home","draw","away"}:
        return None
    inv=[1/prices[k] for k in ("home","draw","away")]
    s=sum(inv)
    if not 0.98<=s<=1.35:
        return None
    return tuple(v/s for v in inv)


def _complete_two_way_line(kind, outcomes, home, away):
    """One coherent J1 two-way line from ONE book, for coverage ONLY.

    This is not an independent bookmaker quote, live execution check, or
    inferred Asian-handicap/totals settlement model. A single valid leg,
    duplicate direction, or incompatible quarter-goal line fails closed.
    """
    if kind not in ("spreads", "totals") or not isinstance(outcomes, list):
        return False
    if len(outcomes)!=2:
        return False
    legs={}
    for outcome in outcomes:
        if not isinstance(outcome, dict) or _price(outcome) is None:
            return False
        if kind=="spreads":
            side=_side(outcome,home,away)
            if side not in ("home","away"):
                return False
        else:
            label=outcome.get("name")
            side=label if label in ("Over","Under") else None
            if side is None:
                return False
        if side in legs:
            return False
        try:
            units=quarter_units(outcome.get("point"))
        except (ValueError, TypeError):
            return False
        if kind=="totals" and units<0:
            return False
        legs[side]=units
    if kind=="spreads":
        return set(legs)=={"home","away"} and legs["home"]==-legs["away"]
    return set(legs)=={"Over","Under"} and legs["Over"]==legs["Under"]


def _j1_native_event_id(event):
    """Only a bounded native event ID; bool is not a valid numeric ID."""
    if not isinstance(event,dict):
        return None
    raw=event.get("id")
    if type(raw) not in (str,int) or (type(raw) is int and raw <= 0):
        return None
    val=str(raw)
    if (not val or len(val)>128 or val!=val.strip()
            or not val.isprintable()):
        return None
    return val


def _j1_fixture_signature(event):
    """Only used for conservative duplicate *rejection*, not ID assignment."""
    if (not isinstance(event,dict)
            or event.get("sport_key") not in (None,SPORT)):
        return None
    home,away=event.get("home_team"),event.get("away_team")
    if (not all(type(v) is str and 0<len(v)<=110 for v in (home,away))
            or home==away):
        return None
    try:
        kickoff=utc(event["commence_time"])
    except (KeyError,TypeError,ValueError,OverflowError):
        return None
    h,a=team_id("japan_j1",home),team_id("japan_j1",away)
    if h and a and h==a:
        # Different display spellings of the SAME normalized club cannot
        # make a valid home-versus-away event. Earlier literal fallback
        # inflated provider coverage even though no consensus was emitted.
        return None
    teams=("canonical",h,a) if h and a else ("literal",home,away)
    return (teams,kickoff)


def prop_line(rows, *, now):
    """Strict upstream shape: event-book-market-outcome. No raw quotes out."""
    if not isinstance(rows,list) or len(rows)>MAX_EVENTS:
        raise ValueError("INVALID_PROPLINE_EVENT_BATCH")
    state=source("propline",True)
    consensus={}
    # Quarantine every copy, even if the second row is invalid/finished:
    # first-wins would manufacture seemingly valid pre-match coverage.
    event_counts=Counter(k for k in (_j1_native_event_id(e) for e in rows)
                         if k is not None)
    fixture_counts=Counter(k for k in (_j1_fixture_signature(e) for e in rows)
                           if k is not None)
    for event in rows:
        if (not isinstance(event,dict) or event.get("is_outright") is True
                or event.get("completed") is True):
            continue
        eid=_j1_native_event_id(event)
        fixture_signature=_j1_fixture_signature(event)
        home,away=event.get("home_team"),event.get("away_team")
        if (eid is None or fixture_signature is None
                or event_counts[eid]!=1 or fixture_counts[fixture_signature]!=1):
            continue
        try:
            kickoff=utc(event["commence_time"])
        except (KeyError,ValueError,TypeError,OverflowError):
            continue
        if not _prematch(now,kickoff):
            continue
        state["upcoming_events"]+=1
        books=event.get("bookmakers")
        if not isinstance(books,list) or len(books)>MAX_BOOKS:
            continue
        # Duplicate native book IDs poison all copies, including copies with
        # invalid/missing market blocks. A previous first-wins rule was unsafe.
        book_counts=Counter(book.get("key") for book in books
                            if isinstance(book,dict)
                            and type(book.get("key")) is str)
        per_book={}
        spreads=set()
        totals=set()
        for book in books:
            if not isinstance(book,dict):
                continue
            bk=book.get("key")
            if (type(bk) is not str or not bk or len(bk)>128
                    or bk!=bk.strip() or book_counts[bk]!=1):
                # An ambiguous native bookmaker cannot supply an independent
                # quote, even if one duplicate is invalid or appears later.
                continue
            markets=book.get("markets",[])
            if not isinstance(markets,list) or len(markets)>35:
                continue
            per_book[bk]=None
            market_blocks=Counter(row.get("key") for row in markets
                                  if isinstance(row,dict)
                                  and row.get("key") in ("h2h","spreads","totals"))
            h2h_blocks=market_blocks["h2h"]
            for m in markets:
                if (not isinstance(m,dict) or m.get("key") not in ("h2h","spreads","totals")
                        or m.get("suspended_at") is not None):
                    continue
                try:
                    age=now-utc(m["last_update"])
                    if not timedelta(seconds=-5)<=age<=MAX_AGE:
                        state["free_stale_quote_rejects"]+=1
                        continue
                except (KeyError,ValueError,TypeError,OverflowError):
                    state["free_stale_quote_rejects"]+=1
                    continue
                outcomes=m.get("outcomes")
                if not isinstance(outcomes,list) or len(outcomes)>35:
                    continue
                if m["key"]=="h2h":
                    # Multiple H2H market blocks from one bookmaker are
                    # ambiguous even if their initial rows have valid odds.
                    if h2h_blocks!=1:
                        continue
                    prices={}
                    seen_sides=set()
                    duplicate=False
                    for o in outcomes:
                        if not isinstance(o,dict):
                            continue
                        side=_side(o,home,away)
                        if side is None:
                            continue
                        # Check duplicate identity BEFORE checking price:
                        # a bad second HOME value must poison the block.
                        if side in seen_sides:
                            duplicate=True
                            continue
                        seen_sides.add(side)
                        price=_price(o)
                        if price is not None:
                            prices[side]=price
                    if not duplicate:
                        p=_no_vig(prices)
                        if p:
                            per_book[bk]=p
                elif m["key"] in ("spreads","totals"):
                    # A lone home or Over price is not a complete market.
                    # Reject duplicate market blocks and require complementary
                    # sides on exactly the same settlement line for this book.
                    kind=m["key"]
                    if (market_blocks[kind]==1
                            and _complete_two_way_line(kind,outcomes,home,away)):
                        if kind=="spreads":
                            spreads.add(bk)
                        else:
                            totals.add(bk)
        if spreads:
            state["fresh_spread_event_count"]+=1
        if totals:
            state["fresh_totals_event_count"]+=1
        confirmed=[b for b in per_book.values() if b is not None]
        if len(confirmed)>=2:
            state["fresh_3way_event_count"]+=1
            values=[statistics.median(x[i] for x in confirmed) for i in range(3)]
            scale=sum(values)
            h,a=team_id("japan_j1",home),team_id("japan_j1",away)
            if h and a and h!=a:
                consensus[(h,a,kickoff)]=tuple(v/scale for v in values)
    state["status"]="RESEARCH_ONLY" if any(state[k] for k in (
        "fresh_3way_event_count","fresh_spread_event_count",
        "fresh_totals_event_count")) else "HOLD"
    state["reason"]="FRESH_PREMATCH_RESEARCH_METADATA_ONLY" if state["status"]=="RESEARCH_ONLY" else "NO_FRESH_QUALIFIED_J1_LINES"
    return state,consensus


def rundown(dates, payload, *, now):
    """Count FREE delayed J1 main lines only; do not publicize proprietary legs."""
    state=source("therundown",True)
    if (not isinstance(dates,dict) or not isinstance(payload,dict)
            or not isinstance(payload.get("events"),list)
            or len(payload["events"])>MAX_EVENTS):
        raise ValueError("INVALID_RUNDOWN_FREE_SCHEMA")
    for e in payload["events"]:
        if not isinstance(e,dict) or e.get("sport_id") not in (19,"19"):
            continue
        try:
            kickoff=utc(e["event_date"])
        except (KeyError,TypeError,ValueError,OverflowError):
            continue
        if not _prematch(now,kickoff):
            continue
        state["upcoming_events"]+=1
        markets=e.get("markets")
        if not isinstance(markets,list) or len(markets)>120:
            continue
        ready=set()
        for m in markets:
            if not isinstance(m,dict) or m.get("market_id") not in (1,2,3):
                continue
            participants=m.get("participants")
            if not isinstance(participants,list) or len(participants)>8:
                continue
            # A 3-way moneyline cannot be counted from one team price,
            # even if that single leg is repeated across three bookmakers.
            # Count distinct participant identities only; one source account
            # repeated under several affiliate IDs is not extra outcomes.
            qualified_participants=set()
            for p in participants:
                if not isinstance(p,dict) or not isinstance(p.get("lines"),list):
                    continue
                participant=p.get("id")
                if not isinstance(participant,(str,int)) or str(participant)=="":
                    continue
                valid_affiliates=set()
                for line in p["lines"][:10]:
                    if not isinstance(line,dict) or not isinstance(line.get("prices"),dict):
                        continue
                    for book_id,item in line["prices"].items():
                        if book_id not in ("19","22","23") or not isinstance(item,dict):
                            continue
                        price=item.get("price")
                        if type(price) not in (int,float) or not math.isfinite(price) or -100<price<100:
                            continue
                        try:
                            age=now-utc(item["updated_at"])
                            if not timedelta(seconds=-5)<=age<=timedelta(minutes=25):
                                state["free_stale_quote_rejects"]+=1
                                continue
                        except (KeyError,TypeError,ValueError,OverflowError):
                            continue
                        valid_affiliates.add(book_id)
                if len(valid_affiliates)>=2:
                    qualified_participants.add(str(participant))
            needed=3 if m["market_id"]==1 else 2
            if len(qualified_participants)>=needed:
                ready.add(m["market_id"])
        if 1 in ready:state["fresh_3way_event_count"]+=1
        if 2 in ready:state["fresh_spread_event_count"]+=1
        if 3 in ready:state["fresh_totals_event_count"]+=1
    state["status"]="RESEARCH_ONLY" if any(state[k] for k in (
        "fresh_3way_event_count","fresh_spread_event_count",
        "fresh_totals_event_count")) else "HOLD"
    state["reason"]="FIVE_MIN_DELAYED_PREMATCH_COVERAGE_ONLY" if state["status"]=="RESEARCH_ONLY" else "NO_FRESH_J1_MAIN_LINES"
    return state


def _rundown_date(dates,now):
    items=dates.get(str(RUNDOWN_ID)) if isinstance(dates,dict) else None
    if not isinstance(items,dict) or not isinstance(items.get("dates"),list):
        return None
    best=[]
    for value in items["dates"][:200]:
        try:
            dt=datetime.fromtimestamp(float(value),tz=timezone.utc)
        except (OverflowError,ValueError,TypeError):
            continue
        if now.date() <= dt.date() <= (now+FUTURE_WINDOW).date():
            best.append(dt)
    return min(best).date().isoformat() if best else None


def strict_fresh_odds_j1(event,now):
    """Both contributing 1X2 books need individually recent market stamps.

    Existing core six-league adapter intentionally permits older market
    observations. Japan J1 cannot reuse that tolerance as 'fresh' research.
    """
    if not isinstance(event,dict):
        return None
    home,away=event.get("home_team"),event.get("away_team")
    if not all(isinstance(x,str) and x for x in (home,away)) or home==away:
        return None
    try:
        ko=utc(event["commence_time"])
    except (KeyError,ValueError,TypeError,OverflowError):
        return None
    if not _prematch(now,ko):return None
    bookmakers=event.get("bookmakers")
    if not isinstance(bookmakers,list) or len(bookmakers)>MAX_BOOKS:
        return None
    # The J1 market sidecar must not count a first valid bookmaker copy
    # when another raw block carries the same native bookmaker ID.
    book_counts=Counter(book.get("key") for book in bookmakers
                        if isinstance(book,dict) and type(book.get("key")) is str)
    good={}
    for book in bookmakers:
        if not isinstance(book,dict):
            continue
        key=book.get("key")
        if (type(key) is not str or not key or key!=key.strip()
                or len(key)>128 or book_counts[key]!=1):
            continue
        markets=book.get("markets")
        if not isinstance(markets,list):
            continue
        h2h=[row for row in markets if isinstance(row,dict)
             and row.get("key")=="h2h"]
        if len(h2h)!=1 or h2h[0].get("suspended_at") is not None:
            # A recent last_update does NOT override explicit suspension.
            # Keep this J1-only rule separate from the existing six-league
            # parser, and reject any non-null suspension marker (even 0).
            continue
        val=book_probabilities(book,home,away,now)
        if val is None:
            continue
        p,updated=val
        if not timedelta(seconds=-5)<=now-updated<=MAX_AGE:
            continue
        good[key]=p
    if len(good)<2:
        return None
    rows=list(good.values())
    center=[statistics.median(v[i] for v in rows) for i in range(3)]
    scale=sum(center)
    if scale<=0:return None
    return home,away,ko,tuple(v/scale for v in center)


def odds_japan(key,*,now,opener=None):
    state=source("the_odds_api_j1",True)
    consensus={}
    def pull(path,params=None):
        state["requests_attempted"]+=1
        return odds_retrieve(path,key,opener=opener,params=params) if opener is not None else odds_retrieve(path,key,params=params)
    sport_list,q=pull(THE_ODDS_SPORTS)
    if not isinstance(sport_list,list):
        raise ValueError("ODDS_SPORT_CATALOG_INVALID")
    if not any(isinstance(x,dict) and x.get("key")==SPORT and x.get("active") is True for x in sport_list):
        state["reason"]="J1_SPORT_NOT_ACTIVE_FOR_ACCOUNT"
        return state,consensus
    if not (may_spend(q) and type(q.get("used")) is int and q["used"]<MAX_THE_ODDS_USED
            and type(q.get("remaining")) is int and q["remaining"]>MIN_THE_ODDS_LEFT):
        state["reason"]="PRESERVE_EXISTING_SIX_LEAGUE_FREE_CREDITS"
        state["quota_remaining"]=q.get("remaining")
        return state,consensus
    events,post=pull(THE_ODDS_J1,{"regions":"eu","markets":"h2h",
                                  "oddsFormat":"decimal","dateFormat":"iso"})
    if not isinstance(events,list) or len(events)>MAX_EVENTS:
        raise ValueError("INVALID_ODDS_J1_EVENTS")
    state["quota_remaining"]=post.get("remaining")
    # Reject *all copies* of duplicated native IDs, or the same normalized
    # fixture under multiple IDs, before counting any coverage. ID checks
    # include malformed/final versions so a clean first row cannot win.
    native_ids=Counter(ident for ident in
                       (_j1_native_event_id(event) for event in events)
                       if ident is not None)
    fixture_ids=Counter(ident for ident in
                        (_j1_fixture_signature(event) for event in events)
                        if ident is not None)
    for event in events:
        if not isinstance(event,dict) or type(event.get("id")) is not str:
            continue
        native_id=_j1_native_event_id(event)
        fixture_id=_j1_fixture_signature(event)
        if (native_id is None or fixture_id is None
                or native_ids[native_id]!=1 or fixture_ids[fixture_id]!=1
                or event.get("completed") is True
                or event.get("is_outright") is True):
            continue
        kickoff=fixture_id[1]
        if not _prematch(now,kickoff):
            continue
        state["upcoming_events"]+=1
        fresh=strict_fresh_odds_j1(event,now)
        if fresh is None:continue
        home,away,kickoff,p=fresh
        state["fresh_3way_event_count"]+=1
        h,a=team_id("japan_j1",home),team_id("japan_j1",away)
        if h and a and h!=a:
            consensus[(h,a,kickoff)]=p
    state["status"]="RESEARCH_ONLY" if state["fresh_3way_event_count"] else "HOLD"
    state["reason"]="DERIVED_PREMATCH_3WAY_CONSENSUS_ONLY" if state["status"]=="RESEARCH_ONLY" else "NO_ELIGIBLE_3WAY_J1_PRICES"
    return state,consensus


def crosscheck(a,b):
    """Count coarse J1 coverage ONLY for mutually unique source pairings.

    A single candidate on the A side is insufficient if that B candidate is
    also close to a competing A fixture. Never resolve ambiguity by loop order
    or first-wins. Thirty minutes is a candidate discovery tolerance, NOT
    same-instant independent bookmaker or market quote authentication.
    """
    candidate_b={}
    reverse_counts=defaultdict(int)
    for (home,away,kickoff),_ in a.items():
        key=(home,away,kickoff)
        candidates=[other for other in b
                    if other[0]==home and other[1]==away
                    and abs((other[2]-kickoff).total_seconds())<=30*60]
        candidate_b[key]=candidates
        for other in candidates:
            reverse_counts[other]+=1
    matches=[]
    for key, p in a.items():
        candidates=candidate_b[key]
        if len(candidates)!=1 or reverse_counts[candidates[0]]!=1:
            continue
        q=b[candidates[0]]
        matches.append(abs(p[0]-q[0]))
    return {"same_fixture_two_api_observations":len(matches),
            "median_abs_home_probability_delta":(
                round(statistics.median(matches),5) if matches else None),
            "api_provider_count_is_not_independent_bookmaker_count":True,
            "independent_venue_quote_verified":False}


def collect(keys=None,*,now=None,requester=fetch,odds_opener=None):
    keys=keys or {}
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError("NAIVE_NOW")
    names=(("propline","PROPLINE_API_KEY"),
           ("therundown","THERUNDOWN_API_KEY"),
           ("the_odds_api_j1","THE_ODDS_API_KEY"))
    providers={name:source(name,bool(keys.get(env))) for name,env in names}
    comparisons={}
    for name,env in names:
        token=keys.get(env)
        if not isinstance(token,str) or not token:
            continue
        state=providers[name]
        try:
            if name=="propline":
                state["requests_attempted"]+=1
                rows,meta=requester(PROPLINE_URL,{"X-API-Key":token})
                next_state,comparisons["propline"]=prop_line(rows,now=now)
                next_state["requests_attempted"]=state["requests_attempted"]
                remaining=meta.get("X-Daily-Remaining",meta.get("x-daily-remaining"))
                if remaining is not None:
                    try:next_state["provider_daily_remaining"]=max(0,int(remaining))
                    except (TypeError,ValueError):pass
                state=next_state
            elif name=="therundown":
                state["requests_attempted"]+=1
                dates,first_headers=requester(RUNDOWN_DATES_URL,{"X-TheRundown-Key":token})
                # TheRundown bills DATA POINTS, not request count.
                # If a free bootstrap is already costly/unknown, stop.
                day=_rundown_date(dates,now)
                charged=first_headers.get("X-Datapoints",first_headers.get("x-datapoints"))
                if charged is not None:
                    try:
                        if int(charged)>500:
                            day=None
                            state["reason"]="RUNDOWN_FREE_DATAPOINT_GUARD"
                    except (TypeError,ValueError):
                        day=None
                        state["reason"]="RUNDOWN_UNKNOWN_DATAPOINT_HEADER"
                if not day:
                    if state["reason"] == "PENDING_SOURCE_CHECK":
                        state["reason"]="NO_J1_UPCOMING_DATE_ON_FREE_SCHEDULE"
                else:
                    state["requests_attempted"]+=1
                    url=RUNDOWN_EVENT_PREFIX+day+"?"+urlencode({
                        "market_ids":"1,2,3","affiliate_ids":"19,22,23",
                        "main_line":"true"})
                    body,_=requester(url,{"X-TheRundown-Key":token})
                    next_state=rundown(dates,body,now=now)
                    next_state["requests_attempted"]=state["requests_attempted"]
                    state=next_state
            else:
                state,comparisons["the_odds_api_j1"]=odds_japan(
                    token,now=now,opener=odds_opener)
        except (ValueError,TypeError,KeyError,OverflowError,APIProblem) as exc:
            state["status"]="HOLD"
            code=str(exc)
            state["reason"]=code if code in {
                "AUTH_NOT_ALLOWED","PAID_SCOPE_NOT_ALLOWED",
                "RATE_LIMIT_REACHED","UPSTREAM_UNAVAILABLE","UPSTREAM_OVERSIZE",
                "UPSTREAM_INVALID_JSON","UPSTREAM_HTTP_FAILURE",
                "INVALID_PROPLINE_EVENT_BATCH","INVALID_RUNDOWN_FREE_SCHEMA",
                "INVALID_ODDS_J1_EVENTS","ODDS_SPORT_CATALOG_INVALID",
                "MISSING_KEY","KEY_REJECTED_OR_NOT_AUTHORIZED",
                "SPORT_OR_PLAN_NOT_AUTHORIZED","RATE_LIMITED",
                "PROVIDER_NETWORK_ERROR","PROVIDER_BAD_JSON"
            } else "SCHEMA_OR_PROVIDER_RESEARCH_HOLD"
        providers[name]=state
    report={
        "schema":SCHEMA,"collected_utc":now.isoformat(),
        "status":"RESEARCH_ONLY" if any(
            x["status"]=="RESEARCH_ONLY" for x in providers.values()) else "HOLD",
        "j1_free_prematch_sources":[providers[name] for name,_ in names],
        "cross_feed_consistency_observation":crosscheck(
            comparisons.get("propline",{}),
            comparisons.get("the_odds_api_j1",{})),
        "the_odds_api_european_six_league_market_is_untouched":True,
        "j1_fixtures_not_independently_verified":True,
        "j1_model_remains_uncalibrated":True,
        "j1_2026_27_outcomes_not_proven":True,
        "realtime_inplay_quotes_confirmed":False,
        "free_tier_closing_lines_available":False,
        "raw_bookmaker_prices_or_names_redistributed":False,
        "estimated_roi":None,"bet_recommendation_count":0,
        "production_recommendations":"DISABLED",
        "no_secret_values_logged_or_persisted":True,
    }
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",default="japan-free-market.json")
    a=p.parse_args()
    result=collect({
        "PROPLINE_API_KEY":os.environ.get("PROPLINE_API_KEY",""),
        "THERUNDOWN_API_KEY":os.environ.get("THERUNDOWN_API_KEY",""),
        "THE_ODDS_API_KEY":os.environ.get("THE_ODDS_API_KEY",""),
    })
    dest=Path(a.output)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",
                    encoding="utf-8")
    print(json.dumps({"status":result["status"],
                      "sources":[{"provider":s["provider"],"status":s["status"],
                                  "reason":s["reason"],"requests":s["requests_attempted"],
                                  "j1_events_with_3way":s["fresh_3way_event_count"],
                                  "j1_events_with_spread":s["fresh_spread_event_count"]}
                                 for s in result["j1_free_prematch_sources"]],
                      "production_recommendations":"DISABLED"},ensure_ascii=False))


if __name__=="__main__":
    main()
