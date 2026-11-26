"""Fixed retrospective three-league model stress; no promotion or live data."""
import json
import math
from collections import defaultdict
from datetime import date
from itertools import groupby
from urllib.request import Request,build_opener
from live_core_multi_source import blob,checked,row,unique,NoRedirect,LIMIT
from research_strict_json import unique_object,reject_constant
from score_distribution_vnext import score_matrix,one_x_two

SPECS={
    "MX":("mx.1","Liga MX 2024/25","01eb9b765c10372ad3dd5ebe8a2067bfc4376223",340),
    "EPL":("en.1","English Premier League 2024/25","504f2e732fbc3c9caeb98e4382b13b094453b840",380),
    "BL":("de.1","Deutsche Bundesliga 2024/25","9921b1d8485429913ff6d161500beb519d8b0e51",306)}
MODELS=("league_poisson","team_poisson","team_dc","elo_poisson","decay_team")
OUTCOMES=("HOME","DRAW","AWAY")
EPOCH=date(1970,1,1)


def fetch(tag):
    path,name,pin,count=SPECS[tag]
    url=f"https://raw.githubusercontent.com/openfootball/football.json/master/2024-25/{path}.json"
    with build_opener(NoRedirect()).open(Request(url,headers={"Accept":"application/json","User-Agent":"FootballKingResearch/1.0"}),timeout=15) as res:
        if res.geturl()!=url or res.status!=200:
            raise ValueError("HTTP_SOURCE")
        raw=res.read(LIMIT+1)
    if len(raw)>LIMIT or blob(raw)!=pin:
        raise ValueError("BLOB_CHANGED")
    data=json.loads(checked(raw),object_pairs_hook=unique_object,parse_constant=reject_constant)
    if data["name"]!=name:
        raise ValueError("LEAGUE_SCOPE")
    rows=unique([row(m["date"],m["team1"],m["team2"],m["score"]["ft"])
                 for m in data["matches"] if m.get("score",{}).get("ft") is not None])
    if len(rows)!=count or any(not "2024-07-01"<=r[0]<"2025-07-01" for r in rows):
        raise ValueError("COHORT_SCOPE")
    return rows


def clip(x):
    return max(.1,min(5.5,x))


def rates(h,a,H,A):
    return (clip(((h[1]+8*H)/(h[0]+8))*((a[5]+8*H)/(a[3]+8))/H),
            clip(((a[4]+8*A)/(a[3]+8))*((h[2]+8*A)/(h[0]+8))/A))


def update(hist,home,away,x,y):
    h,a=hist[home],hist[away]
    h[0]+=1;h[1]+=x;h[2]+=y
    a[3]+=1;a[4]+=y;a[5]+=x


def paired_ci(groups,draws=2000):
    """Resample calendar-week clusters; descriptive, unadjusted intervals."""
    if len(groups)<2 or type(draws) is not int or draws<40:
        return None
    seed=20261126
    samples=[]
    for _ in range(draws):
        total=n=0
        for _ in groups:
            seed=(seed*1664525+1013904223)&0xffffffff
            delta,count=groups[seed*len(groups)//2**32]
            total+=delta;n+=count
        samples.append(total/n)
    samples.sort()
    return [samples[math.ceil(.025*draws)-1],samples[math.ceil(.975*draws)-1]]


def compare(rows):
    rows=unique(rows)
    hist=defaultdict(lambda:[0.]*6)
    decay=defaultdict(lambda:[0.]*6)
    elo=defaultdict(lambda:1500.)
    n=gh=ga=0
    previous=None
    observations=[]
    for day,g in groupby(rows,key=lambda r:r[0]):
        batch=list(g)
        t=(date.fromisoformat(day)-EPOCH).days
        if previous is not None:
            factor=2**(-(t-previous)/90)
            for v in decay.values():
                for i in range(6):
                    v[i]*=factor
        previous=t
        if n>=50:
            H,A=clip(gh/n),clip(ga/n)
            for _,home,away,x,y in batch:
                hr,ar=rates(hist[home],hist[away],H,A)
                dr,da=rates(decay[home],decay[away],H,A)
                gap=max(-400,min(400,elo[home]-elo[away]))/800
                configs=((H,A,0),(hr,ar,0),(hr,ar,-.08),
                         (clip(H*math.exp(gap)),clip(A*math.exp(-gap)),0),(dr,da,0))
                k="HOME" if x>y else "DRAW" if x==y else "AWAY"
                values=[]
                for h,a,rho in configs:
                    matrix=score_matrix(h,a,rho=rho)
                    p=one_x_two(matrix)
                    u=math.fsum(v for i,r in enumerate(matrix) for j,v in enumerate(r) if i+j<=2)
                    l=math.fsum(v for i,r in enumerate(matrix) for j,v in enumerate(r) if i+j<=1)
                    values.append((-math.log(max(1e-15,p[k])),
                        math.fsum((p[j]-(j==k))**2 for j in OUTCOMES),
                        int(max(OUTCOMES,key=lambda j:p[j])==k),
                        (u-(x+y<=2))**2,(l-(x+y<=1))**2))
                observations.append(((t+3)//7,values))
        changes=defaultdict(float)
        for _,home,away,x,y in batch:
            update(hist,home,away,x,y)
            update(decay,home,away,x,y)
            expected=1/(1+10**(-(elo[home]-elo[away]+65)/400))
            delta=20*((1 if x>y else .5 if x==y else 0)-expected)
            changes[home]+=delta;changes[away]-=delta
            n+=1;gh+=x;ga+=y
        for team,delta in changes.items():
            elo[team]+=delta
    result={}
    count=len(observations)
    weeks=defaultdict(list)
    for w,v in observations:
        weeks[w].append(v)
    for i,m in enumerate(MODELS):
        averages=[math.fsum(v[i][j] for _,v in observations)/count if count else None for j in range(5)]
        groups=[(math.fsum(v[0][0]-v[i][0] for v in vs),len(vs)) for vs in weeks.values()]
        result[m]=dict(zip(("log_loss","brier","accuracy","under25_brier","under15_brier"),averages))
        result[m]["baseline_minus_candidate_log_loss_ci95"]=paired_ci(groups)
    return {"finished_matches":n,"assessment_n":count,"weeks":len(weeks),"models":result}


def main():
    out={"leagues":{k:compare(fetch(k)) for k in SPECS},"historically_reconstructed":True,
         "assessment_previously_inspected":True,"cross_season_verified":False,
         "model_calibrated":False,"automatic_promotion":False,
         "positive_ev_verified":False,"verified_forward_sample_credit":0,
         "production_recommendations":"DISABLED","status":"HOLD"}
    print(json.dumps(out,sort_keys=True,allow_nan=False))


if __name__=="__main__":
    main()
