"""Offline paired forecast uncertainty; no authenticated prospective evidence."""
from collections import defaultdict
from collections.abc import Mapping
from datetime import timezone
from hashlib import sha256
from json import dumps
from math import fsum
from random import Random
from ops.live_snapshot_market_audit_20261126 import aware
from ops.live_score_challenger_20261127 import paired_evaluate

METRICS=("log_loss","brier","rps")
MIN_FIXTURES=100
MIN_WEEKS=20
DRAWS=2000
SEED=20261127

def _id(x):
    if not isinstance(x,str) or not x or x.strip()!=x:
        raise ValueError("invalid identifier")
    return x

def _utc(x):
    return aware(x).astimezone(timezone.utc)

def _quantile(values, p):
    s=sorted(values)
    index=(len(s)-1)*p
    i=int(index)
    return s[i]+(s[min(i+1,len(s)-1)]-s[i])*(index-i)

def evaluate_holdout(manifest, rows):
    """Fixed complete fixture cohort, predeclared model IDs, UTC week clusters.

    Manifest freeze and model identifiers are assertions, not cryptographic
    proof of publication or fitting history. Percentile bootstrap is exploratory.
    """
    if not isinstance(manifest,Mapping) or not isinstance(rows,list):
        raise ValueError("invalid input")
    freeze=_utc(manifest.get("frozen_at"))
    baseline=_id(manifest.get("baseline_id"))
    challenger=_id(manifest.get("challenger_id"))
    if baseline==challenger:
        raise ValueError("models must differ")
    entries=manifest.get("fixtures")
    if not isinstance(entries,list) or not entries:
        raise ValueError("empty manifest")
    expected={}
    for entry in entries:
        if not isinstance(entry,Mapping):
            raise ValueError("invalid manifest entry")
        fid=_id(entry.get("fixture_id"))
        decision=_utc(entry.get("decision_at"))
        if fid in expected or decision<=freeze:
            raise ValueError("duplicate fixture or decision before freeze")
        expected[fid]=decision
    canonical={"frozen_at":freeze.isoformat(),"baseline_id":baseline,
               "challenger_id":challenger,"fixtures":[
                   [k,v.isoformat()] for k,v in sorted(expected.items())]}
    digest=sha256(dumps(canonical,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    by_week=defaultdict(list)
    seen=set()
    for r in rows:
        if not isinstance(r,Mapping):
            raise ValueError("invalid row")
        fid=_id(r.get("fixture_id"))
        if fid in seen or fid not in expected:
            raise ValueError("duplicate or unregistered fixture")
        decision=_utc(r.get("decision_at"))
        if decision!=expected[fid]:
            raise ValueError("decision mismatch")
        seen.add(fid)
        for name,model in (("baseline",baseline),("challenger",challenger)):
            if r.get(name+"_id")!=model:
                raise ValueError("model mismatch")
            if _utc(r.get(name+"_trained_through"))>freeze:
                raise ValueError("training after manifest freeze")
            if _utc(r.get(name+"_issued_at"))<freeze:
                raise ValueError("forecast issued before manifest freeze")
        result=paired_evaluate([r])["mean_challenger_minus_baseline"]
        week=decision.isocalendar()[:2]
        by_week[week].append(tuple(result[m] for m in METRICS))
    if seen!=set(expected):
        raise ValueError("incomplete cohort")
    blocks=[by_week[k] for k in sorted(by_week)]
    n=len(seen)
    sums=[(len(block),tuple(fsum(v[i] for v in block) for i in range(3))) for block in blocks]
    means={m:fsum(v[1][i] for v in sums)/n for i,m in enumerate(METRICS)}
    result={"n":n,"utc_weeks":len(blocks),"manifest_sha256":digest,
            "mean_challenger_minus_baseline":means,"intervals":None,
            "status":"INSUFFICIENT_SAMPLE","primary_metric":"log_loss",
            "thresholds_provisional":True,"confidence_interval_verified":False,
            "out_of_sample_verified":False,"positive_ev_verified":False,
            "deployment":"HOLD","recommendations":"DISABLED"}
    if n<MIN_FIXTURES or len(blocks)<MIN_WEEKS:
        return result
    rng=Random(SEED)
    draws=[[],[],[]]
    for _ in range(DRAWS):
        selected=[sums[rng.randrange(len(sums))] for _ in sums]
        size=sum(v[0] for v in selected)
        for i in range(3):
            draws[i].append(fsum(v[1][i] for v in selected)/size)
    intervals={m:[_quantile(draws[i],.025),_quantile(draws[i],.975)]
               for i,m in enumerate(METRICS)}
    result.update(intervals=intervals, status="EXPLORATORY_ONLY",
                  bootstrap_draws=DRAWS,bootstrap_seed=SEED,
                  method="paired UTC-week cluster percentile bootstrap",
                  primary_interval_below_zero=intervals["log_loss"][1]<0)
    return result
