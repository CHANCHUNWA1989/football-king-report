"""V11.2 sequential importance/resampling for interval-censored match states.
Gamma prior is an illustrative proxy around sealed native joint rates, NOT
the domestic V11 learned state. No claim of source authentication or fit.
"""
import math
import random
from collections import Counter
from inplay_state_challenger_vnext import _rate
from live_snapshot_adapter import hold
from vnext_native_series_replay import replay_series
from vnext_world_model import hazards,sample_path,PATHS,SEED,wilson
from score_distribution_vnext import one_x_two,market_distribution,validate_matrix

PARTICLES=1024
SHAPE=8.
MAX_CUTS=120
ESS_FRACTION=.5
MIN_UNIQUE=128

def prior_draw(rng,rate):
    # Explicit truncated Gamma prior; nominal mean before truncation is rate.
    for _ in range(1000):
        v=rng.gammavariate(SHAPE,rate/SHAPE)
        if .1<=v<=5.5:return v
    raise ValueError("PRIOR_TRUNCATION_FAILED")

def transition_loglik(hr,ar,previous,current):
    """Exact zero/one jump interval likelihood under the V11.1 CTMC.
    Multi-event intervals cannot establish exact order and are withheld.
    """
    dt=current["minute"]-previous["minute"]
    old=(*previous["score"],*previous["red_cards"])
    new=(*current["score"],*current["red_cards"])
    increments=[b-a for a,b in zip(old,new)]
    if dt<=0 or any(x<0 for x in increments) or sum(increments)>1:
        raise ValueError("UNSUPPORTED_EVENT_INTERVAL")
    before=hazards(hr,ar,*old);a=math.fsum(before)
    if not sum(increments):return -a*dt
    k=increments.index(1)
    if before[k]<=0:raise ValueError("IMPOSSIBLE_EVENT")
    b=math.fsum(hazards(hr,ar,*new))
    # Integral of exp(-a*s-b*(dt-s)), stable for equal rates.
    diff=abs(a-b)
    factor=dt if diff<1e-12 else -math.expm1(-diff*dt)/diff
    return math.log(before[k])+math.log(factor)-min(a,b)*dt

def normalize(logweights):
    m=max(logweights);q=[math.exp(x-m) for x in logweights];s=math.fsum(q)
    if not math.isfinite(s) or s<=0:raise ValueError("INVALID_PARTICLE_MASS")
    return [x/s for x in q]

def effective_size(w):
    return 1/math.fsum(x*x for x in w)

def resample(rng,particles,weights):
    # Systematic resampling; keep identities to detect impoverishment.
    n=len(particles);u=rng.random()/n;j=0;c=weights[0];out=[]
    for i in range(n):
        t=u+i/n
        while t>c and j<n-1:
            j+=1;c+=weights[j]
        out.append(particles[j])
    return out

def particle_filter(hr,ar,states,*,seed=SEED):
    hr,ar=_rate(hr),_rate(ar)
    if not 2<=len(states)<=MAX_CUTS:raise ValueError("INSUFFICIENT_INTERVALS")
    rng=random.Random(seed)
    particles=[(prior_draw(rng,hr),prior_draw(rng,ar)) for _ in range(PARTICLES)]
    weights=[1/PARTICLES]*PARTICLES
    steps=[];resampling=0
    for old,new in zip(states,states[1:]):
        logweights=[math.log(max(w,1e-300))+transition_loglik(h,a,old,new)
                    for (h,a),w in zip(particles,weights)]
        weights=normalize(logweights)
        ess=effective_size(weights)
        means=[math.fsum(w*p[k] for p,w in zip(particles,weights)) for k in (0,1)]
        resampled=ess<PARTICLES*ESS_FRACTION
        if resampled:
            particles=resample(rng,particles,weights)
            weights=[1/PARTICLES]*PARTICLES;resampling+=1
        unique=len(set(particles))
        if unique<MIN_UNIQUE:raise ValueError("PARTICLE_IMPOVERISHMENT")
        steps.append({"minute":new["minute"],"posterior_rate_means":means,
                      "ess_before_resample":ess,"resampled":resampled,"unique_particles":unique})
    return particles,weights,steps,resampling

def posterior_grid(particles,weights,state):
    rng=random.Random(SEED+1);counts=Counter()
    for h,a in rng.choices(particles,weights=weights,k=PATHS):
        x,y,_,_,_=sample_path(rng,h,a,state["minute"],state["score"],state["red_cards"])
        counts[x,y]+=1
    height=max(h for h,a in counts)+1;width=max(a for h,a in counts)+1
    grid=tuple(tuple(counts[i,j]/PATHS for j in range(width)) for i in range(height))
    validate_matrix(grid);return grid

def research_series(raw,archive_sha256,*,fixture_id,home_native_id,away_native_id,kickoff_utc,cuts):
    """Condition only on intervals after the first accepted cut; no extrapolated event order."""
    try:
        validated=replay_series(raw,archive_sha256,fixture_id=fixture_id,home_native_id=home_native_id,
            away_native_id=away_native_id,kickoff_utc=kickoff_utc,cuts=cuts)
        if validated.get("series_status")!="STRUCTURAL_RESEARCH_ONLY":
            return hold("PARTICLE_SERIES_REJECTED")
        states=validated["cuts"];pre=cuts[0]["envelope"]["model"]["prematch"]
        p,w,steps,resampling=particle_filter(pre["expected_home_goals"],pre["expected_away_goals"],states)
        grid=posterior_grid(p,w,states[-1]);probs=one_x_two(grid);quote=cuts[-1]["snapshot"]["quote"]
        dist=market_distribution(grid,market=quote["market"],side=quote["selection"].upper(),line=quote["line"])
        return {**hold("UNAUTHENTICATED_PARTICLE_RESEARCH"),
            "particle_status":"STRUCTURAL_RESEARCH_ONLY","fixture_id":fixture_id,
            "archive_sha256_unattested":archive_sha256,"cut_count":len(states),
            "conditioned_intervals":len(steps),"first_cut_minute":states[0]["minute"],
            "particles":PARTICLES,"predictive_paths":PATHS,"resampling_count":resampling,
            "steps":steps,"probabilities_1x2":probs,"market_distribution":dist,
            "score_matrix":[list(row) for row in grid],
            "monte_carlo_sampling_ci_95":{k:wilson(v,PATHS) for k,v in probs.items()},
            "prior_shape":SHAPE,"prior_type":"truncated-gamma-native-joint-rate-proxy",
            "learned_v11_state_connected":False,"prior_to_first_cut_conditioned":False,
            "static_latent_rates_with_sequential_posterior_updates":True,
            "model_uncertainty_calibrated":False,"actual_xg":None,"actual_quote_verified":False,
            "verified_forward_sample_credit":0,"model_edge":None}
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return hold("INVALID_PARTICLE_RESEARCH")
