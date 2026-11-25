"""Historical date adapter; retain pinned V5 Elo rates and update algorithm."""
from collections import defaultdict
from types import SimpleNamespace
from ops import v5_dynamic_elo as elo,v8_multiseason as v
import json

def replay(doc,season):
    if not isinstance(doc,dict) or len(doc.get("matches",[]))>elo.MAX_ROWS:raise ValueError("ARCHIVE_LIMIT")
    rows,_,_=v.parse(json.dumps(doc,allow_nan=False).encode(),season)
    groups=defaultdict(list)
    for r in rows:groups[r[0]].append(r)
    earlier,ratings,cases=[],{},[]
    for day in sorted(groups):
        batch=groups[day];changes=defaultdict(float)
        for _,h,a,gh,ga in batch:
            base=elo.rates(earlier,day,h,a,ratings,False)
            cand=elo.rates(earlier,day,h,a,ratings,True)
            if base is not None and cand is not None:
                cases.append({"date":day.isoformat(),"home":h,"away":a,"y":0 if gh>ga else 1 if gh==ga else 2,
                              "baseline":elo.probabilities(*base),"candidate":elo.probabilities(*cand)})
            expected=1/(1+10**((ratings.get(a,1500.)-ratings.get(h,1500.)-elo.HOME_ELO)/400))
            observed=1 if gh>ga else .5 if gh==ga else 0
            delta=elo.K*(observed-expected)
            changes[h]+=delta;changes[a]-=delta
        for team,delta in changes.items():ratings[team]=ratings.get(team,1500.)+delta
        earlier.extend(batch)
    return cases
def adapter(season):
    return SimpleNamespace(replay=lambda doc:replay(doc,season))
