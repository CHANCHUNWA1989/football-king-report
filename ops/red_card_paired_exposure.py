"""Offline descriptive comparison of paired within-fixture shot xG exposure.

Input is private regulation-dismissal bucket output, e.g. PR #680 replay.
No source authentication, causal estimation, coefficient fitting or publication.
Only one permanent dismissal and >=15 minutes in each state are admitted.
"""
import math
from collections import Counter

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
            "score_state_and_team_strength_adjusted":False}
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
    for row in keyed:
        if counts[row["match_id"]]!=1:
            rejects["DUPLICATE_MATCH"]+=1
            continue
        try:
            accepted.append(_fixture(row))
        except (ValueError,KeyError,TypeError,OverflowError) as exc:
            reason=str(exc)
            rejects[reason if reason.isupper() and len(reason)<60 else "INVALID_RECORD"]+=1
    result.update(accepted_matches=len(accepted),rejected=dict(rejects),
                  small_sample=len(accepted)<MIN_MATCHES)
    if accepted:
        totals=[math.fsum(row[i] for row in accepted) for i in range(6)]
        pre,post=totals[:2]
        for name,i in (("dismissed_team",2),("opponent",4)):
            a,b=90*totals[i]/pre,90*totals[i+1]/post
            result[name]={"pre_minutes":pre,"post_minutes":post,
                          "pre_xg_per_90":a,"post_xg_per_90":b,
                          "rate_difference":b-a,
                          "post_pre_ratio":b/a if a>0 else None}
    return result
