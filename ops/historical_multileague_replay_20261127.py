"""Pinned retrospective three-league replay; not prospective evidence."""
from collections import defaultdict
from datetime import timedelta
from math import fsum
from pathlib import Path
from ops.historical_season_replay_20261127 import load_season,replay_pairs,METRICS

SOURCE="https://github.com/openfootball/football.json"
MANIFEST={
    "EN":("en.1.json",380,"f62b11dfaf06cffd1236c2777caebb880a0cfea1","504f2e732fbc3c9caeb98e4382b13b094453b840"),
    "DE":("de.1.json",306,"2c41078e751d914f24bfe7e55c5567cea70a4aee","9921b1d8485429913ff6d161500beb519d8b0e51"),
    "FR":("fr.1.json",306,"a5c5c479bd14c4581931219a41687d9938e4dc1e","8bc6ec90c62fa423386ec60473cfa6236419a636"),
}
DRAWS=2000
SEED=20261127

def week_bootstrap(pairs):
    groups=defaultdict(list)
    for day,delta in pairs:
        groups[day-timedelta(days=day.weekday())].append(delta)
    blocks=[(len(groups[k]),tuple(fsum(v[i] for v in groups[k]) for i in range(3)))
            for k in sorted(groups)]
    if len(pairs)<100 or len(blocks)<20:
        return {"weeks":len(blocks),"intervals":None,"status":"INSUFFICIENT_SAMPLE"}
    state=SEED
    samples=[[],[],[]]
    for _ in range(DRAWS):
        selected=[]
        for _ in blocks:
            state=(1664525*state+1013904223)&0xffffffff
            selected.append(blocks[state*len(blocks)//4294967296])
        n=sum(b[0] for b in selected)
        for i in range(3):
            samples[i].append(fsum(b[1][i] for b in selected)/n)
    def q(xs,p):
        xs=sorted(xs); j=(len(xs)-1)*p;i=int(j)
        return xs[i]+(xs[i+1]-xs[i])*(j-i)
    return {"weeks":len(blocks),"draws":DRAWS,"seed":SEED,
            "intervals":{m:[q(samples[i],.025),q(samples[i],.975)] for i,m in enumerate(METRICS)},
            "status":"EXPLORATORY_ONLY"}

def run(root):
    reports={};pairs=[]
    for league,(name,n,train_blob,test_blob) in MANIFEST.items():
        train=load_season((root/"2023-24"/name).read_bytes(),train_blob)
        test=load_season((root/"2024-25"/name).read_bytes(),test_blob)
        if len(train)!=n or len(test)!=n:
            raise ValueError("incomplete pinned season")
        report,rows=replay_pairs(train,test)
        reports[league]=report
        pairs.extend(rows)
    n=sum(r["test"] for r in reports.values())
    means={side:{m:fsum(r[side][m]*r["test"] for r in reports.values())/n for m in METRICS}
           for side in ("baseline","challenger")}
    return {"source":SOURCE,"train":sum(r["train"] for r in reports.values()),
            "test":n,"leagues":reports,**means,
            "correct":[sum(r["correct"][i] for r in reports.values()) for i in (0,1)],
            "unseen_team_fixtures":sum(r["unknown_team_fixtures"] for r in reports.values()),
            "bootstrap":week_bootstrap(pairs),"retrospective_only":True,
            "prospective_verified":False,"confidence_interval_verified":False,
            "positive_ev_verified":False,"deployment":"HOLD","recommendations":"DISABLED"}

if __name__=="__main__":
    from argparse import ArgumentParser
    from json import dumps
    p=ArgumentParser()
    p.add_argument("root",type=Path,help="local directory containing the pinned season files")
    print(dumps(run(p.parse_args().root),indent=2))
