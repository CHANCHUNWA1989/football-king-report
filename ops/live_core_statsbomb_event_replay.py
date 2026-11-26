"""Private StatsBomb historical event replay; not a live or causal model.

StatsBomb Open Data: https://github.com/hudl/open-data
Operator must verify research-use rights and publication attribution separately.
No network, no raw files in Git, no estimates of prospective performance.
"""
import json
import math
import re
import hashlib
from collections import defaultdict
from research_strict_json import unique_object,reject_constant

MAX=12_000_000
CLOCK=re.compile(r"^(\d{2}):([0-5]\d):([0-5]\d)\.(\d{3})$")
CARDS={"Red Card","Second Yellow"}


def clock(s):
    if type(s) is not str or not (m:=CLOCK.fullmatch(s)):
        raise ValueError("EVENT_CLOCK")
    h,mn,sec,ms=map(int,m.groups())
    return 3600000*h+60000*mn+1000*sec+ms


def native(v):
    if type(v) is not int or v<=0:
        raise ValueError("NATIVE_ID")
    return v


def decode(raw,expected_blob):
    if type(raw) is not bytes or not 0<len(raw)<=MAX:
        raise ValueError("CAPTURE_SIZE")
    blob=hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()
    if blob!=expected_blob:
        raise ValueError("BLOB_MISMATCH")
    rows=json.loads(raw.decode("utf-8"),object_pairs_hook=unique_object,parse_constant=reject_constant)
    if type(rows) is not list or not 0<len(rows)<=20000:
        raise ValueError("EVENT_LIST")
    return rows


def replay(events,home_id,away_id):
    """Measure historical elapsed exposure and shot xG by player-dismissal state.

    Period-relative timestamps; include stoppage within halves, exclude extra
    time and shootouts. Temporary injury exits do not count as dismissals.
    Starting XI and substitutions define roster eligibility, not actual
    second-by-second on-pitch headcount. Ambiguous card identity fails closed.
    """
    teams=(native(home_id),native(away_id))
    if len(set(teams))!=2 or type(events) is not list or not events:
        raise ValueError("FIXTURE")
    roster={t:set() for t in teams};sent={t:set() for t in teams}
    xi=set();ids=set();last_index=0
    periods={};last_period=0
    xg=defaultdict(lambda:[0.,0.]);shots=defaultdict(lambda:[0,0])
    exposure=defaultdict(int);cards=[]
    ignored_nonreg=0;last_time=0;end_times=set()
    def state():
        return tuple(len(sent[t]) for t in teams)
    def close_period():
        if len(end_times)!=1 or next(iter(end_times))!=last_time:
            raise ValueError("PERIOD_END")
        periods[last_period]=last_time
    for e in events:
        idx=native(e["index"]);eid=e["id"]
        if idx<=last_index or type(eid) is not str or not eid or eid in ids:
            raise ValueError("EVENT_ORDER")
        last_index=idx;ids.add(eid)
        p=e["period"]
        if type(p) is not int or p not in (1,2,3,4,5):
            raise ValueError("PERIOD")
        typ=e["type"]["name"]
        card=(e.get("foul_committed") if typ=="Foul Committed" else
              e.get("bad_behaviour") if typ=="Bad Behaviour" else None) or {}
        card_name=(card.get("card") or {}).get("name")
        if p>2:
            if card_name in CARDS:ignored_nonreg+=1
            continue
        if p!=last_period:
            if p!=last_period+1:raise ValueError("PERIOD_ORDER")
            if last_period:close_period()
            last_period=p;last_time=0;end_times=set()
        ts=clock(e["timestamp"])
        # Event providers can order some adjacent actions out of timestamp
        # order. Do not infer exposure or card ordering through such ambiguity.
        if ts<last_time or ts>100*60000:
            raise ValueError("EVENT_TIME_REGRESSION")
        exposure[state()]+=ts-last_time;last_time=ts
        team=native(e["team"]["id"])
        if team not in roster:raise ValueError("TEAM")
        if typ=="Half End":
            end_times.add(ts)
        if typ=="Starting XI":
            if p!=1 or ts!=0 or team in xi:raise ValueError("STARTING_XI")
            players=[native(v["player"]["id"]) for v in e["tactics"]["lineup"]]
            if len(players)!=11 or len(set(players))!=11:raise ValueError("STARTING_XI")
            roster[team].update(players);xi.add(team)
        elif typ=="Substitution":
            player=native(e["player"]["id"])
            replacement=native(e["substitution"]["replacement"]["id"])
            if player not in roster[team] or replacement in roster[team] or replacement in sent[team]:
                raise ValueError("SUBSTITUTION")
            roster[team].remove(player);roster[team].add(replacement)
        if card_name in CARDS:
            player=native(e["player"]["id"])
            if player in sent[team]:
                raise ValueError("DUPLICATE_DISMISSAL")
            if player not in roster[team]:
                raise ValueError("NON_ROSTER_RED_REVIEW")
            sent[team].add(player);roster[team].remove(player)
            if len(sent[team])>3:raise ValueError("RED_COUNT")
            cards.append((p,ts,team,player))
        elif card_name is not None and card_name!="Yellow Card":
            raise ValueError("UNKNOWN_CARD")
        if typ=="Shot":
            v=e["shot"]["statsbomb_xg"]
            if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1:
                raise ValueError("MISSING_OR_INVALID_XG")
            if xi!=set(teams):raise ValueError("MISSING_LINEUP")
            k=teams.index(team)
            xg[state()][k]+=v;shots[state()][k]+=1
    close_period()
    if set(periods)!={1,2} or xi!=set(teams):
        raise ValueError("INCOMPLETE_REGULATION")
    buckets=[]
    for k,ms in sorted(exposure.items()):
        if not ms and not sum(shots[k]):continue
        buckets.append({"dismissals":list(k),"elapsed_minutes":ms/60000,
                        "shots":shots[k],"xg":xg[k]})
    return {"buckets":buckets,"regulation_cards":len(cards),
            "ignored_nonregulation_cards":ignored_nonreg,
            "regulation_elapsed_minutes":sum(periods.values())/60000,
            "historically_reconstructed":True,"source":"StatsBomb",
            "source_authenticated":False,"model_calibrated":False,
            "causal_red_card_effect_estimated":False,
            "verified_forward_sample_credit":0,"positive_ev_verified":False,
            "production_recommendations":"DISABLED","status":"HOLD"}


def audit(raw,expected_blob,home_id,away_id):
    try:
        return replay(decode(raw,expected_blob),home_id,away_id)
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):
        return {"status":"HOLD","reason":"EVENT_REVIEW_REQUIRED",
                "source":"StatsBomb","model_calibrated":False,
                "verified_forward_sample_credit":0,"production_recommendations":"DISABLED"}
