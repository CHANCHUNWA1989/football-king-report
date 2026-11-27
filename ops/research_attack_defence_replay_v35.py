"""Fixed-rule retrospective attack/defence experiment, never a sealed forecast.

Archive capture clocks are unauthenticated and cohort selection is retrospective.
Use only recorded final candidates strictly before original forecast minus delay.
"""
from collections import defaultdict,Counter
from datetime import datetime,timedelta,timezone
import hashlib
import json
import math
from pathlib import Path
from .research_candidate_gap_v6 import stamp
from .research_missing_fixture_discovery_v16 import candidates
from .research_live_intake_v4 import MAX_BYTES
from .research_archive_score_recovery_v14 import archive_snapshots
from .research_two_publisher_recovery_v15 import secondary_snapshots
from .research_calendar_gap_priority_v33 import selectors
from .research_supplemental_history_v32 import inventory
from .research_multimodel_v1 import probabilities,score_matrix

# Fixed research assumptions, not optimized against these outcomes.
LEAGUE_PRIOR=10
TEAM_PRIOR=5
HOME_BASE=1.4
AWAY_BASE=1.1
DELAYS=(0,6,24)
LABELS=("home","draw","away")

def vec(h,a):
    p=probabilities(score_matrix(h,a))
    return [p[x] for x in LABELS]

def rates(history,key):
    league,home,away,_=key
    matches=[(k,s) for _,k,s in history if k[0]==league]
    n=len(matches)
    lh=(LEAGUE_PRIOR*HOME_BASE+sum(s[0] for _,s in matches))/(LEAGUE_PRIOR+n)
    la=(LEAGUE_PRIOR*AWAY_BASE+sum(s[1] for _,s in matches))/(LEAGUE_PRIOR+n)
    mean=(lh+la)/2
    def factors(team):
        games=[s if k[1]==team else s[::-1] for k,s in matches if team in k[1:3]]
        denom=(len(games)+TEAM_PRIOR)*mean
        return ((sum(s[0] for s in games)+TEAM_PRIOR*mean)/denom,
                (sum(s[1] for s in games)+TEAM_PRIOR*mean)/denom,len(games))
    ha,hd,hn=factors(home);aa,ad,an=factors(away)
    clamp=lambda x:min(4.0,max(.2,x))
    return clamp(lh*ha*ad),clamp(la*aa*hd),(len(history),n,hn,an)

def eligible(pool,forecast,delay):
    return [item for item in pool if item[0]+timedelta(hours=delay)<forecast]

def metrics(pairs):
    if not pairs:return {"n":0,"brier":None,"log_loss":None,"accuracy":None}
    n=len(pairs)
    return {"n":n,"brier":sum(sum((v-int(i==y))**2 for i,v in enumerate(p)) for p,y in pairs)/n,
            "log_loss":sum(-math.log(max(p[y],1e-15)) for p,y in pairs)/n,
            "accuracy":sum(max(range(3),key=lambda i:p[i])==y for p,y in pairs)/n}

def replay(raw,inv):
    rows=candidates(raw)
    if inv["ledger_sha256"]!=hashlib.sha256(raw).hexdigest() or inv["training_admission"] is not False:
        raise ValueError("invalid source inventory")
    data=inv["replay_inputs"]
    base=data["base"];extra=data["extra"];targets=data["targets"];expanded=base+extra
    keys=[k for _,k,_ in expanded]
    if len(set(keys))!=len(keys) or any(k not in rows for _,k,_ in base) or any(k in rows for _,k,_ in extra):
        raise ValueError("invalid history partition")
    for t,k,s in expanded:
        if t<k[3]+timedelta(minutes=90) or len(s)!=2 or any(type(v) is not int or not 0<=v<=30 for v in s):
            raise ValueError("invalid final candidate")
        if k in rows and (0 if s[0]>s[1] else 1 if s[0]==s[1] else 2)!=rows[k]["y"]:
            raise ValueError("outcome conflict")
    if len({k for _,k in targets})!=len(targets) or any(k not in {p[1] for p in base} or f!=stamp(rows[k]["forecast_utc"]) or f>k[3]-timedelta(minutes=10) for f,k in targets):
        raise ValueError("invalid forecast targets")
    # Freeze one target roster using expanded 24h support, without looking at target outcomes.
    strict=[]
    for f,k in targets:
        _,_,n=rates(eligible(expanded,f,24),k)
        if n[0]>=30 and n[1]>=5 and min(n[2:])>=3:strict.append((f,k))
    if len(strict)!=inv["scenarios"]["24"]["expanded"]["all_three_thresholds"]:
        raise ValueError("readiness count mismatch")
    def evaluate(cohort,delay):
        pairs=defaultdict(list)
        for f,k in sorted(cohort):
            r=rows[k];y=r["y"]
            for name,pool in (("original_history",base),("expanded_history",expanded)):
                h,a,_=rates(eligible(pool,f,delay),k)
                pairs[name].append((vec(h,a),y))
            pairs["fixed_poisson"].append((vec(HOME_BASE,AWAY_BASE),y))
            # Original market vector may have rounding; normalize identically for scoring.
            m=r["m"];pairs["recorded_market"].append(([v/sum(m) for v in m],y))
        return {name:metrics(pairs[name]) for name in ("original_history","expanded_history","fixed_poisson","recorded_market")}
    return {"schema":"fixed_attack_defence_replay-v35","status":"HOLD","production_recommendations":"DISABLED",
            "ledger_sha256":inv["ledger_sha256"],"history_count":len(expanded),"targets":len(targets),
            "strict_24h_targets":len(strict),"strict_by_league":dict(Counter(k[0] for _,k in strict)),
            "scenarios":{str(d):{"all":evaluate(targets,d),"fixed_strict_24h_cohort":evaluate(strict,d)} for d in DELAYS},
            "fixed_parameters":{"league_prior":LEAGUE_PRIOR,"team_prior":TEAM_PRIOR,"home":HOME_BASE,"away":AWAY_BASE},
            "hyperparameters_tuned":False,"historical_reconstruction_only":True,"metrics_descriptive_only":True,
            "selection_bias_possible":True,"archive_timestamps_authenticated":False,"market_same_cutoff_proven":False,
            "authenticated_samples":0,"independent_oos_proven":False,"training_admission":False,"model_promotion_allowed":False}

def from_root(root,*,as_of):
    with (root/"evidence/settled.json").open("rb") as f:raw=f.read(MAX_BYTES+1)
    rows=candidates(raw)
    a,_=selectors(rows,primary=True);b,_=selectors(rows,primary=False)
    inv=inventory(raw,archive_snapshots(root/"sources/live_germany/history",a),
        secondary_snapshots(root/"sources/history",b),as_of=as_of,include_replay_inputs=True)
    return replay(raw,inv)
