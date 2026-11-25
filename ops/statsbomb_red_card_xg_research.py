"""Single-dismissal historical xG diagnostic, not a causal red-card model.

Use pinned StatsBomb open data bytes. Period clocks include stoppage but
exclude halftime; they are elapsed match clocks, not ball-in-play time.
Lineups and events come from the same provider, not independent sources.
"""
import json
import math
import re
from hashlib import sha256
from ops.statsbomb_shot_xg_diagnostic import summarize_shots, _unique, _bad_constant
from ops.xt_chronological_research import validate_manifest, verify_all_historical_sources

REDS = {"Red Card", "Second Yellow"}


def _clock(value):
    if type(value) is not str or not re.fullmatch(r"00:[0-5][0-9]:[0-5][0-9](?:\.[0-9]{1,3})?", value):
        raise ValueError("INVALID_PERIOD_CLOCK")
    _,m,s=value.split(":")
    return 60*int(m)+float(s)


def _lineup_clock(value):
    if type(value) is not str or not re.fullmatch(r"[0-9]{1,3}:[0-5][0-9]",value):
        raise ValueError("INVALID_LINEUP_CLOCK")
    m,s=map(int,value.split(":"))
    return 60*m+s


def _decode(raw,spec):
    if (type(raw) is not bytes or not 0<len(raw)<=8_000_000
            or len(raw)!=spec["bytes"] or sha256(raw).hexdigest()!=spec["sha256"]):
        raise ValueError("RAW_BYTES_MISMATCH")
    a=json.loads(raw,object_pairs_hook=_unique,parse_constant=_bad_constant)
    if type(a) is not list or len(a)!=spec["records"]:
        raise ValueError("RAW_RECORD_COUNT_MISMATCH")
    return a


def summarize(events_raw,lineups_raw,rec):
    # Full shot validation, including provider xG and unique event IDs.
    summarize_shots(events_raw,rec)
    events=_decode(events_raw,rec["events"])
    lineups=_decode(lineups_raw,rec["lineups"])
    teams=(rec["home_team_id"],rec["away_team_id"])
    if len(lineups)!=2 or {t["team_id"] for t in lineups}!=set(teams):
        raise ValueError("LINEUP_TEAM_MISMATCH")
    claims=[]
    for t in lineups:
        for p in t["lineup"]:
            for c in p["cards"]:
                if c["card_type"] in REDS:
                    claims.append((t["team_id"],p["player_id"],c))
    reds=[]
    ends={1:[],2:[]}
    seen=set()
    for e in events:
        ix=e["index"]
        if type(ix) is not int or ix<=0 or ix in seen:
            raise ValueError("INVALID_EVENT_INDEX")
        seen.add(ix)
        for attr in ("foul_committed","bad_behaviour"):
            card=e.get(attr,{}).get("card",{})
            if card.get("name") in REDS:
                reds.append((e,card["name"]))
        if e["period"] in ends and e["type"]["name"]=="Half End":
            ends[e["period"]].append(_clock(e["timestamp"]))
    out={"status":"HOLD","production_recommendations":"DISABLED",
         "match_id":rec["match_id"],"event_dismissals":len(reds),
         "lineup_dismissals":len(claims),"independent_source_verified":False,
         "model_promoted":False,"certified_prospective_samples":0,
         "positive_ev_verified":False,"causal_effect_estimated":False}
    if not reds and not claims:
        return {**out,"reason":"NO_DISMISSAL_RECORDED"}
    if len(reds)!=1 or len(claims)!=1:
        return {**out,"reason":"UNSUPPORTED_OR_CONFLICTING_CARD_COUNTS"}
    e,label=reds[0]
    team,player,c=claims[0]
    period=e["period"]
    if (period not in (1,2) or team not in teams or e["team"]["id"]!=team
            or e["player"]["id"]!=player or c["period"]!=period or c["card_type"]!=label):
        return {**out,"reason":"CARD_IDENTITY_OR_PERIOD_MISMATCH"}
    clock=_clock(e["timestamp"])
    if abs(_lineup_clock(c["time"])-(45*60*(period-1)+clock))>=1.0:
        return {**out,"reason":"CARD_CLOCK_MISMATCH"}
    if any(not v or max(v)!=min(v) or not 2700<=v[0]<3600 for v in ends.values()):
        return {**out,"reason":"MISSING_OR_CONFLICTING_HALF_END_CLOCK"}
    if not 0<clock<ends[period][0]:
        return {**out,"reason":"CARD_OUTSIDE_HALF_CLOCK"}
    before=clock+(ends[1][0] if period==2 else 0)
    after=ends[1][0]+ends[2][0]-before
    buckets={t:[[],[]] for t in teams}
    for shot in events:
        if shot["type"]["name"]!="Shot" or shot["period"] not in (1,2):
            continue
        if not 0<=_clock(shot["timestamp"])<=ends[shot["period"]][0]:
            raise ValueError("SHOT_OUTSIDE_HALF_CLOCK")
        order=(shot["period"],_clock(shot["timestamp"]),shot["index"])
        red_order=(period,clock,e["index"])
        # When period-clock and event index disagree, do not silently reorder.
        if (order>red_order)!=(shot["index"]>e["index"]):
            return {**out,"reason":"SHOT_EVENT_ORDER_CONFLICT"}
        buckets[shot["team"]["id"]][int(order>red_order)].append(shot["shot"])
    def metrics(items,seconds):
        x=math.fsum(s["statsbomb_xg"] for s in items)
        return {"shots":len(items),"xg":x,"shot_goals":sum(s["outcome"]["name"]=="Goal" for s in items),
                "xg_per_90_elapsed_minutes":x*5400/seconds}
    return {**out,"reason":"SINGLE_PROVIDER_POSTMATCH_DESCRIPTIVE_ONLY",
            "card_event_id":e["id"],"dismissed_team_id":team,"period":period,
            "card_clock_seconds":clock,"before_elapsed_seconds":before,"after_elapsed_seconds":after,
            "ball_in_play_time_verified":False,"on_pitch_dismissal_independently_verified":False,
            "teams":{str(t):{"before":metrics(buckets[t][0],before),
                             "after":metrics(buckets[t][1],after)} for t in teams}}


def audit_local(root,manifest):
    train,evaluation=validate_manifest(manifest)
    frozen=verify_all_historical_sources(root,manifest)
    def run(rows):
        return [summarize(frozen[r["match_id"]]["events"],frozen[r["match_id"]]["lineups"],r)
                for r in rows]
    return {"status":"HOLD","production_recommendations":"DISABLED",
            "certified_prospective_samples":0,"model_promoted":False,
            "training":run(train),"evaluation":run(evaluation)}
