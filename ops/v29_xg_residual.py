"""V29 authorized xG residual challenge against the frozen V10.1 anchor.
Offline only: no fetch, license inference, invented availability clock or promotion.
"""
import argparse,json,math
from pathlib import Path
from datetime import datetime,timezone,date
from zoneinfo import ZoneInfo
from ops import v9_stacking_research as s,v9_feature_calibration as f,v9_xg_research as xg
from ops import v5_ensemble_competition as e,v8_multiseason as v
from ops.v9_league_weights import ci
from ops.v6_forward_bundle import decode,digest,utc
from ops.v20_signed_receipts import bounded,sha
from ops.v5_ucl_source_gate import ident

SHARES=(0.,.125,.25,.5,.75)
ZONES={"de.1":"Europe/Berlin","en.1":"Europe/London","es.1":"Europe/Madrid","fr.1":"Europe/Paris",
       "it.1":"Europe/Rome","nl.1":"Europe/Amsterdam","pt.1":"Europe/Lisbon"}
MAX=8_000_000
def enc(d):return json.dumps(d,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def read(path):
    p=Path(path)
    if not 0<p.stat().st_size<=MAX:raise ValueError("FILE_SIZE")
    return bounded(p.read_bytes(),MAX)
def checked(raw,expected):
    bounded(raw,MAX)
    if sha(raw)!=digest(expected):raise ValueError("DIGEST")
    return decode(raw)
def anchor_export(data,rows):
    parts=s.partition(rows);model=s.fit_stack(parts["train"])
    def predict(a):
        return [e.vec([float(x) for x in p]) for p in model.predict_proba([s.features(r) for r in a])]
    t,w=s.select_calibration(parts["cal"],predict(parts["cal"]))
    results=[]
    for part in ("cal","test"):
        for r,p in zip(parts[part],predict(parts[part])):
            key=(r["league"],r["season"])
            # Exact source labels and full-time score, never inferred from outcome alone.
            matches=[z for z in data[key] if (z[0].isoformat(),z[1],z[2])==e.key(r)]
            if len(matches)!=1:raise ValueError("ANCHOR_FIXTURE")
            h,a=matches[0][3:]
            if (0 if h>a else 1 if h==a else 2)!=r["y"]:raise ValueError("ANCHOR_OUTCOME")
            results.append({k:r[k] for k in ("league","season","date","home","away","y")}|{"goals":[h,a],
                "stack":s.combine(p,r["candidate"],t,w)})
    return {"schema":"v29-stack-reference-v1","historical_source_commit":v.PIN,"rows":results,
            "temperature":t,"stack_weight":w,"historical_reconstructed":True,"status":"HOLD",
            "production_recommendations":"DISABLED","verified_forward_sample_credit":0}
def correction(r,w):
    if w not in SHARES:raise ValueError("XG_WEIGHT")
    p=e.vec(r["stack"])
    if not w:return p
    g=e.vec(r["goal_model"]);x=e.vec(r["xg_model"])
    # Bounded log likelihood ratio; avoids overstating tiny probability changes.
    z=[math.log(max(a,1e-15))+w*max(-1.,min(1.,math.log(max(c,1e-9)/max(b,1e-9)))) for a,b,c in zip(p,g,x)]
    q=[math.exp(a-max(z)) for a in z]
    return e.vec([a/math.fsum(q) for a in q])
def join(anchor,provider_rows,mapping,league,provider):
    if anchor.get("schema")!="v29-stack-reference-v1" or anchor.get("historical_source_commit")!=v.PIN or anchor.get("status")!="HOLD" or anchor.get("production_recommendations")!="DISABLED" or anchor.get("verified_forward_sample_credit")!=0:raise ValueError("ANCHOR_CONTRACT")
    if mapping.get("schema")!="v29-explicit-xg-fixture-crosswalk-v1" or mapping.get("league")!=league or mapping.get("provider")!=provider or league not in ZONES:raise ValueError("MAP_CONTRACT")
    idx={}
    for r in anchor["rows"]:
        if r["league"]!=league:continue
        key=e.key(r)
        if key in idx or r["season"] not in (s.CAL,s.TEST) or not isinstance(r["goals"],list) or len(r["goals"])!=2 or any(type(z) is not int or not 0<=z<=20 for z in r["goals"]):raise ValueError("ANCHOR_DUPLICATE_OR_SCORE")
        year=int(r["season"][:4])
        if not date(year,7,1)<=date.fromisoformat(r["date"])<date(year+1,7,1):raise ValueError("ANCHOR_DATE")
        h,a=r["goals"]
        if type(r["y"]) is not int or r["y"]!=(0 if h>a else 1 if h==a else 2):raise ValueError("ANCHOR_OUTCOME")
        e.vec(r["stack"]);idx[key]=r
    by_id={r["id"]:r for r in provider_rows}
    if len(by_id)!=len(provider_rows):raise ValueError("XG_DUPLICATE")
    seen=set();keys=set();links={}
    for m in mapping["pairs"]:
        if set(m)!={"match_id","home_id","away_id","kickoff_utc","date","home","away","evidence_reference"}:raise ValueError("MAP_FIELDS")
        mid=ident(m["match_id"]);q=by_id.get(mid);key=e.key(m)
        if mid in seen or key in keys or q is None or key not in idx or not isinstance(m["evidence_reference"],str) or not m["evidence_reference"].startswith("https://"):raise ValueError("MAP_IDENTITY")
        if (q["home"],q["away"],q["ko"])!=(ident(m["home_id"]),ident(m["away_id"]),utc(m["kickoff_utc"])) or q["ko"].astimezone(ZoneInfo(ZONES[league])).date().isoformat()!=m["date"] or tuple(idx[key]["goals"])!=q["goals"]:raise ValueError("MAP_SCORE_CLOCK")
        seen.add(mid);keys.add(key);links[mid]=idx[key]
    cases=[]
    for r in f.xg_cases(provider_rows):
        if r["id"] not in links:continue
        a=links[r["id"]]
        # xG case uses only previous UTC date and explicitly available prior records.
        # Exclude previous UTC-day matches that may share the target local calendar date.
        local=r["ko"].astimezone(ZoneInfo(ZONES[league])).date()
        hist=[q for q in provider_rows if q["ko"].date()<r["ko"].date() and q["ko"].astimezone(ZoneInfo(ZONES[league])).date()<local and q["available"]<r["ko"]]
        gr=f.rates(hist,r["home"],r["away"],r["ko"],"goals");xr=f.rates(hist,r["home"],r["away"],r["ko"],"xg")
        if gr is None or xr is None:continue
        cases.append({**a,"id":r["id"],"ko":r["ko"],"available":r["available"],
            "goal_model":e.dc(*gr),"xg_model":e.dc(*xr)})
    return cases,len(idx)
def evaluate(rows,total):
    split=utc("2025-07-01T00:00:00Z");end=utc("2026-07-01T00:00:00Z")
    cal=[r for r in rows if r["season"]==s.CAL and r["ko"]<split and r["available"]<split]
    test=[r for r in rows if r["season"]==s.TEST and split<=r["ko"]<end and r["available"]<end]
    out={"schema":"v29-xg-residual-research-v1","anchor_reference_rows":total,"calibration_n":len(cal),"assessment_n":len(test),
         "selected_xg_weight":None,"metrics":None,"verified_forward_sample_credit":0,"automatic_promotion":False,
         "production_recommendations":"DISABLED","status":"HOLD","rights_and_clocks_independently_verified":False,
         "historical_reconstructed":True,"assessment_previously_inspected":True}
    if len(cal)<100 or len(test)<50 or {r["y"] for r in cal}!={0,1,2} or {r["y"] for r in test}!={0,1,2}:
        return {**out,"reason":"INSUFFICIENT_AUTHORIZED_PAIRED_COHORT"}
    w=min(SHARES,key=lambda w:(math.fsum(e.loss(correction(r,w),r["y"]) for r in cal)/len(cal)+.01*w*w,w))
    a=[{**r,"hybrid":r["stack"],"candidate":correction(r,w)} for r in test]
    m={k:e.metrics(a,lambda r:r[k]) for k in ("stack","goal_model","xg_model","candidate")}
    interval=ci(a)
    return {**out,"selected_xg_weight":w,"metrics":m,"paired_week_ci_stack_minus_candidate":interval,
        "historical_proper_score_gate":bool(w and interval and interval[0]>0 and all(m["candidate"][k]<m["stack"][k] for k in ("log_loss","brier")))}
def run(anchor_raw,anchor_digest,capture_raw,meta_raw,mapping_raw,mapping_digest,*,now):
    a=checked(anchor_raw,anchor_digest);m=checked(mapping_raw,mapping_digest);meta=decode(bounded(meta_raw,100000))
    league=meta.get("competition_scope")
    if league not in ZONES or meta.get("owner_authorization_reviewed") is not True or meta.get("historical_availability_recorded") is not True:raise ValueError("AUTHORIZATION_OR_AVAILABILITY_REQUIRED")
    rows=xg.load(capture_raw,meta,now)
    cases,total=join(a,rows,m,league,meta["provider"])
    return {**evaluate(cases,total),"league":league,"provider":meta["provider"],"input_sha256":[sha(x) for x in (anchor_raw,capture_raw,meta_raw,mapping_raw)]}
def main():
    p=argparse.ArgumentParser()
    for k in ("anchor","anchor-sha256","capture","metadata","mapping","mapping-sha256","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args();out=run(read(a.anchor),a.anchor_sha256,read(a.capture),read(a.metadata),read(a.mapping),a.mapping_sha256,now=datetime.now(timezone.utc))
    with Path(a.output).open("x") as h:json.dump(out,h,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
