"""Offline provider capture normalization and quote evidence review.

No external I/O, no key, no quota bypass. Capture times are claims, not upstream
timestamps. Never treat an empty events list as independently verified no cards.
"""
import hashlib
import json
import math
from datetime import datetime
from urllib.parse import urlsplit
from vnext_direct_transport_offline import unique_object, reject_constant
from live_core_real_observations import research, evidence
from live_snapshot_adapter import hold

MAX_BYTES=1200000


def capture(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("CAPTURE_SIZE")
    data=json.loads(raw.decode("utf-8"),object_pairs_hook=unique_object,parse_constant=reject_constant)
    if type(data) is not dict or type(data.get("errors")) not in (dict,list) or data["errors"]:
        raise ValueError("PROVIDER_ERROR")
    if type(data.get("response")) is not list or len(data["response"]) != 1:
        raise ValueError("REQUIRE_ONE_FIXTURE")
    return data["response"][0],hashlib.sha256(raw).hexdigest()


def identity(row, mapping):
    if type(mapping) is not dict or set(mapping)!={"fixture_id","provider_id","home_id","away_id","kickoff_utc"}:
        raise ValueError("CROSSWALK_SCHEMA")
    for k in ("provider_id","home_id","away_id"):
        if type(mapping[k]) is not int or mapping[k]<=0:
            raise ValueError("CROSSWALK_ID")
    if mapping["home_id"]==mapping["away_id"]:
        raise ValueError("CROSSWALK_TEAMS")
    f=row["fixture"]
    teams=row["teams"]
    def clock(s):
        d=datetime.fromisoformat(s.replace("Z","+00:00"))
        if d.tzinfo is None:
            raise ValueError("NAIVE_KICKOFF")
        return d
    if (f["id"],teams["home"]["id"],teams["away"]["id"])!=(mapping["provider_id"],mapping["home_id"],mapping["away_id"]) or clock(f["date"])!=clock(mapping["kickoff_utc"]):
        raise ValueError("FIXTURE_CROSSWALK_MISMATCH")
    return f


def normalize(raw, mapping, *, captured, received, observed_claim, now):
    """API-Football fixtures?id=... captured response; no request made here.

    Reject stoppage/half-time and uncertain card events. The fixture endpoint
    may omit events/statistics: never convert omission into zero.
    """
    if any(type(v) is not int for v in (captured,received,observed_claim,now)) or not 0<observed_claim<=captured<=received<=now or now-observed_claim>90:
        raise ValueError("CAPTURE_CLOCK")
    row,sha=capture(raw)
    f=identity(row,mapping)
    status=f["status"]
    if status["short"] not in ("1H","2H") or status.get("extra") not in (None,0):
        raise ValueError("UNSUPPORTED_PHASE")
    minute=status["elapsed"]
    events=row.get("events")
    if type(events) is not list or len(events)>200:
        raise ValueError("EVENTS_MISSING")
    cards={mapping["home_id"]:set(),mapping["away_id"]:set()}
    for e in events:
        if e["type"]=="Var":
            # No reliable correction/retraction mapping in this adapter.
            raise ValueError("VAR_EVENT_REVIEW_REQUIRED")
        if e["type"]!="Card":
            continue
        detail=e["detail"]
        if detail=="Yellow Card":
            continue
        if detail not in ("Red Card","Second Yellow card","Second Yellow Card"):
            raise ValueError("UNKNOWN_CARD")
        t=e["time"]["elapsed"]
        team,player=e["team"]["id"],e["player"]["id"]
        if team not in cards or type(player) is not int or player<=0 or type(t) is not int or not 0<=t<=minute:
            raise ValueError("CARD_ID_OR_CLOCK")
        cards[team].add(player)
    state=dict(fixture_id=mapping["fixture_id"],origin="api-football",
               observed=observed_claim,received=received,minute=minute,
               home=row["goals"]["home"],away=row["goals"]["away"],
               red_home=len(cards[mapping["home_id"]]),red_away=len(cards[mapping["away_id"]]),
               phase={"1H":"FIRST_HALF","2H":"SECOND_HALF"}[status["short"]])
    item=dict(state=state,url="https://v3.football.api-sports.io/fixtures",payload_sha256=sha)
    evidence(item,now)
    xg=None
    stats=row.get("statistics")
    if stats is not None:
        if type(stats) is not list or len(stats)>2:
            raise ValueError("STATISTICS_SCHEMA")
        values={}
        for team in stats:
            tid=team["team"]["id"]
            if tid not in cards or tid in values:
                raise ValueError("STATISTICS_TEAM")
            matches=[s["value"] for s in team["statistics"] if s["type"]=="expected_goals"]
            if len(matches)>1:
                raise ValueError("DUPLICATE_XG")
            value=matches[0] if matches else None
            if value is not None:
                if type(value) not in (str,int,float):
                    raise ValueError("INVALID_XG")
                value=float(value)
                if not math.isfinite(value) or not 0<=value<=30:
                    raise ValueError("INVALID_XG")
            values[tid]=value
        if all(values.get(k) is not None for k in cards):
            xg=dict(fixture_id=mapping["fixture_id"],observed=observed_claim,minute=minute,
                    home=values[mapping["home_id"]],away=values[mapping["away_id"]],
                    source_url=item["url"])
    return item,xg


def quote_review(quote, state, now):
    """Structural quote check only; a timestamp/price claim is not executable."""
    keys={"fixture_id","observed","minute","score","reds","market","side","line",
          "decimal_price","source_url","bookmaker","suspended","scope"}
    if type(quote) is not dict or set(quote)!=keys:
        raise ValueError("QUOTE_SCHEMA")
    q=quote
    if (q["fixture_id"]!=state["fixture_id"] or type(q["observed"]) is not int
        or not 0<=now-q["observed"]<=30 or abs(q["observed"]-state["observed"])>30
        or type(q["minute"]) is not int or q["minute"]!=state["minute"]
        or q["score"]!=[state["home"],state["away"]]
        or q["reds"]!=[state["red_home"],state["red_away"]]
        or q["suspended"] is not False or q["scope"]!="REGULATION_FULLTIME"):
        raise ValueError("QUOTE_NOT_SAME_CUT")
    if any(type(v) is not int for v in q["score"]+q["reds"]):
        raise ValueError("QUOTE_STATE_TYPE")
    p=q["decimal_price"]
    if type(p) not in (int,float) or not math.isfinite(p) or not 1<p<=1000:
        raise ValueError("QUOTE_PRICE")
    if type(q["bookmaker"]) is not str or not q["bookmaker"].strip() or len(q["bookmaker"])>100:
        raise ValueError("QUOTE_BOOKMAKER")
    if type(q["source_url"]) is not str or len(q["source_url"])>2048:
        raise ValueError("QUOTE_URL")
    u=urlsplit(q["source_url"])
    if u.scheme!="https" or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ValueError("QUOTE_URL")
    return {k:q[k] for k in ("market","side","line")}


def run(raw,mapping,*,captured,received,observed_claim,now,secondary,prematch,markets,quotes=None):
    """One offline path from original captured bytes to existing research model."""
    try:
        a,xg=normalize(raw,mapping,captured=captured,received=received,observed_claim=observed_claim,now=now)
        out=research(a,secondary,kickoff_utc=mapping["kickoff_utc"],prematch=prematch,
                     now=now,markets=markets,xg=xg)
        if out.get("research_status")!="RESEARCH_ONLY":
            return out
        reviewed=[]
        if quotes is not None:
            if type(quotes) is not list or len(quotes)>24:
                raise ValueError("QUOTE_BATCH")
            for q in quotes:
                m=quote_review(q,a["state"],now)
                if m not in markets:
                    raise ValueError("QUOTE_MARKET_NOT_REQUESTED")
                quote_review(q,secondary["state"],now)
                reviewed.append({"market":m,"same_cut_claim":True,
                                 "executable_verified":False})
        return {**out,"provider_payload_digest":a["payload_sha256"],
                "provider_upstream_clock_verified":False,
                "quote_reviews":reviewed,"actual_live_odds_verified":False,
                "positive_ev_verified":False,"model_edge":None}
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return hold("PROVIDER_OR_QUOTE_EVIDENCE_REJECTED")
