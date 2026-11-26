"""Private retrospective dismissal-event windows; no causal or live inference."""
import math
import re
from deep_handicap_historical_inputs import _decode,_id,MAX_BYTES,MAX_EVENTS
from deep_handicap_halftime_study import extract

WINDOW=600000  # ten minutes of same-period event clock
STAMP=re.compile(r"([0-9]{2}):([0-5][0-9]):([0-5][0-9])\.([0-9]{3})")
DISMISSALS={"Red Card","Second Yellow"}
WINDOW_REASONS=("CLOCK_AMBIGUOUS","NO_DISMISSAL_EVENT","MULTIPLE_DISMISSAL_EVENTS",
                "INSUFFICIENT_SAME_PERIOD_WINDOW","SIMULTANEOUS_SHOT_AMBIGUOUS",
                "PAIRED_CLOCK_WINDOWS_PRIVATE_ONLY")

def millis(v):
    m=STAMP.fullmatch(v) if isinstance(v,str) else None
    if not m:raise ValueError("BAD_EVENT_CLOCK")
    h,mi,s,ms=map(int,m.groups())
    if h>1:raise ValueError("BAD_EVENT_CLOCK")
    return ((h*60+mi)*60+s)*1000+ms

def inspect(raw,match):
    # Existing structural and FT reconciliation are mandatory first.
    extract(raw,match)
    h,a=(_id(match["home_team"]["home_team_id"]),_id(match["away_team"]["away_team_id"]))
    events=sorted(_decode(raw,MAX_BYTES),key=lambda e:e["index"])
    cards=[];shots=[];ends={1:[],2:[]};last={};ambiguous=False
    for e in events:
        period=e["period"];kind=e["type"]["name"]
        if period not in (1,2):raise ValueError("REGULATION_ONLY")
        # Examine both documented card-bearing event types. Do not infer a
        # dismissal merely from a yellow, foul, or player substitution.
        fields=[(k,e[k]) for k in ("foul_committed","bad_behaviour") if k in e]
        for k,v in fields:
            if not isinstance(v,dict):raise ValueError("BAD_CARD_PAYLOAD")
            if "card" not in v:continue
            c=v["card"]
            if not isinstance(c,dict) or c.get("name") not in DISMISSALS|{"Yellow Card"}:
                raise ValueError("UNKNOWN_CARD")
            expected={"foul_committed":"Foul Committed","bad_behaviour":"Bad Behaviour"}[k]
            if kind!=expected:raise ValueError("CARD_TYPE_CONFLICT")
            if c["name"] in DISMISSALS:
                team=_id(e["team"]["id"]);player=_id(e["player"]["id"])
                if team not in (h,a):raise ValueError("CARD_TEAM")
                t=millis(e["timestamp"])
                if t<last.get(period,0):ambiguous=True
                last[period]=t
                cards.append((period,t,team,player))
        if kind in ("Shot","Half End"):
            t=millis(e["timestamp"])
            if t<last.get(period,0):ambiguous=True
            last[period]=t
            if kind=="Half End":ends[period].append(t)
            else:shots.append((period,t,_id(e["team"]["id"]),e["shot"]["statsbomb_xg"]))
    out={"status":"HOLD","production_recommendations":"DISABLED",
         "source_authenticated":False,"on_field_dismissal_verified":False,
         "causal_effect_identified":False,"model_calibrated":False,
         "true_forward_sample_count":0,"private_windows":None}
    if ambiguous:return {**out,"reason":"CLOCK_AMBIGUOUS"}
    if not cards:return {**out,"reason":"NO_DISMISSAL_EVENT"}
    if len(cards)!=1:return {**out,"reason":"MULTIPLE_DISMISSAL_EVENTS"}
    period,t,team,_=cards[0]
    if not ends[period] or t<WINDOW or t+WINDOW>min(ends[period]):
        return {**out,"reason":"INSUFFICIENT_SAME_PERIOD_WINDOW"}
    if any(p==period and s==t for p,s,_,_ in shots):
        return {**out,"reason":"SIMULTANEOUS_SHOT_AMBIGUOUS"}
    sums={(side,window):[] for side in ("dismissal_team","opponent") for window in ("before","after")}
    for p,s,k,x in shots:
        if p!=period:continue
        role="dismissal_team" if k==team else "opponent"
        if t-WINDOW<=s<t:sums[role,"before"].append(x)
        elif t<s<=t+WINDOW:sums[role,"after"].append(x)
    return {**out,"reason":"PAIRED_CLOCK_WINDOWS_PRIVATE_ONLY",
            "private_windows":{role:{w:{"shots":len(sums[role,w]),"shot_xg":math.fsum(sums[role,w])}
                                      for w in ("before","after")} for role in ("dismissal_team","opponent")},
            "same_period_window_minutes":10,"score_state_confounding_ruled_out":False}


def classify_window(report):
    """A technical parse pass does not imply an eligible paired window."""
    if (type(report) is not dict or report.get("status")!="HOLD"
            or report.get("production_recommendations")!="DISABLED"
            or type(report.get("true_forward_sample_count")) is not int
            or report["true_forward_sample_count"]!=0
            or any(report.get(k) is not False for k in
                   ("source_authenticated","on_field_dismissal_verified",
                    "causal_effect_identified","model_calibrated"))):
        raise ValueError("UNSAFE_WINDOW_REPORT")
    reason=report.get("reason")
    if reason not in WINDOW_REASONS:raise ValueError("UNKNOWN_WINDOW_REASON")
    paired=reason=="PAIRED_CLOCK_WINDOWS_PRIVATE_ONLY"
    private=report.get("private_windows")
    if not paired:
        if private is not None:raise ValueError("UNEXPECTED_PRIVATE_WINDOWS")
        return reason
    if (report.get("same_period_window_minutes")!=10
            or report.get("score_state_confounding_ruled_out") is not False
            or type(private) is not dict or set(private)!={"dismissal_team","opponent"}):
        raise ValueError("BAD_PAIRED_WINDOWS")
    for windows in private.values():
        if type(windows) is not dict or set(windows)!={"before","after"}:
            raise ValueError("BAD_PAIRED_WINDOWS")
        for item in windows.values():
            if type(item) is not dict or set(item)!={"shots","shot_xg"}:
                raise ValueError("BAD_WINDOW_FEATURE")
            n,x=item["shots"],item["shot_xg"]
            if (type(n) is not int or not 0<=n<=MAX_EVENTS
                    or type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=n):
                raise ValueError("BAD_WINDOW_FEATURE")
    return reason

def reconcile_dispositions(reasons,expected):
    """Private exhaustive accounting; never publish observed match counts."""
    from collections import Counter
    if type(expected) is not int or not 0<=expected<=48 or len(reasons)!=expected:
        raise ValueError("WINDOW_DENOMINATOR")
    allowed=(*WINDOW_REASONS,"STRUCTURE_REJECTED")
    if any(k not in allowed for k in reasons):raise ValueError("UNKNOWN_WINDOW_REASON")
    counts=Counter(reasons)
    return {k:counts[k] for k in allowed}
