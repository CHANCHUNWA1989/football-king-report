"""Offline five-grade challenger comparison; descriptive only, never release evidence.

Rows must be pre-paired by an upstream fixture/line/cutoff validator. No odds,
source authentication, or production permissions are inferred here.
"""
from collections import defaultdict
from datetime import datetime, timezone
from math import isfinite, log
from random import Random

GRADES = ('full_loss', 'half_loss', 'push', 'half_win', 'full_win')


def _prob(v):
    if not isinstance(v, (list, tuple)) or len(v) != 5:
        raise ValueError('five probabilities required')
    if any(type(p) not in (int, float) or not isfinite(p) or not 0 <= p <= 1 for p in v):
        raise ValueError('invalid probability')
    if abs(sum(v) - 1) > 1e-9:
        raise ValueError('probability sum')
    return v


def compare(rows, draws=2000, seed=714):
    """Positive paired differences favour challenger; UTC week cluster resampling.

    One row per fixture globally to avoid correlated duplicate market weighting.
    All malformed/duplicate input aborts; no silently selected favourable subset.
    Intervals are exploratory, not coverage guarantees or certified evidence.
    """
    if type(draws) is not int or not 200 <= draws <= 10000:
        raise ValueError('draws out of range')
    if not isinstance(rows, (list, tuple)) or len(rows) > 10000:
        raise ValueError('bounded row sequence required')
    seen, blocks, leagues = set(), defaultdict(list), set()
    for r in rows:
        if not isinstance(r, dict):
            raise ValueError('row')
        key, league = r.get('fixture'), r.get('league')
        if any(not isinstance(s, str) or not s.strip() or s != s.strip() or len(s)>200 for s in (key, league)):
            raise ValueError('identity')
        if key in seen:
            raise ValueError('duplicate fixture')
        seen.add(key)
        leagues.add(league)
        t = datetime.fromisoformat(r['kickoff'].replace('Z', '+00:00'))
        if t.utcoffset() is None:
            raise ValueError('timezone required')
        week = t.astimezone(timezone.utc).isocalendar()[:2]
        y = GRADES.index(r['grade'])
        b, c = _prob(r['baseline']), _prob(r['challenger'])
        # Multiclass Brier and clipped log loss; identical scoring for both.
        db = sum((p-(i==y))**2 for i,p in enumerate(b))-sum((p-(i==y))**2 for i,p in enumerate(c))
        dl = log(max(c[y], 1e-12))-log(max(b[y], 1e-12))
        blocks[week].append((db,dl))
    n=len(seen)
    stats=[(len(v),sum(x[0] for x in v),sum(x[1] for x in v)) for _,v in sorted(blocks.items())]
    out={'state':'HOLD','production_enabled':False,'certified_cases':0,'fixtures':n,'weeks':len(stats),'leagues':len(leagues),'brier_delta':None,'log_loss_delta':None,'brier_ci':None,'log_loss_ci':None}
    if not n:
        return out
    out.update(brier_delta=sum(x[1] for x in stats)/n,log_loss_delta=sum(x[2] for x in stats)/n)
    # Provisional minimum for displaying descriptive uncertainty; not a power test.
    if n<60 or len(stats)<12 or len(leagues)<2:
        return out
    rng=Random(seed)
    samples=[[],[]]
    for _ in range(draws):
        chosen=rng.choices(stats,k=len(stats))
        den=sum(x[0] for x in chosen)
        for i in range(2):
            samples[i].append(sum(x[i+1] for x in chosen)/den)
    for field,values in zip(('brier_ci','log_loss_ci'),samples):
        values.sort()
        out[field]=[values[int(.025*(draws-1))],values[int(.975*(draws-1))]]
    return out
