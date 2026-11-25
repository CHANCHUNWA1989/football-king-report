"""V8.7 explicit historical club label continuity challenger. Research only."""
import argparse,json
from pathlib import Path
from collections import defaultdict
from ops import v8_ucl_strength as u,v8_ucl_gap_fill as g,v8_ucl_opponent as o
from ops.v6_forward_bundle import decode
from ops import v5_ensemble_competition as e

def mapping(doc,rows):
    if doc.get("schema")!="v8-7-ucl-historical-alias-hypotheses-v1" or doc.get("independently_verified") is not False:raise ValueError("MAP_SCHEMA")
    pairs=doc["pairs"]
    if not isinstance(pairs,list) or len(pairs)>100:raise ValueError("MAP_SIZE")
    seen={t for r in rows for t in r[1:3]}
    m={}
    for r in pairs:
        a,b=r["from"],r["to"]
        if a in m or a==b or not u.TEAM.fullmatch(a) or not u.TEAM.fullmatch(b) or a[-5:]!=b[-5:]:raise ValueError("MAP_CONFLICT")
        m[a]=b
    if set(m)&set(m.values()):raise ValueError("ALIAS_CHAIN")
    active={a:b for a,b in m.items() if a in seen and b in seen}
    # If two labels occur in the same season, refuse to collapse them.
    by=defaultdict(set)
    for r in rows:
        for t in r[1:3]:by[r[-1]].add(t)
    if any(a in ts and b in ts for ts in by.values() for a,b in active.items()):raise ValueError("COEXISTING_LABELS")
    return active

def remap(rows,m):
    out=[];seen=set()
    for d,h,a,ch,ca,x,y,s in rows:
        h,a=m.get(h,h),m.get(a,a)
        if h==a or (d,h,a) in seen:raise ValueError("CANONICAL_COLLISION")
        seen.add((d,h,a));out.append((d,h,a,ch,ca,x,y,s))
    return sorted(out)
def build(rows,doc):
    m=mapping(doc,rows);changed=remap(rows,m)
    def idx(rows,mapped=False):
        out={}
        for r in o.replay(rows):
            if r["season"]!="2025-26":continue
            k=(r["date"],m.get(r["home"],r["home"]) if mapped else r["home"],m.get(r["away"],r["away"]) if mapped else r["away"])
            if k in out:raise ValueError("DUPLICATE_CASE")
            out[k]=r
        return out
    a,b=idx(rows,True),idx(changed)
    if len(a)!=144 or a.keys()!=b.keys():raise ValueError("COHORT_MISMATCH")
    paired=[]
    for k in sorted(a):
        if a[k]["y"]!=b[k]["y"]:raise ValueError("OUTCOME_CONFLICT")
        paired.append({"y":a[k]["y"],"date":k[0],"baseline":a[k]["hybrid"],"candidate":b[k]["hybrid"]})
    def score(rows):return {k:e.metrics(rows,lambda r:r[k]) for k in ("baseline","candidate")}
    fixed=[r for r in paired if max(r["baseline"])>=.5]
    return {"schema":"v8-7-ucl-label-continuity-research-v1","active_alias_pairs":len(m),
        "changed_historical_rows":sum(h in m or a in m for _,h,a,*_ in rows),"same_fixture_latest":score(paired),
        "same_baseline_selected":{"n":len(fixed),"metrics":score(fixed)},
        "individual_threshold_50":{k:{"n":len(a),"coverage":len(a)/144,"metrics":e.metrics(a,lambda r:r[k])} for k in ("baseline","candidate") for a in [[r for r in paired if max(r[k])>=.5]]},
        "historical_aliases_independently_verified":False,"assessment_previously_inspected":True,
        "prospective_validation":False,"current_fixture_forecasts":0,"verified_forward_sample_credit":0,
        "production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}
def main():
    p=argparse.ArgumentParser()
    for k in ("input-dir","manifest","old-dir","old-manifest","aliases","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args()
    old,_=u.load(a.old_dir,decode(Path(a.old_manifest).read_bytes()))
    new,_=g.load(a.input_dir,decode(Path(a.manifest).read_bytes()))
    if sorted(r for r in old if r[-1]=="2024-25")!=sorted(r for r in new if r[-1]=="2024-25"):raise ValueError("OVERLAP_CONFLICT")
    rows=sorted([r for r in old if r[-1]!="2024-25"]+new)
    if len(rows)!=1536:raise ValueError("COHORT_SIZE")
    out=build(rows,decode(Path(a.aliases).read_bytes()))
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
