"""Opt-in live state sensitivity. No authenticated feed, live calibration or betting.
All inputs are assertions; fixed red-card coefficients are stress scenarios only.
"""
import argparse
import json
import math
from datetime import timedelta
from pathlib import Path
from ops.live_score_identity_guard import check, parse_utc

MAX_AGE = timedelta(seconds=90)
SCENARIOS = (("NO_CARD_EFFECT_CONTROL", 1.0, 1.0),
             ("CARD_STRESS_A", .85, 1.15),
             ("CARD_STRESS_B", .65, 1.35))
SCHEMA = "football-king-live-state-sensitivity-v1"

def _state(obs, now, ko):
    stamp = parse_utc(obs.get("source_updated_utc"))
    captured = parse_utc(obs.get("captured_utc"))
    if not ko <= stamp <= captured <= now or now-stamp > MAX_AGE:
        raise ValueError("LIVE_STATE_TOO_OLD_OR_FUTURE")
    minute = obs.get("regulation_minute")
    status = obs.get("match_status")
    if (type(minute) is not int or not 1 <= minute <= 89
            or (status == "FIRST_HALF" and minute > 45)
            or (status == "HALF_TIME" and minute != 45)
            or (status == "SECOND_HALF" and minute < 46)
            or status not in ("FIRST_HALF","HALF_TIME","SECOND_HALF")):
        raise ValueError("UNSUPPORTED_REGULATION_CLOCK")
    # Wall-clock can be longer than playing time because of half-time/stoppages.
    elapsed = (stamp-ko).total_seconds()/60
    if elapsed < minute-1 or elapsed > minute+45:
        raise ValueError("LIVE_CLOCK_INCONSISTENT")
    events = obs.get("red_card_events")
    if obs.get("red_card_history_complete_assertion") is not True or not isinstance(events,list) or len(events)>8:
        raise ValueError("MISSING_COMPLETE_RED_CARD_ASSERTION")
    normalized = []
    ids = set()
    for event in events:
        if not isinstance(event,dict):
            raise ValueError("INVALID_RED_CARD_EVENT")
        ident, side, when = (event.get(k) for k in ("source_event_id","side","minute"))
        if (not isinstance(ident,str) or not 1<=len(ident)<=128 or ident in ids
                or side not in ("HOME","AWAY") or type(when) is not int
                or not 1<=when<=minute or event.get("status")!="CONFIRMED_ASSERTION"):
            raise ValueError("INVALID_RED_CARD_EVENT")
        ids.add(ident)
        normalized.append((side,when))
    if any(sum(side==team for side,_ in normalized)>4 for team in ("HOME","AWAY")):
        raise ValueError("UNSUPPORTED_PLAYER_COUNT")
    return minute,tuple(sorted(normalized))

def _weights(rate):
    values=[math.exp(-rate)]
    for i in range(1,41):
        values.append(values[-1]*rate/i)
    total=math.fsum(values)
    return [p/total for p in values]

def _project(h,a,h_rate,a_rate):
    one=[0.,0.,0.]
    over=0.
    for i,ph in enumerate(_weights(h_rate)):
        for j,pa in enumerate(_weights(a_rate)):
            x,y=h+i,a+j
            p=ph*pa
            one[0 if x>y else 1 if x==y else 2]+=p
            if x+y>2: over+=p
    if abs(math.fsum(one)-1)>1e-9:
        raise ValueError("BAD_PROBABILITY_MASS")
    return {"hypothetical_final_1x2":one,
            "hypothetical_final_over_2_5":min(1.,max(0.,over)),
            "hypothetical_trailing_team_final_win":one[0] if h<a else one[2] if a<h else None}

def evaluate(fixture, observations, *, as_of_utc, assumed_full_match_rates):
    result={"schema":SCHEMA,"status":"HOLD","production_recommendations":"DISABLED",
            "independently_authenticated":False,"model_calibrated":False,
            "actual_live_xg_used":False,"actual_market_quote_available":False,
            "positive_ev_verified":False,"recommendations":[],"scenarios":[],
            "scenario_only":True,"reason":"INVALID_INPUT"}
    guard=check(fixture,observations,as_of_utc)
    if guard["status"]!="RESEARCH_ONLY":
        return {**result,"reason":guard["reason"]}
    if guard["match_status"] not in ("FIRST_HALF","HALF_TIME","SECOND_HALF"):
        return {**result,"reason":"NOT_SUPPORTED_LIVE_REGULATION"}
    try:
        now,ko=parse_utc(as_of_utc),parse_utc(fixture["kickoff_utc"])
        states=[_state(o,now,ko) for o in observations]
        if len(set(states))!=1:
            raise ValueError("CROSS_SOURCE_CLOCK_OR_CARD_CONFLICT")
        minute,cards=states[0]
        if (not isinstance(assumed_full_match_rates,(list,tuple))
                or len(assumed_full_match_rates)!=2
                or not all(type(v) in (int,float) and math.isfinite(v) and .1<=v<=5.5
                           for v in assumed_full_match_rates)):
            raise ValueError("MISSING_VALID_HYPOTHETICAL_RATES")
        hg,ag=assumed_full_match_rates
        hr=sum(side=="HOME" for side,_ in cards)
        ar=sum(side=="AWAY" for side,_ in cards)
        left=(90-minute)/90
        h,a=guard["score_home"],guard["score_away"]
        out=[]
        for label,own,opponent in SCENARIOS:
            # Differential red-card effects only; no claim of fitted coefficients.
            diff=hr-ar
            home=hg*left*(own**max(diff,0))*(opponent**max(-diff,0))
            away=ag*left*(own**max(-diff,0))*(opponent**max(diff,0))
            out.append({"scenario_id":label,"assumed_own_card_multiplier":own,
                        "assumed_opponent_card_multiplier":opponent,
                        "assumed_remaining_home_goals":home,
                        "assumed_remaining_away_goals":away,
                        **_project(h,a,home,away)})
        return {**result,"status":"RESEARCH_ONLY",
                "reason":"CONSISTENT_ASSERTIONS_HYPOTHETICAL_SENSITIVITY_NOT_AUTHENTICATED",
                "regulation_minute":minute,"score_assertion":[h,a],
                "red_card_count_assertion":[hr,ar],"providers":guard["providers"],
                "stoppage_time_included":False,"scenarios":out}
    except (ValueError,KeyError,TypeError,OverflowError) as exc:
        return {**result,"reason":str(exc) if isinstance(exc,ValueError) else "INVALID_INPUT"}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    path=Path(args.input)
    if path.stat().st_size>1_000_000:
        raise ValueError("INPUT_TOO_LARGE")
    doc=json.loads(path.read_text(encoding="utf-8"))
    result=evaluate(doc.get("fixture"),doc.get("observations"),
                    as_of_utc=doc.get("as_of_utc"),
                    assumed_full_match_rates=doc.get("assumed_full_match_rates"))
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__":
    main()
