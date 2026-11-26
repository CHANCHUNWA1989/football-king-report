"""Offline descriptive comparison of paired within-fixture shot xG exposure.

Input is private regulation-dismissal bucket output, e.g. PR #680 replay.
No source authentication, causal estimation, coefficient fitting or publication.
Only one permanent dismissal and >=15 minutes in each state are admitted.
"""
import math
import random
from collections import Counter
from datetime import datetime, timezone
import re

MAX_MATCHES=10000
MIN_EXPOSURE=15
MIN_MATCHES=30


def _number(v):
    return type(v) in (int,float) and math.isfinite(v)


def _fixture(row):
    if type(row.get("regulation_cards")) is not int or row["regulation_cards"]!=1:
        raise ValueError("NOT_SINGLE_DISMISSAL")
    buckets=row.get("buckets")
    if not isinstance(buckets,list) or len(buckets)!=2:
        raise ValueError("INVALID_BUCKETS")
    parsed={}
    for b in buckets:
        cards=b["dismissals"]
        if (not isinstance(cards,list) or len(cards)!=2
                or any(type(v) is not int for v in cards)):
            raise ValueError("INVALID_CARD_STATE")
        state=tuple(cards)
        if state not in ((0,0),(1,0),(0,1)) or state in parsed:
            raise ValueError("INVALID_CARD_STATE")
        minutes=b["elapsed_minutes"]
        xg=b["xg"]
        shots=b["shots"]
        if not _number(minutes) or not 0<minutes<=150:
            raise ValueError("INVALID_EXPOSURE")
        if (not isinstance(shots,list) or len(shots)!=2
                or any(type(s) is not int or not 0<=s<=200 for s in shots)
                or not isinstance(xg,list) or len(xg)!=2
                or any(not _number(v) or not 0<=v<=s for v,s in zip(xg,shots))):
            raise ValueError("INVALID_XG")
        parsed[state]=(minutes,xg)
    if (0,0) not in parsed:
        raise ValueError("MISSING_PRE_STATE")
    post=next(k for k in parsed if k!=(0,0))
    pre_minutes,pre_xg=parsed[(0,0)]
    post_minutes,post_xg=parsed[post]
    if not 90<=pre_minutes+post_minutes<=150:
        raise ValueError("INVALID_REGULATION_DURATION")
    if min(pre_minutes,post_minutes)<MIN_EXPOSURE:
        raise ValueError("INSUFFICIENT_EXPOSURE")
    dismissed=post.index(1)
    return (pre_minutes,post_minutes,pre_xg[dismissed],post_xg[dismissed],
            pre_xg[1-dismissed],post_xg[1-dismissed])


def _totals(rows):
    return [math.fsum(row[i] for row in rows) for i in range(6)]


def _difference(t, i):
    return 90*(t[i+1]/t[1]-t[i]/t[0])


def _interval(values):
    values=sorted(values)
    def q(p):
        pos=(len(values)-1)*p
        low=int(pos)
        return values[low]+(pos-low)*(values[min(low+1,len(values)-1)]-values[low])
    return {"lower":q(.025),"upper":q(.975)}


def _uncertainty(rows):
    n=len(rows)
    report={"status":"INSUFFICIENT_SAMPLE","replicates":0,
            "method":"paired_fixture_percentile_bootstrap",
            "nominal_percentile_level":.95,"inferentially_validated":False,
            "rate_difference_intervals":None,
            "dependence_and_confounding_not_adjusted":True}
    if n<MIN_MATCHES:
        return report
    # Bound work; no hidden truncation or change of estimand.
    if n>3000:
        report["status"]="BOOTSTRAP_WORK_LIMIT"
        return report
    rng=random.Random(714)
    draws=[[],[]]
    for _ in range(1000):
        t=[0.0]*6
        for _ in range(n):
            row=rows[rng.randrange(n)]
            for i,value in enumerate(row):
                t[i]+=value
        for j,i in enumerate((2,4)):
            draws[j].append(_difference(t,i))
    report.update(status="DESCRIPTIVE_INTERVAL_ONLY",replicates=1000,
                  rate_difference_intervals={
                      name:_interval(draws[j])
                      for j,name in enumerate(("dismissed_team","opponent"))})
    return report


def _sensitivity(rows):
    out=[]
    for threshold in (15,20,30):
        subset=[row for row in rows if min(row[:2])>=threshold]
        item={"minimum_minutes_each_state":threshold,"matches":len(subset),
              "dismissed_team":None,"opponent":None}
        if subset:
            t=_totals(subset)
            for name,i in (("dismissed_team",2),("opponent",4)):
                item[name]={"rate_difference":_difference(t,i)}
        out.append(item)
    return out


def _influence(rows):
    if not rows:
        return None
    t=_totals(rows)
    out={}
    for name,i in (("dismissed_team",2),("opponent",4)):
        equal=math.fsum(_difference(row,i) for row in rows)/len(rows)
        bounds=None
        if len(rows)>1:
            loo=[_difference([a-b for a,b in zip(t,row)],i) for row in rows]
            bounds={"lower":min(loo),"upper":max(loo)}
        out[name]={"equal_fixture_mean_difference":equal,
                   "leave_one_out_rate_difference_range":bounds}
    return out


def _context(row, parsed):
    # Exposure time includes stoppage, not the official regulation clock.
    pre=parsed[0]
    band="LT_30" if pre<30 else "30_TO_LT_60" if pre<60 else "GE_60"
    state="UNKNOWN"
    quality="MISSING"
    if "score_immediately_before_dismissal" in row:
        score=row["score_immediately_before_dismissal"]
        quality="INVALID"
        if (isinstance(score,list) and len(score)==2
                and all(type(x) is int and 0<=x<=25 for x in score)):
            # _fixture has already validated exactly one dismissal state.
            dismissed=next(b["dismissals"].index(1) for b in row["buckets"]
                           if 1 in b["dismissals"])
            diff=score[dismissed]-score[1-dismissed]
            state="LEADING" if diff>0 else "TRAILING" if diff<0 else "DRAWING"
            quality="DECLARED"
    return state,band,quality


def _strata(records):
    states=Counter(dict.fromkeys(("LEADING","DRAWING","TRAILING","UNKNOWN"),0))
    bands=Counter(dict.fromkeys(("LT_30","30_TO_LT_60","GE_60"),0))
    quality=Counter()
    groups={}
    for parsed,(state,band,q) in records:
        states[state]+=1
        bands[band]+=1
        quality[q]+=1
        groups.setdefault((state,band),[]).append(parsed)
    results=[]
    for (state,band),rows in sorted(groups.items()):
        item={"score_state_at_dismissal":state,"pre_dismissal_elapsed_band":band,
              "matches":len(rows),"rates":None,"status":"INSUFFICIENT_SAMPLE"}
        # Provisional disclosure threshold, not an inferential sample-size claim.
        if len(rows)>=10:
            t=_totals(rows)
            item.update(status="DESCRIPTIVE_ONLY",rates={
                name:{"pre_xg_per_90":90*t[i]/t[0],
                      "post_xg_per_90":90*t[i+1]/t[1],
                      "rate_difference":_difference(t,i)}
                for name,i in (("dismissed_team",2),("opponent",4))})
        results.append(item)
    return {"score_context_counts":dict(states),"elapsed_band_counts":dict(bands),
            "missing_score_context":quality["MISSING"],"invalid_score_context":quality["INVALID"],
            "groups":results,"min_group_matches":10,
            "elapsed_band_is_not_official_match_minute":True,
            "score_claims_authenticated":False,"confounding_adjusted":False,
            "descriptive_only":True}


def _strength_context(row):
    if "prematch_strength" not in row:
        return "UNKNOWN","MISSING",None
    claim=row["prematch_strength"]
    def utc(value):
        if not isinstance(value,str) or len(value)>64:
            raise ValueError("BAD_TIME")
        d=datetime.fromisoformat(value.replace("Z","+00:00"))
        if d.tzinfo is None:
            raise ValueError("NAIVE_TIME")
        return d.astimezone(timezone.utc)
    try:
        if not isinstance(claim,dict) or claim.get("scale")!="ELO_POINTS":
            raise ValueError("BAD_SCALE")
        for field in ("match_id","home_id","away_id"):
            if (type(row.get(field)) is not int or not 0<row[field]<2**63
                    or type(claim.get(field)) is not int or claim[field]!=row[field]):
                raise ValueError("BAD_IDENTITY")
        if row["home_id"]==row["away_id"]:
            raise ValueError("SAME_TEAM")
        model=claim["model_id"]
        if not isinstance(model,str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}",model):
            raise ValueError("BAD_MODEL")
        if not utc(claim["training_cutoff_utc"])<=utc(claim["recorded_utc"])<utc(row["kickoff_utc"]):
            raise ValueError("LATE_RATING")
        h,a=claim["home_rating"],claim["away_rating"]
        if any(not _number(x) or not 0<=x<=4000 for x in (h,a)):
            raise ValueError("BAD_RATING")
        dismissed=next(b["dismissals"].index(1) for b in row["buckets"] if 1 in b["dismissals"])
        gap=(h-a) if dismissed==0 else (a-h)
        return ("STRONGER" if gap>=100 else "WEAKER" if gap<=-100 else "SIMILAR"),"DECLARED",model
    except (ValueError,TypeError,KeyError,OverflowError):
        return "UNKNOWN","INVALID",None


def _strength_strata(records):
    counts=Counter(dict.fromkeys(("STRONGER","SIMILAR","WEAKER","UNKNOWN"),0))
    quality=Counter()
    groups={}
    for parsed,(band,q,model) in records:
        counts[band]+=1
        quality[q]+=1
        groups.setdefault(band,[]).append((parsed,model))
    result=[]
    # A mixed rating system can produce incompatible band assignments even
    # when each individual band happens to contain only one version.
    all_models={model for _,(_,q,model) in records if q=="DECLARED"}
    for band,items in sorted(groups.items()):
        entry={"strength_band":band,"matches":len(items),"rates":None,
               "status":"INSUFFICIENT_SAMPLE"}
        if band=="UNKNOWN":
            entry["status"]="NO_VALID_RATING_CONTEXT"
        elif len(all_models)>1:
            entry["status"]="MIXED_RATING_MODELS"
        elif len(items)>=10:
            t=_totals([parsed for parsed,_ in items])
            entry.update(status="DESCRIPTIVE_ONLY",rates={
                name:{"pre_xg_per_90":90*t[i]/t[0],
                      "post_xg_per_90":90*t[i+1]/t[1],
                      "rate_difference":_difference(t,i)}
                for name,i in (("dismissed_team",2),("opponent",4))})
        result.append(entry)
    return {"counts":dict(counts),"missing_context":quality["MISSING"],
            "invalid_context":quality["INVALID"],"groups":result,
            "absolute_elo_gap_threshold":100,"min_group_matches":10,
            "rating_versions_count":len(all_models),"ratings_authenticated":False,
            "confounding_adjusted":False,"descriptive_only":True}


def summarize(rows):
    """Return aggregate research only; never exposes individual fixtures."""
    result={"status":"HOLD","production_recommendations":"DISABLED",
            "source_authenticated":False,"model_calibrated":False,
            "causal_effect_estimated":False,"verified_forward_sample_credit":0,
            "positive_ev_verified":False,"descriptive_only":True,
            "accepted_matches":0,"rejected":{},"dismissed_team":None,
            "opponent":None,"small_sample":True,"min_exposure_minutes":MIN_EXPOSURE,
            "min_matches_for_descriptive_flag":MIN_MATCHES,
            "selection_bias_not_ruled_out":True,
            "score_state_and_team_strength_adjusted":False,
            "uncertainty":_uncertainty([]),"exposure_sensitivity":_sensitivity([]),
            "influence":None,"tactical_strata":_strata([]),
            "strength_strata":_strength_strata([])}
    if not isinstance(rows,list) or len(rows)>MAX_MATCHES:
        result["rejected"]={"INVALID_BATCH":1}
        return result
    keyed=[]
    rejects=Counter()
    for row in rows:
        if (not isinstance(row,dict) or type(row.get("match_id")) is not int
                or not 0<row["match_id"]<2**63):
            rejects["INVALID_MATCH_ID"]+=1
            continue
        keyed.append(row)
    counts=Counter(row["match_id"] for row in keyed)
    accepted=[]
    contexts=[]
    strength_contexts=[]
    for row in sorted(keyed,key=lambda item:item['match_id']):
        if counts[row["match_id"]]!=1:
            rejects["DUPLICATE_MATCH"]+=1
            continue
        try:
            parsed=_fixture(row)
            context=_context(row,parsed)
            strength=_strength_context(row)
            accepted.append(parsed)
            contexts.append((parsed,context))
            strength_contexts.append((parsed,strength))
        except (ValueError,KeyError,TypeError,OverflowError) as exc:
            reason=str(exc)
            rejects[reason if reason.isupper() and len(reason)<60 else "INVALID_RECORD"]+=1
    result.update(accepted_matches=len(accepted),rejected=dict(rejects),
                  small_sample=len(accepted)<MIN_MATCHES)
    result.update(uncertainty=_uncertainty(accepted),
                  exposure_sensitivity=_sensitivity(accepted),
                  influence=_influence(accepted),tactical_strata=_strata(contexts),
                  strength_strata=_strength_strata(strength_contexts))
    if accepted:
        totals=_totals(accepted)
        pre,post=totals[:2]
        for name,i in (("dismissed_team",2),("opponent",4)):
            a,b=90*totals[i]/pre,90*totals[i+1]/post
            result[name]={"pre_minutes":pre,"post_minutes":post,
                          "pre_xg_per_90":a,"post_xg_per_90":b,
                          "rate_difference":b-a,
                          "post_pre_ratio":b/a if a>0 else None}
    return result
