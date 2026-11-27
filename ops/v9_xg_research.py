"""V9.1 authorized historical xG research adapter, no provider/rights attestation."""
import argparse,json,math,hashlib
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from ops.v6_forward_bundle import decode
from ops.v5_ucl_source_gate import utc,ident
from ops import v5_ensemble_competition as e
from ops import v5_joint_poisson as j
MAX_BYTES=8_000_000
MIN_HISTORY=20
MIN_TEAM=5
def sha(raw):return hashlib.sha256(raw).hexdigest()
def number(x,upper):
    if type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=upper:raise ValueError("INVALID_NUMBER")
    return float(x)
def load(raw,meta,now):
    if not 0<len(raw)<=MAX_BYTES or meta.get("schema")!="v9-1-authorized-xg-receipt-v1" or meta.get("sha256")!=sha(raw):raise ValueError("INTEGRITY")
    provider=meta.get("provider");method=meta.get("metric_definition");rights=meta.get("authorization_reference")
    if not isinstance(provider,str) or not provider.strip() or not isinstance(method,str) or not method.strip() or not isinstance(rights,str) or not rights.strip():raise ValueError("MISSING_METADATA")
    captured=utc(meta["captured_utc"])
    if captured>now:raise ValueError("FUTURE_CAPTURE")
    doc=decode(raw)
    if doc.get("schema")!="v9-1-historical-xg-matches-v1" or doc.get("provider")!=provider:raise ValueError("SCOPE")
    rows=doc["matches"]
    if not isinstance(rows,list) or not 1<=len(rows)<=20000:raise ValueError("ROW_COUNT")
    out=[];seen=set();pairs=set()
    for r in rows:
        if r.get("phase")!="REGULATION" or r.get("status")!="FINISHED":raise ValueError("NON_REGULATION")
        mid=ident(r["match_id"]);h=ident(r["home_id"]);a=ident(r["away_id"])
        ko=utc(r["kickoff_utc"]);available=utc(r["xg_available_utc"])
        if h==a or mid in seen or (ko,h,a) in pairs:raise ValueError("DUPLICATE")
        seen.add(mid);pairs.add((ko,h,a))
        if not ko+timedelta(hours=2)<=available<=captured:raise ValueError("XG_CLOCK")
        if r.get("xg_kind")!="PROVIDER_PRE_SHOT_XG" or r.get("metric_definition")!=method:raise ValueError("XG_DEFINITION")
        x,y=r["home_goals"],r["away_goals"]
        if any(type(v) is not int or not 0<=v<=20 for v in (x,y)):raise ValueError("SCORE")
        out.append({"id":mid,"home":h,"away":a,"ko":ko,"available":available,"goals":(x,y),"xg":(number(r["home_xg"],20),number(r["away_xg"],20))})
    return sorted(out,key=lambda r:(r["ko"],r["id"]))

def rates(hist,h,a,key):
    mu=[sum(r[key][i] for r in hist)/len(hist) for i in (0,1)]
    home=[r[key] for r in hist if r["home"]==h]
    away=[r[key] for r in hist if r["away"]==a]
    if min(len(home),len(away))<MIN_TEAM:return None
    def shrink(values,idx):return (sum(v[idx] for v in values)+5*mu[idx])/(len(values)+5)
    return tuple(max(.05,min(8,(shrink(home,i)+shrink(away,i))/2)) for i in (0,1))

def replay(rows):
    out=[]
    for r in rows:
        # Availability is required for BOTH comparator models, identical cohort.
        hist=[s for s in rows if s["ko"].date()<r["ko"].date() and s["available"]<r["ko"]]
        if len(hist)<MIN_HISTORY:continue
        b=rates(hist,r["home"],r["away"],"goals");x=rates(hist,r["home"],r["away"],"xg")
        if b is None or x is None:continue
        p=e.vec(j.probability(b));q=e.vec(j.probability(tuple((v+w)/2 for v,w in zip(b,x))))
        gh,ga=r["goals"]
        out.append({"date":r["ko"].date().isoformat(),"y":0 if gh>ga else 1 if gh==ga else 2,"baseline":p,"candidate":q})
    return out
def build(rows):
    paired=replay(rows)
    return {"schema":"v9-1-xg-research-v1","input_matches":len(rows),"paired_matches":len(paired),
        "coverage":len(paired)/len(rows),"baseline":e.metrics(paired,lambda r:r["baseline"]),
        "candidate":e.metrics(paired,lambda r:r["candidate"]),"fixed_xg_weight":.5,
        "declared_source_and_clock_not_authenticated":True,"authorization_independently_verified":False,
        "historical_reconstructed_not_prospective":True,"verified_forward_sample_credit":0,
        "production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}
def main():
    p=argparse.ArgumentParser()
    for k in ("capture","metadata","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args();f=Path(a.capture);m=Path(a.metadata)
    if not 0<f.stat().st_size<=MAX_BYTES or not 0<m.stat().st_size<=100000:raise ValueError("SIZE")
    rows=load(f.read_bytes(),decode(m.read_bytes()),datetime.now(timezone.utc))
    out=build(rows)
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
