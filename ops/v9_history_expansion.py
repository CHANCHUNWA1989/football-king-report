"""V9.6 pinned seven-league history extension and causal rolling replay."""
import argparse,json,hashlib
from pathlib import Path
from collections import defaultdict
from ops import v8_multiseason as v,v5_ensemble_competition as e
from ops.v6_forward_bundle import decode
# Explicit upstream availability; missing earlier scopes are not invented.
START={"de.1":2010,"en.1":2010,"es.1":2012,"it.1":2013,"fr.1":2014,"nl.1":2018,"pt.1":2018}
def season(y):return f"{y}-{str(y+1)[-2:]}"
def expected():
    return {f"{season(y)}/{k}.json" for k,start in START.items() for y in range(start,2021)}
def load(root,m):
    files=m.get("files",[])
    if m.get("commit")!=v.PIN or m.get("repository")!="openfootball/football.json" or len(files)!=len(expected()) or {r["path"] for r in files}!=expected():raise ValueError("MANIFEST_SCOPE")
    data={};receipts=[]
    for x in files:
        p=Path(root)/x["path"]
        if not 0<p.stat().st_size==x["bytes"]<=500000:raise ValueError("SIZE")
        raw=p.read_bytes()
        if v.git_blob(raw)!=x["git_blob_sha"]:raise ValueError("BLOB")
        s,k=x["path"].split("/");k=k[:-5]
        receipt={"season":s,"league":k,"sha256":hashlib.sha256(raw).hexdigest()}
        try:rows,missing,total=v.parse(raw,s)
        except (ValueError,TypeError,KeyError) as exc:
            receipts.append({**receipt,"status":"QUARANTINE","reason":str(exc),"finished":0,"missing":None});continue
        data[s,k]=rows
        receipts.append({**receipt,"status":"PARTIAL" if missing else "PARSED","finished":len(rows),"missing":missing,"scheduled":total})
    return data,receipts
def combine(old,new):
    if set(old)&set(new):raise ValueError("OVERLAPPING_SCOPES")
    data={**old,**new};seen=set()
    for (s,k),rows in data.items():
        for d,h,a,x,y in rows:
            key=(k,d,h,a)
            if key in seen:raise ValueError("DUPLICATE_FIXTURE")
            seen.add(key)
    return data
def build(data,receipts,base_count,ucl_count):
    total=sum(len(a) for a in data.values())
    if total!=sum(x["finished"] for x in receipts):raise ValueError("COUNT_MISMATCH")
    rows=[];scopes=[];excluded=[]
    for k,start in START.items():
        for y in range(start+1,2026):
            old,new=season(y-1),season(y)
            tr,te=data.get((old,k)),data.get((new,k))
            if tr is None or te is None or len(tr)<100 or not te:
                excluded.append({"league":k,"season":new,"reason":"MISSING_OR_INSUFFICIENT_SCOPE"});continue
            # COVID extensions or malformed chronology must not create leakage.
            if max(r[0] for r in tr)>=min(r[0] for r in te):
                excluded.append({"league":k,"season":new,"reason":"OVERLAPPING_DATES"});continue
            a=v.replay(tr,te,k,new);rows+=a
            scopes.append({"league":k,"season":new,"n":len(a)})
    last=[r for r in rows if r["season"]=="2025-26"]
    return {"schema":"v9-6-expanded-domestic-history-v1","historical_domestic_finished":total,
        "previous_domestic_finished":base_count,"new_domestic_finished":total-base_count,
        "ucl_historical_finished_reference":ucl_count,"combined_historical_finished":total+ucl_count,
        "combined_history_target_30000":total+ucl_count>=30000,
        "source_scope_count":len(receipts),"parsed_scope_count":len(data),
        "missing_results_excluded":sum(x["missing"] or 0 for x in receipts),
        "quarantined_scopes":[x for x in receipts if x["status"]=="QUARANTINE"],
        "source_receipts":receipts,"rolling_scope_count":len(scopes),"excluded_replay_scopes":excluded,
        "rolling_all":v.metrics(rows),"latest_season":v.metrics(last),
        "per_league":{k:v.metrics([r for r in rows if r["league"]==k]) for k in START},
        "baseline_definition":"V8 prior-season joint Poisson vs fixed rolling DC; no full ensemble extension",
        "exact_labels_no_independent_identity":True,"historical_results_independently_verified":False,
        "assessment_previously_inspected":True,"prospective_validation":False,"verified_forward_sample_credit":0,
        "production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}
def main():
    p=argparse.ArgumentParser()
    for k in ("input-dir","manifest","base-dir","base-manifest","ucl-report","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args()
    old,old_receipts=v.load(a.base_dir,decode(Path(a.base_manifest).read_bytes()))
    new,new_receipts=load(a.input_dir,decode(Path(a.manifest).read_bytes()))
    u=decode(Path(a.ucl_report).read_bytes())
    if u.get("schema")!="v8-4-ucl-gap-fill-research-v1" or u.get("historical_phase_matches")!=1536 or u.get("production_recommendations")!="DISABLED":raise ValueError("UCL_REFERENCE")
    data=combine(old,new);out=build(data,old_receipts+new_receipts,sum(len(r) for r in old.values()),u["historical_phase_matches"])
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in out.items() if k!="source_receipts"},allow_nan=False))
if __name__=="__main__":main()
