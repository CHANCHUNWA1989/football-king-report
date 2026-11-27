"""Unified live scenario research; no feeds, fitted coefficients or production signals."""
from datetime import datetime, timezone
import math
from .research_multimodel_v1 import score_matrix, multiclass_brier, log_loss
from .research_asian_settlement_v1 import asian_ev

VERSION = "unified-live-v1"
MAX_AGE = 90

def number(v, lo, hi):
    if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
        raise ValueError("invalid numeric input")
    return float(v)

def integer(v, lo, hi):
    if type(v) is not int or not lo <= v <= hi:
        raise ValueError("invalid integer input")
    return v

def utc(v):
    if not isinstance(v, str):
        raise ValueError("timestamp missing")
    d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("timezone missing")
    return d.astimezone(timezone.utc)

def text(v):
    if not isinstance(v, str) or not v.strip():
        raise ValueError("identifier missing")
    return v.strip()

def record(r, event, now, material):
    if r["event_id"] != event:
        raise ValueError("fixture mismatch")
    text(r["source"]); text(r["origin"])
    t, cap = utc(r["updated"]), utc(r["captured"])
    if not material <= t <= cap <= now or (now-t).total_seconds() > MAX_AGE:
        raise ValueError("stale, future or pre-event record")
    return t

def pair(rows, event, now, material):
    if not isinstance(rows, list) or len(rows) != 2:
        raise ValueError("two records required")
    a,b = rows
    times = [record(r,event,now,material) for r in rows]
    if (a["source"].strip().casefold() == b["source"].strip().casefold()
        or a["origin"].strip().casefold() == b["origin"].strip().casefold()):
        raise ValueError("duplicate origin/source")
    if abs((times[0]-times[1]).total_seconds()) > 30:
        raise ValueError("snapshot skew")
    return a,b

def terminal(h,a,lh,la):
    if lh == 0 and la == 0:
        m = [[1.0]]
    else:
        m = score_matrix(lh,la)
    n = len(m)+max(h,a)
    final = [[0.0]*n for _ in range(n)]
    for i,row in enumerate(m):
        for j,p in enumerate(row):
            final[h+i][a+j] = p
    return final

def summaries(m):
    return {"home":sum(p for h,row in enumerate(m) for a,p in enumerate(row) if h>a),
            "draw":sum(row[h] for h,row in enumerate(m)),
            "away":sum(p for h,row in enumerate(m) for a,p in enumerate(row) if h<a),
            "over_2_5":sum(p for h,row in enumerate(m) for a,p in enumerate(row) if h+a>2),
            "scores":sorted([(p,h,a) for h,row in enumerate(m) for a,p in enumerate(row) if p>0], reverse=True)[:5]}

def intensity(prior, recent, window, remaining, margin, own_red, opp_red, scenario):
    # Recent non-penalty xG only; shrink toward fixed pre-match prior.
    # All multipliers and 30-minute pseudo-exposure are UNFITTED sensitivity assumptions.
    observed = min(4.0, recent*90/window)
    w = window/(window+30)
    rate = (1-w)*prior + w*observed
    state = (1.0 if margin==0 else (1.10 if margin<0 else 0.92))
    red = (0.80**own_red)*(1.15**opp_red)
    return min(10.0,max(0.001,rate*state*red*remaining/90*scenario))

def forecast(snapshot, prior, *, as_of):
    out = {"version":VERSION,"status":"HOLD","production":"DISABLED",
           "certified_ev":False,"source_authenticity_verified":False,
           "calibrated":False,"reasons":[]}
    try:
        now = utc(as_of)
        event = text(snapshot["event_id"])
        if prior["event_id"] != event:
            raise ValueError("prior fixture mismatch")
        kickoff = utc(snapshot["kickoff"])
        material = utc(snapshot["last_material_event"])
        if not utc(prior["frozen_at"]) < kickoff <= material <= now:
            raise ValueError("invalid prior or event time")
        ph,pa = [number(prior[k],0.05,5) for k in ("home_xg","away_xg")]
        score1,score2 = pair(snapshot["score"],event,now,material)
        fields = ("home","away","home_red","away_red","minute","phase","lineup_id","last_material_event")
        if any(score1[k]!=score2[k] for k in fields):
            raise ValueError("score, card, clock or lineup disagreement")
        if utc(score1["last_material_event"]) != material:
            raise ValueError("material event mismatch")
        h,a = [integer(score1[k],0,30) for k in ("home","away")]
        rh,ra = [integer(score1[k],0,4) for k in ("home_red","away_red")]
        lineup = text(score1["lineup_id"])
        minute = number(score1["minute"],0,90)
        phase = score1["phase"]
        if phase not in ("1H","2H") or (phase=="1H" and minute>45) or (phase=="2H" and minute<45) or minute>=90:
            raise ValueError("unsupported phase or clock")
        remaining = 90-minute
        baseline = summaries(terminal(h,a,ph*remaining/90,pa*remaining/90))
        out.update(baseline=baseline,prior_signature=(event,prior["frozen_at"],ph,pa),
                   state=(h,a,rh,ra,lineup),minute=minute,phase=phase)
        s1,s2 = pair(snapshot["stats"],event,now,material)
        # Only a common, explicitly bounded recent window after last material event.
        for s in (s1,s2):
            if s["lineup_id"]!=lineup or s["phase"]!=phase:
                raise ValueError("stats phase/lineup mismatch")
            if not material <= utc(s["window_start"]) < utc(s["window_end"]) <= utc(s["updated"]):
                raise ValueError("invalid recent window")
            if (utc(s["updated"])-utc(s["window_end"])).total_seconds()>30:
                raise ValueError("stale recent window")
        if any(s1[k]!=s2[k] for k in ("window_start","window_end")):
            raise ValueError("xG window mismatch")
        window = number((utc(s1["window_end"])-utc(s1["window_start"])).total_seconds()/60,3,15)
        vals=[]
        for k in ("home_npxg","away_npxg"):
            x,y = number(s1[k],0,5),number(s2[k],0,5)
            if abs(x-y)>0.15:
                raise ValueError("xG disagreement")
            vals.append((x+y)/2)
        matrices=[]
        # Sensitivity envelope, not a confidence interval.
        for sh,sa in ((1,1),(.8,1.2),(1.2,.8),(.8,.8),(1.2,1.2)):
            lh=intensity(ph,vals[0],window,remaining,h-a,rh,ra,sh)
            la=intensity(pa,vals[1],window,remaining,a-h,ra,rh,sa)
            matrices.append(terminal(h,a,lh,la))
        models=[summaries(m) for m in matrices]
        out["dynamic"]=models[0]
        out["scenario_ranges"]={k:[min(m[k] for m in models),max(m[k] for m in models)]
                                for k in ("home","draw","away","over_2_5")}
        out["dynamic_minus_baseline"]={k:models[0][k]-baseline[k] for k in ("home","draw","away","over_2_5")}
        q=snapshot["quote"]
        record(q,event,now,material)
        if q["in_play"] is not True or q["scope"]!="full_match" or q["suspended"] is not False:
            raise ValueError("unsupported or suspended quote")
        text(q["bookmaker"])
        if (q["home"],q["away"],q["home_red"],q["away_red"],q["lineup_id"])!=out["state"]:
            raise ValueError("quote state mismatch")
        if q["market"]=="totals" and number(q["line"],0,20)<0:
            raise ValueError("invalid totals")
        if q["market"]=="handicap" and q["line_convention"]!="home_signed":
            raise ValueError("ambiguous handicap convention")
        evs=[asian_ev(m,market=q["market"],selection=q["selection"],line=q["line"],
                     decimal_odds=number(q["decimal_odds"],1.001,1000)) for m in matrices]
        out["hypothetical_ev"]={"base":evs[0]["expected_net_return"],
             "range":[min(e["expected_net_return"] for e in evs),max(e["expected_net_return"] for e in evs)],
             "settlement":evs[0]["outcome_probabilities"],"not_executable":True}
        out["reasons"]=["UNFITTED_SCENARIOS","SOURCE_AUTHENTICITY_UNPROVEN","QUOTE_EXECUTABILITY_UNPROVEN","OOS_UNPROVEN"]
    except (KeyError,TypeError,ValueError,OverflowError,AttributeError) as exc:
        out["reasons"]=[str(exc)]
    return out

def audit_change(old,new):
    if (old["version"]!=VERSION or new["version"]!=VERSION or
        old["prior_signature"]!=new["prior_signature"] or new["minute"]<=old["minute"] or
        old["state"]!=new["state"] or old["phase"]!=new["phase"]):
        raise ValueError("not comparable; state or model changed")
    return {k:{"clock_only":new["baseline"][k]-old["baseline"][k],
               "dynamic_increment_change":new["dynamic_minus_baseline"][k]-old["dynamic_minus_baseline"][k],
               "total":new["dynamic"][k]-old["dynamic"][k]}
            for k in ("home","draw","away","over_2_5")}

def paired_metrics(rows):
    """Descriptive paired Brier/log loss; not independent OOS certification."""
    seen=set(); scores=[]
    for r in rows:
        event=text(r["event_id"])
        if event in seen or not utc(r["train_cutoff"]) < utc(r["kickoff"]) <= utc(r["forecast_at"]) < utc(r["result_at"]):
            raise ValueError("duplicate fixture or temporal leakage")
        seen.add(event)
        b,c,y=r["baseline"],r["challenger"],r["outcome"]
        scores.append((multiclass_brier(c,y)-multiclass_brier(b,y),log_loss(c,y)-log_loss(b,y)))
    if not scores:
        raise ValueError("empty cohort")
    return {"n":len(scores),"delta_brier":sum(s[0] for s in scores)/len(scores),
            "delta_log_loss":sum(s[1] for s in scores)/len(scores),"certified_oos":False}
