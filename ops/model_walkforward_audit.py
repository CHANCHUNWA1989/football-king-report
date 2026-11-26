"""Research-only weekly prequential 1X2 model selection, not release evidence."""
from datetime import datetime, timezone, timedelta
from math import isfinite, log


def stamp(v):
    if not isinstance(v, str):
        raise ValueError('timestamp')
    t = datetime.fromisoformat(v.replace('Z', '+00:00'))
    if t.utcoffset() is None:
        raise ValueError('timezone')
    return t.astimezone(timezone.utc)


def evaluate(rows, candidates, minimum=60, improvement=.01):
    """Freeze selection per UTC week using strictly earlier settled fixtures.

    All rows must contain identical fixed candidate roster plus baseline.
    Timestamps are caller claims, not proof of prospective sealing.
    """
    if not isinstance(candidates, (list, tuple)) or not 1 <= len(candidates) <= 8 or any(not isinstance(x,str) or not x.strip() or x=='baseline' for x in candidates) or len(set(candidates))!=len(candidates):
        raise ValueError('candidate roster')
    if type(minimum) is not int or minimum<1 or type(improvement) not in (int,float) or not isfinite(improvement) or improvement<0:
        raise ValueError('selection settings')
    if not isinstance(rows,(list,tuple)) or len(rows)>10000:
        raise ValueError('rows')
    roster=['baseline']+sorted(candidates)
    seen=set(); prepared=[]
    for r in rows:
        k=r['fixture']
        if not isinstance(k,str) or not k.strip() or k in seen:
            raise ValueError('fixture identity')
        seen.add(k)
        kickoff, cutoff, final=map(stamp,(r['kickoff'],r['cutoff'],r['settled_at']))
        if not cutoff<kickoff<final:
            raise ValueError('chronology')
        y=r['outcome']
        if type(y) is not int or y not in (0,1,2) or set(r['forecasts'])!=set(roster):
            raise ValueError('outcome or roster')
        scores={}
        for name,p in r['forecasts'].items():
            if not isinstance(p,(list,tuple)) or len(p)!=3 or any(type(x) not in (int,float) or not isfinite(x) or not 0<=x<=1 for x in p) or abs(sum(p)-1)>1e-9:
                raise ValueError('probabilities')
            scores[name]=(-log(max(p[y],1e-12)),sum((x-(i==y))**2 for i,x in enumerate(p)))
        week=(cutoff-timedelta(days=cutoff.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
        prepared.append((week,final,k,scores))
    prepared.sort(key=lambda x:(x[0],x[2]))
    settlements=sorted(prepared,key=lambda x:(x[1],x[2]))
    historical={m:0.0 for m in roster}; pos=0; choices={}; totals=[0.0,0.0]; counts=dict.fromkeys(roster,0)
    for week,_,_,scores in prepared:
        if week not in choices:
            while pos<len(settlements) and settlements[pos][1]<week:
                for m in roster: historical[m]+=settlements[pos][3][m][0]
                pos+=1
            best=min(roster,key=lambda m:(historical[m],m!='baseline',m))
            chosen=best if pos>=minimum and (historical['baseline']-historical[best])/pos>improvement else 'baseline'
            choices[week]=(chosen,pos)
        chosen,_=choices[week]; counts[chosen]+=1
        for i in range(2): totals[i]+=scores['baseline'][i]-scores[chosen][i]
    n=len(prepared)
    return dict(state='HOLD',production_enabled=False,certified_cases=0,fixtures=n,selection_counts=counts,weekly=[dict(week=w.isoformat(),model=m,prior_settled=n0) for w,(m,n0) in choices.items()],log_loss_delta=totals[0]/n if n else None,brier_delta=totals[1]/n if n else None)
