"""Live prospective research ledger. Local hashes are not external attestations."""
from copy import deepcopy
from datetime import timedelta
import math
import random
from .research_unified_live_v2 import forecast, verify_report, digest, utc, text, integer
from .research_multimodel_v1 import multiclass_brier, log_loss

SCHEMA="live-evidence-v3"
KEYS=("home","draw","away")

def seal(snapshot, prior, *, as_of, captured_at, model_release):
    """Replayable bundle; supplied capture clock and release remain untrusted."""
    if utc(captured_at)!=utc(as_of):
        raise ValueError("capture clock mismatch")
    text(model_release)
    r=forecast(snapshot,prior,as_of=as_of)
    if not verify_report(r) or "dynamic" not in r or "baseline" not in r:
        raise ValueError("complete live probability report required")
    if "hypothetical_ev" not in r:
        raise ValueError("complete synchronized research snapshot required")
    body=dict(schema=SCHEMA,event_id=snapshot["event_id"],as_of=utc(as_of).isoformat(),
              captured_at=utc(captured_at).isoformat(),model_release=model_release,
              snapshot=deepcopy(snapshot),prior=deepcopy(prior),report=r,
              status="HOLD",production="DISABLED")
    body["sha256"]=digest(body)
    return body

def verify_bundle(bundle):
    try:
        body=dict(bundle); claimed=body.pop("sha256")
        if digest(body)!=claimed or body["schema"]!=SCHEMA:
            return False
        replay=seal(body["snapshot"],body["prior"],as_of=body["as_of"],
                    captured_at=body["captured_at"],model_release=body["model_release"])
        return replay["sha256"]==claimed and verify_report(body["report"])
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError):
        return False

def settle(bundle, observations, *, as_of):
    """Structural two-origin final-score agreement; not source authentication."""
    if not verify_bundle(bundle):
        raise ValueError("bundle replay failed")
    if not isinstance(observations,list) or len(observations)!=2:
        raise ValueError("two final observations required")
    forecast_at=utc(bundle["as_of"])
    kickoff=utc(bundle["snapshot"]["kickoff"])
    now=utc(as_of)
    identities=[]; scores=[]; finishes=[]
    for r in observations:
        if r["event_id"]!=bundle["event_id"] or r["status"]!="FT" or r["scope"]!="regulation":
            raise ValueError("fixture or final status mismatch")
        source,origin=text(r["source"]).casefold(),text(r["origin"]).casefold()
        text(r["evidence_ref"])
        finished,updated,captured=map(utc,(r["finished_at"],r["updated"],r["captured"]))
        if not kickoff+timedelta(minutes=90)<=finished or not forecast_at<finished<=updated<=captured<=now:
            raise ValueError("impossible final chronology")
        identities.append((source,origin))
        scores.append((integer(r["home"],0,30),integer(r["away"],0,30)))
        finishes.append(finished)
    if any(identities[0][i]==identities[1][i] for i in (0,1)) or scores[0]!=scores[1]:
        raise ValueError("conflicting or duplicate result origin")
    if abs((finishes[0]-finishes[1]).total_seconds())>300:
        raise ValueError("final clock disagreement")
    h,a=scores[0]
    old_h,old_a=bundle["report"]["state"][:2]
    if h<old_h or a<old_a:
        raise ValueError("score correction requires manual review")
    outcome="home" if h>a else ("away" if a>h else "draw")
    body=dict(schema=SCHEMA,event_id=bundle["event_id"],bundle_sha256=bundle["sha256"],
              observed_at=now.isoformat(),observations=deepcopy(observations),
              final_score=[h,a],outcome=outcome,status="HOLD",production="DISABLED",
              source_authenticity_verified=False)
    body["sha256"]=digest(body)
    return body

def _bins(rows,label,key):
    bins=[]
    for index in range(10):
        group=[(p[key],float(y==key)) for p,y in rows[label] if min(9,int(p[key]*10))==index]
        if group:
            bins.append(dict(bin=index,count=len(group),
                             mean_probability=sum(x for x,_ in group)/len(group),
                             observed_frequency=sum(y for _,y in group)/len(group)))
    return bins

def evaluate(pairs, *, model_release, cohort_start, cohort_end, as_of):
    """One fixed minute band per fixture; descriptive metrics, not certified OOS."""
    start,end,now=map(utc,(cohort_start,cohort_end,as_of))
    if not start<end<=now:
        raise ValueError("invalid cohort")
    text(model_release)
    seen=set(); dates={}; rows={"baseline":[],"dynamic":[]}
    losses={"baseline":[],"dynamic":[]}
    for bundle,result in pairs:
        if not verify_bundle(bundle) or bundle["model_release"]!=model_release:
            raise ValueError("model or bundle mismatch")
        if result!=settle(bundle,result["observations"],as_of=result["observed_at"]):
            raise ValueError("settlement replay failed")
        when=utc(bundle["as_of"])
        minute=bundle["report"]["minute"]
        if not start<=when<end or utc(result["observed_at"])>now or not 20<=minute<30:
            raise ValueError("outside fixed 20-30 minute cohort or future result")
        event=bundle["event_id"]
        if event in seen:
            raise ValueError("duplicate fixture")
        seen.add(event)
        y=result["outcome"]
        vals=[]
        for label in rows:
            p={k:bundle["report"][label][k] for k in KEYS}
            rows[label].append((p,y))
            loss=(multiclass_brier(p,y),log_loss(p,y))
            losses[label].append(loss); vals.append(loss)
        day=utc(bundle["snapshot"]["kickoff"]).date().isoformat()
        dates.setdefault(day,[]).append(tuple(vals[1][i]-vals[0][i] for i in (0,1)))
    n=len(seen)
    if not n:
        raise ValueError("empty cohort")
    def means(values):
        return [sum(v[i] for v in values)/len(values) for i in (0,1)]
    baseline=means(losses["baseline"]); dynamic=means(losses["dynamic"])
    delta=[dynamic[i]-baseline[i] for i in (0,1)]
    # Day-cluster bootstrap: resample whole UTC match days, weighted by sampled fixture count.
    # Fixed seed and thresholds for repeatability, not statistical qualification.
    clusters=[dates[k] for k in sorted(dates)]
    intervals=None
    if len(clusters)>=20 and n>=300:
        rng=random.Random(20261127)
        replicates=[means([v for _ in clusters for v in rng.choice(clusters)]) for _ in range(1000)]
        intervals=[]
        for i in (0,1):
            values=sorted(v[i] for v in replicates)
            intervals.append([values[25],values[974]])
    return dict(schema=SCHEMA,status="HOLD",production="DISABLED",n=n,days=len(clusters),
                minute_band=[20,30],metrics={"baseline":baseline,"dynamic":dynamic,"delta":delta,
                "order":["brier","log_loss"],"descriptive_cluster_bootstrap_ci95":intervals},
                reliability={label:{k:_bins(rows,label,k) for k in KEYS} for label in rows},
                external_anchor_verified=False,source_authenticity_verified=False,
                independent_oos_proven=False,cohort_completeness_proven=False,
                calibrated=False,qualified_for_production=False)
