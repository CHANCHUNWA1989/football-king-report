"""V11 approximate dynamic Gamma-Poisson attack/defence filter.
Date-only historical research; no fitted latent joint posterior, no actual xG,
no source authentication. Same-day states frozen before any result update.
"""
import math
from collections import defaultdict
from datetime import date
from ops import v5_ensemble_competition as e,v8_multiseason as v
from ops.v5_integration_acceptance import project,summary

PRIOR=8.
HALF_LIFE=180.
MAX_GOALS=65
TAIL=1e-10
MARKETS=(("handicap","home",-.25),("totals","over",2.25))

def mean(state):
    return state[0]/state[1]

def decay(state,day):
    a,b,previous=state
    if previous>day:raise ValueError("FUTURE_STATE")
    w=2**(-(day-previous).days/HALF_LIFE)
    return (PRIOR+w*(a-PRIOR),PRIOR+w*(b-PRIOR),day)

def rate_moments(base,attack,defence):
    # Independent Gamma factors; product matched to a Gamma by first two moments.
    mu=max(.1,min(5.5,base*mean(attack)*mean(defence)))
    relative_variance=1/attack[0]+1/defence[0]+1/(attack[0]*defence[0])
    shape=1/relative_variance
    return mu,shape

def marginal(mu,shape):
    if not all(type(x) in (int,float) and math.isfinite(x) for x in (mu,shape)) or not .1<=mu<=5.5 or not 3.75<=shape<=10000:
        raise ValueError("INVALID_PREDICTIVE_PARAMETERS")
    q=mu/(mu+shape)
    p=[math.exp(shape*math.log1p(-q))]
    for k in range(1,MAX_GOALS+1):
        if 1-math.fsum(p)<=TAIL/4:break
        p.append(p[-1]*(shape+k-1)/k*q)
    mass=math.fsum(p)
    if not 1-TAIL/4<=mass<=1+TAIL/4:raise ValueError("UNBOUNDED_PREDICTIVE_TAIL")
    return [x/mass for x in p]

def score_grid(home,away):
    ph,pa=marginal(*home),marginal(*away)
    g={(i,j):x*y for i,x in enumerate(ph) for j,y in enumerate(pa)}
    if abs(math.fsum(g.values())-1)>1e-9:raise ValueError("MASS")
    return g

def replay(train,test,league,season):
    if league not in v.LEAGUES or len(train)<100 or not test or max(r[0] for r in train)>=min(r[0] for r in test):
        raise ValueError("INVALID_SCOPE")
    days=defaultdict(list);seen=set()
    for row in [*train,*test]:
        d,h,a,x,y=row
        if type(d) is not date or h==a or any(type(n) is not int or not 0<=n<=20 for n in (x,y)) or (d,h,a) in seen:
            raise ValueError("INVALID_FIXTURE")
        seen.add((d,h,a));days[d].append(row)
    cutoff=min(r[0] for r in test)
    # League means fixed from previous season, known before assessment.
    # Training warmup itself is not scored.
    lh=max(.1,min(5.5,math.fsum(r[3] for r in train)/len(train)))
    la=max(.1,min(5.5,math.fsum(r[4] for r in train)/len(train)))
    state={};out=[]
    for day,batch in sorted(days.items()):
        frozen={}
        def get(team,role):
            k=(team,role)
            if k not in frozen:frozen[k]=decay(state.get(k,(PRIOR,PRIOR,day)),day)
            return frozen[k]
        updates=defaultdict(lambda:[0.,0.])
        for _,h,a,x,y in sorted(batch):
            ha,hd,aa,ad=get(h,"attack"),get(h,"defence"),get(a,"attack"),get(a,"defence")
            if day>=cutoff:
                hm,am=rate_moments(lh,ha,ad),rate_moments(la,aa,hd)
                g=score_grid(hm,am)
                p=e.vec(summary(g)["1x2"])
                out.append({"league":league,"season":season,"date":day.isoformat(),"home":h,"away":a,
                    "y":0 if x>y else 1 if x==y else 2,"bayes":p,
                    "home_rate":hm[0],"away_rate":am[0],"home_shape":hm[1],"away_shape":am[1],
                    "score_log_loss":-math.log(max(g.get((x,y),0.),1e-15)),
                    "hypothetical_markets":{str(k):project(g,*k) for k in MARKETS}})
            # Approximate conditional conjugate updates using frozen opponent means.
            for key,goals,exposure in (((h,"attack"),x,lh*mean(ad)),((a,"defence"),x,lh*mean(ha)),
                                       ((a,"attack"),y,la*mean(hd)),((h,"defence"),y,la*mean(aa))):
                updates[key][0]+=goals;updates[key][1]+=exposure
        for k,(goals,exposure) in updates.items():
            a,b,_=frozen[k];state[k]=(a+goals,b+exposure,day)
    return out

def report(data,expert_rows):
    from ops.v9_league_weights import ci
    rows=[];totals=0
    for league in v.LEAGUES:
        tr,te=data["2024-25",league],data["2025-26",league]
        totals+=len(te)
        rows.extend(replay(tr,te,league,"2025-26"))
    def key(r):return (r["league"],*e.key(r))
    index={key(r):r for r in rows}
    if len(index)!=len(rows):raise ValueError("DUPLICATE_BAYES_FIXTURE")
    common=[];seen=set()
    for r in expert_rows:
        if r["season"]!="2025-26":continue
        k=key(r)
        if k in seen or k not in index or index[k]["y"]!=r["y"]:raise ValueError("BAYES_PAIR_MISMATCH")
        seen.add(k)
        common.append({**r,"bayes":index[k]["bayes"]})
    if not common:raise ValueError("NO_COMMON_FIXTURES")
    def metrics(a):
        if not a:return None
        return {k:e.metrics(a,lambda r:r[k]) for k in ("bayes","hybrid","candidate")}
    interval=ci([{**r,"hybrid":r["candidate"],"candidate":r["bayes"]} for r in common])
    return {"schema":"v11-dynamic-gamma-poisson-research-v1","prior":PRIOR,"half_life_days":HALF_LIFE,
        "historical_all_n":len(rows),"all_finished":totals,
        "all_bayes_metrics":e.metrics(rows,lambda r:r["bayes"]),
        "all_score_log_loss":math.fsum(r["score_log_loss"] for r in rows)/len(rows),
        "common_n":len(common),"same_fixture_metrics":metrics(common),
        "per_league":{k:metrics([r for r in common if r["league"]==k]) for k in v.LEAGUES},
        "paired_week_ci_v10_minus_bayes":interval,"approximate_independent_gamma_factors":True,
        "assessment_previously_inspected":True,"prior_day_only":True,"actual_xg_available":False,
        "hypothetical_market_lines_only":True,"prospective_validation":False,
        "verified_forward_sample_credit":0,"automatic_promotion":False,
        "production_recommendations":"DISABLED","status":"HOLD"}
