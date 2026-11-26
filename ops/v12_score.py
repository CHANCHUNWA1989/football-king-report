"""V12 multiscale score distribution research. Historical goals, not provider xG."""
import argparse,json,math,random
from collections import defaultdict
from datetime import date
from pathlib import Path
from ops import v8_multiseason as v,v5_joint_poisson as j,v5_ensemble_competition as e
from ops.v6_forward_bundle import decode
DEV=("2022-23","2023-24","2024-25")
TEST="2025-26"
SCALES=(30,90,365)
MODELS=("base",)+tuple(str(x) for x in SCALES)+("multiscale",)
def grid(h,a):
    if any(not math.isfinite(z) or not .05<=z<=8 for z in (h,a)):raise ValueError("RATE")
    def pois(l):
        p=[math.exp(-l)]
        for i in range(1,25):p.append(p[-1]*l/i)
        return p
    rows=[]
    for i,x in enumerate(pois(h)):
        for k,y in enumerate(pois(a)):
            tau={(0,0):1+.05*h*a,(0,1):1-.05*h,(1,0):1-.05*a,(1,1):1.05}.get((i,k),1.)
            rows.append(x*y*tau)
    s=sum(rows)
    return [z/s for z in rows]
def marginal(g):
    if len(g)!=625 or any(not math.isfinite(z) or z<0 for z in g) or abs(sum(g)-1)>1e-8:raise ValueError("GRID")
    p=[0.,0.,0.];over=0.;home=away=0.
    for n,z in enumerate(g):
        i,k=divmod(n,25)
        p[0 if i>k else 1 if i==k else 2]+=z
        if i+k>=3:over+=z
        home+=i*z;away+=k*z
    return e.vec(p),over,home,away
def rate(base,history,day,h,a,lh,la,half):
    if half not in SCALES:raise ValueError("SCALE")
    mu=(lh+la)/2
    def strength(t):
        hist=history.get(t,[])
        if any(d>=day for d,_,_ in hist):raise ValueError("FUTURE_HISTORY")
        w=[2**(-(day-d).days/half) for d,_,_ in hist]
        n=sum(w)
        return tuple((sum(z*r[i] for z,r in zip(w,hist))+8*mu)/(n+8)/mu for i in (1,2))
    ah,dh=strength(h);aa,da=strength(a)
    return tuple(max(.05,min(8,math.sqrt(b*c))) for b,c in zip(base,(lh*ah*da,la*aa*dh)))
def summarize(g,x,y):
    p,o,h,a=marginal(g);top=max(range(625),key=lambda i:g[i])
    return {"p":p,"score_loss":-math.log(max(g[25*x+y],1e-15)),"exact":int(top==25*x+y),
        "total_brier":(o-int(x+y>=3))**2,"goal_mae":(abs(h-x)+abs(a-y))/2}
def replay(tr,te,league,season):
    if len(tr)<100 or not te or max(r[0] for r in tr)>=min(r[0] for r in te):raise ValueError("TRAIN_ORDER")
    model=j.fit(tr,min(r[0] for r in te));lh=max(.05,sum(r[3] for r in tr)/len(tr));la=max(.05,sum(r[4] for r in tr)/len(tr))
    days=defaultdict(list);teams=defaultdict(list);hist=defaultdict(list);out=[]
    for r in te:days[r[0]].append(r)
    for day in sorted(days):
        for _,h,a,x,y in days[day]:
            b=j.rates(model,h,a)
            if b is None or not all(.05<=z<=8 for z in b):b=(lh,la)
            g=grid(*v.rolling_rates(b,teams,h,a,lh,la))
            gs=[grid(*rate(b,hist,day,h,a,lh,la,t)) for t in SCALES]
            mix=[sum(z)/len(gs) for z in zip(*gs)]
            out.append({"league":league,"season":season,"date":day.isoformat(),"home":h,"away":a,
                "y":0 if x>y else 1 if x==y else 2,
                "models":{k:summarize(z,x,y) for k,z in zip(MODELS,[g,*gs,mix])}})
        for _,h,a,x,y in days[day]:
            teams[h].append((x,y));teams[a].append((y,x))
            hist[h].append((day,x,y));hist[a].append((day,y,x))
    return out
def select(dev):
    if len(dev)<500 or any(r["season"] not in DEV or r["date"]>="2025-07-01" for r in dev):raise ValueError("DEVELOPMENT")
    return min(MODELS,key=lambda k:(sum(r["models"][k]["score_loss"] for r in dev)/len(dev),MODELS.index(k)))
def scores(rows,k):
    n=len(rows)
    if not n:raise ValueError("EMPTY")
    return {**e.metrics(rows,lambda r:r["models"][k]["p"]),
        **{key:sum(r["models"][k][key] for r in rows)/n for key in ("score_loss","exact","total_brier","goal_mae")}}
def ci(rows,k):
    groups=defaultdict(list)
    for r in rows:groups[date.fromisoformat(r["date"]).strftime("%G-W%V")].append(r["models"]["base"]["score_loss"]-r["models"][k]["score_loss"])
    if len(groups)<12:return None
    blocks=list(groups.values());rng=random.Random(20261126);z=[]
    for _ in range(1000):
        a=[x for b in rng.choices(blocks,k=len(blocks)) for x in b];z.append(sum(a)/len(a))
    z.sort();return [z[25],z[974]]
def evaluate(data):
    rows=[]
    for league in v.LEAGUES:
        for old,new in zip(v.SEASONS,v.SEASONS[1:]):
            rows+=replay(data[old,league],data[new,league],league,new)
    dev=[r for r in rows if r["season"] in DEV];test=[r for r in rows if r["season"]==TEST]
    if len(test)!=2362 or any(r["date"]<"2025-07-01" for r in test):raise ValueError("ASSESSMENT")
    k=select(dev)
    def compare(a):
        b,c=scores(a,"base"),scores(a,k);i=ci(a,k)
        return {"baseline":b,"selected":c,"paired_week_score_loss_ci":i,
            "historical_joint_score_gate":bool(i and i[0]>0 and c["score_loss"]<b["score_loss"] and c["log_loss"]<=b["log_loss"] and c["brier"]<=b["brier"])}
    return {"schema":"v12-multiscale-score-research-v1","development_n":len(dev),"assessment_n":len(test),
        "half_life_days":SCALES,"selected_model":k,"pooled":compare(test),
        "per_league":{l:compare([r for r in test if r["league"]==l]) for l in v.LEAGUES},
        "fixed_grid_diagnostics":{k:scores(test,k) for k in MODELS},
        "baseline_definition":"V8 dynamic DC score distribution, not V10/V11 classifier",
        "goals_not_provider_xg":True,"grid_support":[0,24],"assessment_previously_inspected":True,
        "prospective_validation":False,"verified_forward_sample_credit":0,
        "production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}
def main():
    p=argparse.ArgumentParser()
    for k in ("input-dir","manifest","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args();data,_=v.load(a.input_dir,decode(Path(a.manifest).read_bytes()))
    out=evaluate(data)
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
