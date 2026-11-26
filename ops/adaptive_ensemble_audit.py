"""Offline prequential probability pooling. No source or release certification."""
from datetime import datetime, timezone, timedelta
from math import exp, isfinite, log


def utc(s):
    if not isinstance(s, str):
        raise ValueError('timestamp')
    t = datetime.fromisoformat(s.replace('Z', '+00:00'))
    if t.utcoffset() is None:
        raise ValueError('timezone')
    return t.astimezone(timezone.utc)


def evaluate(rows, models, minimum=60, temperature=0.1, anchor=0.5):
    """Fixed roster; freeze weights at each UTC Monday using earlier settlements.

    Pool probabilities, not odds. Baseline receives at least anchor weight.
    Defaults are exploratory and must be fixed before real evaluation.
    """
    if not isinstance(models, (list, tuple)) or not 1 <= len(models) <= 8 or any(not isinstance(m,str) or not m.strip() or m=='baseline' for m in models) or len(set(models))!=len(models):
        raise ValueError('roster')
    if type(minimum) is not int or minimum<1 or type(temperature) not in (int,float) or not isfinite(temperature) or temperature<0.001 or type(anchor) not in (int,float) or not isfinite(anchor) or not 0<=anchor<=1:
        raise ValueError('settings')
    if not isinstance(rows,(list,tuple)) or len(rows)>10000:
        raise ValueError('rows')
    roster=['baseline']+sorted(models)
    seen=set(); data=[]
    for row in rows:
        key=row['fixture']; y=row['outcome']; p=row['forecasts']
        if not isinstance(key,str) or not key.strip() or key in seen or type(y) is not int or y not in (0,1,2) or set(p)!=set(roster):
            raise ValueError('identity/outcome/roster')
        seen.add(key)
        t,k,f=map(utc,(row['cutoff'],row['kickoff'],row['settled_at']))
        if not t<k<f:
            raise ValueError('chronology')
        for v in p.values():
            if not isinstance(v,(tuple,list)) or len(v)!=3 or any(type(x) not in (int,float) or not isfinite(x) or not 0<=x<=1 for x in v) or abs(sum(v)-1)>1e-9:
                raise ValueError('probability')
        w=(t-timedelta(days=t.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
        data.append((w,f,key,y,p))
    data.sort(key=lambda r:(r[0],r[2])); settled=sorted(data,key=lambda r:(r[1],r[2]))
    sums=dict.fromkeys(roster,0.0); i=0; weeks={}; output=[]; delta=[0.0,0.0]
    for week,_,key,y,p in data:
        if week not in weeks:
            while i<len(settled) and settled[i][1]<week:
                _,_,_,z,q=settled[i]
                for m in roster: sums[m]-=log(max(q[m][z],1e-12))
                i+=1
            weights=dict.fromkeys(roster,0.0); weights['baseline']=1.0
            if i>=minimum:
                best=min(sums.values()); raw={m:exp(-(sums[m]-best)/i/temperature) for m in roster}; den=sum(raw.values())
                weights={m:(1-anchor)*raw[m]/den for m in roster}; weights['baseline']+=anchor
            weeks[week]=(weights,i)
        weights,_=weeks[week]
        q=[sum(weights[m]*p[m][j] for m in roster) for j in range(3)]
        delta[0]+=log(max(q[y],1e-12))-log(max(p['baseline'][y],1e-12))
        delta[1]+=sum((x-(j==y))**2 for j,x in enumerate(p['baseline']))-sum((x-(j==y))**2 for j,x in enumerate(q))
        output.append((key,q))
    n=len(data)
    return dict(state='HOLD',production_enabled=False,certified_cases=0,fixtures=n,weekly=[dict(week=w.isoformat(),weights=v,prior_settled=c) for w,(v,c) in weeks.items()],predictions=output,log_loss_delta=delta[0]/n if n else None,brier_delta=delta[1]/n if n else None)
