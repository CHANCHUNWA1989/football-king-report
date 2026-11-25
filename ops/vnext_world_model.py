"""V11.1 continuous-time competing-event Monte Carlo challenger.
Exact exponential waiting times for piecewise-constant state hazards, not a
trained neural point process. No actual xG or authenticated event feed.
"""
import math
import random
from collections import Counter
from inplay_state_challenger_vnext import predict, remaining_matrix, _rate
from score_distribution_vnext import one_x_two, market_distribution, validate_matrix
from live_snapshot_adapter import hold
from vnext_live_evidence_cut import audit_cut

PATHS=8192
SEED=20261126
MAX_EVENTS=70
SCORE_COEF=.075
CARD_COEF=.20
FUTURE_CARD_RATE=.10 # per team per 90 minutes, illustrative only
CLASSES=("HOME","DRAW","AWAY")

def hazards(home_rate,away_rate,h,a,rh,ra,*,score_coef=SCORE_COEF,card_coef=CARD_COEF,card_rate=FUTURE_CARD_RATE):
    gap=max(-4,min(4,h-a))
    change=-score_coef*gap+card_coef*(ra-rh)
    return (home_rate/90*math.exp(change),away_rate/90*math.exp(-change),
            card_rate/90 if rh<3 else 0.,card_rate/90 if ra<3 else 0.)

def sample_path(rng,hrate,arate,minute,score,cards,*,score_coef=SCORE_COEF,
                card_coef=CARD_COEF,card_rate=FUTURE_CARD_RATE):
    """Internal single validated-state path shared with particle challenger."""
    t=float(minute);h,a=score;rh,ra=cards;events=0;first_event=None
    while True:
        rates=hazards(hrate,arate,h,a,rh,ra,score_coef=score_coef,
                      card_coef=card_coef,card_rate=card_rate)
        total=math.fsum(rates)
        t+=rng.expovariate(total)
        if t>=90:break
        events+=1
        if events>MAX_EVENTS:raise ValueError("SIMULATION_EVENT_LIMIT")
        u=rng.random()*total;cum=0.;choice=None
        for i,value in enumerate(rates):
            cum+=value
            if u<cum:
                choice=i;break
        if choice is None:choice=max(i for i,value in enumerate(rates) if value>0)
        if first_event is None:first_event=choice
        if choice==0:h+=1
        elif choice==1:a+=1
        elif choice==2:rh+=1
        else:ra+=1
    return h,a,rh,ra,first_event

def simulate(home_rate,away_rate,minute,score,cards,*,paths=PATHS,seed=SEED,
             score_coef=SCORE_COEF,card_coef=CARD_COEF,card_rate=FUTURE_CARD_RATE):
    hrate,arate=_rate(home_rate),_rate(away_rate)
    if (type(minute) is not int or not 0<=minute<90
        or type(paths) is not int or not 1024<=paths<=32768
        or type(seed) is not int or type(score) not in (tuple,list) or len(score)!=2
        or type(cards) not in (tuple,list) or len(cards)!=2
        or any(type(x) is not int or not 0<=x<=10 for x in score)
        or any(type(x) is not int or not 0<=x<=3 for x in cards)
        or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=.25
               for x in (score_coef,card_coef,card_rate))):
        raise ValueError("INVALID_EVENT_SIMULATION")
    rng=random.Random(seed);counts=Counter();first=Counter();card_paths=0
    for _ in range(paths):
        h,a,rh,ra,first_event=sample_path(rng,hrate,arate,minute,score,cards,
            score_coef=score_coef,card_coef=card_coef,card_rate=card_rate)
        counts[h,a]+=1
        first[first_event]+=1
        card_paths+=int(rh>cards[0] or ra>cards[1])
    height=max(h for h,a in counts)+1;width=max(a for h,a in counts)+1
    grid=tuple(tuple(counts[i,j]/paths for j in range(width)) for i in range(height))
    validate_matrix(grid)
    return grid,{"paths":paths,"seed":seed,
        "first_event":{k:first[i]/paths for i,k in enumerate(("HOME_GOAL","AWAY_GOAL","HOME_RED","AWAY_RED"))}|{"NO_EVENT":first[None]/paths},
        "additional_red_card_path_probability":card_paths/paths}

def wilson(p,n):
    # Monte Carlo sampling uncertainty ONLY, not model predictive validity.
    z=1.959963984540054;d=1+z*z/n
    center=(p+z*z/(2*n))/d
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [max(0.,center-half),min(1.,center+half)]

def research_cut(envelope,snapshot,expected_digest,now):
    """Admit only existing structural evidence cuts; do not change V9 outputs."""
    try:
        checked=audit_cut(envelope,snapshot,expected_digest,now)
        if checked.get("cut_status")!="STRUCTURAL_RESEARCH_ONLY":
            return hold("WORLD_MODEL_CUT_REJECTED")
        m=envelope["model"];pre=m["prematch"]
        base=predict(m)
        grid,diagnostics=simulate(pre["expected_home_goals"],pre["expected_away_goals"],
            m["minute_elapsed"],[m["score_home"],m["score_away"]],[m["red_home"],m["red_away"]])
        p=one_x_two(grid)
        quote=snapshot["quote"]
        market=market_distribution(grid,market=quote["market"],side=quote["selection"].upper(),line=quote["line"])
        trailing="HOME" if m["score_home"]<m["score_away"] else "AWAY" if m["score_away"]<m["score_home"] else None
        return {**hold("UNAUTHENTICATED_WORLD_MODEL_RESEARCH"),
                "world_model_status":"STRUCTURAL_RESEARCH_ONLY",
                "cut_sha256_unattested":expected_digest,"probabilities_1x2":p,
                "market_distribution":market,"static_reference_1x2":base["fulltime_probabilities"],
                "simulation":diagnostics,"monte_carlo_sampling_ci_95":{k:wilson(p[k],PATHS) for k in CLASSES},
                "trailing_team":trailing,"comeback_win_probability":p[trailing] if trailing else None,
                "score_matrix":[list(row) for row in grid],
                "model_uncertainty_calibrated":False,"future_card_hazard_fitted":False,
                "stoppage_time_not_modelled":True,"actual_xg":None,"actual_quote_verified":False,
                "verified_forward_sample_credit":0,"model_edge":None}
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return hold("INVALID_WORLD_MODEL_RESEARCH")
