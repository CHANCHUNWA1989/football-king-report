"""V8.4 fill UCL archive gap with pinned upstream Football.TXT, research only."""
import argparse
from datetime import date
import hashlib,json,re
from pathlib import Path
from ops import v8_ucl_strength as u,v8_ucl_opponent as o
from ops.v8_multiseason import git_blob
from ops.v6_forward_bundle import decode
from ops import v5_ensemble_competition as e

PIN="abfaeddc2ee3d14f99ecc163c9ddb46cb4d67cef"
SEASONS=tuple(f"{y}-{str(y+1)[-2:]}" for y in range(2020,2026))
DAY=re.compile(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun) ([A-Z][a-z]{2}) (\d{1,2})(?: (\d{4}))?")
MATCH=re.compile(r"(?:\d{2}:\d{2}\s+)?(.+? \(([A-Z]{3})\))\s+v\s+(.+? \(([A-Z]{3})\))\s+(\d{1,2})-(\d{1,2})(?: \(\d{1,2}-\d{1,2}\))?")
MONTHS="Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
WEEKDAYS="Mon Tue Wed Thu Fri Sat Sun".split()

def parse(raw,season):
    if season not in SEASONS:raise ValueError("SEASON")
    start=int(season[:4]);phase=False;day=None;seen=set();rows=[];headers=set()
    for line in raw.decode("utf-8").splitlines():
        l=line.strip()
        if l.startswith("▪"):
            label=l[1:].strip()
            pattern=r"League, Matchday [1-8]" if start>=2024 else r"(?:Group|Gruppe) [A-H]|Group, Matchday [1-6]"
            phase=bool(re.fullmatch(pattern,label));day=None
            if phase:
                label=label.replace("Gruppe ","Group ")
                if label in headers:raise ValueError("DUPLICATE_PHASE")
                headers.add(label)
            continue
        if not phase or not l:continue
        d=DAY.fullmatch(l)
        if d:
            wd,mon,num,yr=d.groups()
            month=MONTHS.index(mon)+1;year=start if month>=7 else start+1
            day=date(year,month,int(num))
            if (yr is not None and int(yr)!=year) or WEEKDAYS[day.weekday()]!=wd:raise ValueError("DATE_CONFLICT")
            continue
        m=MATCH.fullmatch(l)
        if m is None or day is None:raise ValueError("UNPARSED_PHASE_ROW")
        h,ch,a,ca,x,y=m.groups();x,y=int(x),int(y)
        if h==a or max(x,y)>20 or (day,h,a) in seen:raise ValueError("INVALID_MATCH")
        seen.add((day,h,a));rows.append((day,h,a,ch,ca,x,y,season))
    expected=144 if start>=2024 else 96
    if len(rows)!=expected or len({r[1] for r in rows}|{r[2] for r in rows})!=(36 if start>=2024 else 32):raise ValueError("INCOMPLETE_PHASE")
    return sorted(rows)

def load(root,m):
    expected={s+"/cl.txt" for s in SEASONS}
    if m["commit"]!=PIN or m["repository"]!="openfootball/champions-league" or len(m["files"])!=6 or {x["path"] for x in m["files"]}!=expected:raise ValueError("MANIFEST")
    rows=[];receipts=[]
    for x in m["files"]:
        f=Path(root)/x["path"]
        if not 0<f.stat().st_size==x["bytes"]<=100000:raise ValueError("SIZE")
        raw=f.read_bytes()
        if git_blob(raw)!=x["git_blob_sha"]:raise ValueError("BLOB")
        a=parse(raw,x["path"].split("/")[0]);rows+=a
        receipts.append({"path":x["path"],"sha256":hashlib.sha256(raw).hexdigest(),"n":len(a)})
    return sorted(rows),receipts

def compare(old,new):
    # Same publisher: overlap is format consistency, not independent verification.
    a=[r for r in old if r[-1]=="2024-25"];b=[r for r in new if r[-1]=="2024-25"]
    if sorted(a)!=sorted(b) or len(a)!=144:raise ValueError("OVERLAP_CONFLICT")
    latest=[r for r in new if r[-1]=="2025-26"]
    filled=sorted([r for r in old if r[-1]!="2024-25"]+new)
    sparse=sorted(old+latest)
    if len(filled)!=1536 or len(latest)!=144:raise ValueError("COHORT_SIZE")
    def index(rows):
        return {(r["date"],r["home"],r["away"]):r for r in o.replay(rows) if r["season"]=="2025-26"}
    x,y=index(sparse),index(filled)
    if len(x)!=144 or x.keys()!=y.keys():raise ValueError("COHORT_MISMATCH")
    paired=[]
    for k in sorted(x):
        if x[k]["y"]!=y[k]["y"]:raise ValueError("OUTCOME_CONFLICT")
        paired.append({**y[k],"sparse":x[k]["hybrid"],"filled":y[k]["hybrid"]})
    def scores(rows):return {k:e.metrics(rows,lambda r:r[k]) for k in ("sparse","filled")}
    common=[r for r in paired if max(r["sparse"])>=.5]
    return {"schema":"v8-4-ucl-gap-fill-research-v1","historical_phase_matches":len(filled),"overlap_exact_matches":144,
        "latest_2025_26_same_fixture":scores(paired),
        "same_sparse_selected":{"n":len(common),"metrics":scores(common)},
        "individual_threshold_50":{k:{"n":len(a),"coverage":len(a)/144,"metrics":e.metrics(a,lambda r:r[k])} for k in ("sparse","filled") for a in [[r for r in paired if max(r[k])>=.5]]},
        "same_publisher_overlap_not_independent":True,"exact_club_labels_no_alias_resolution":True,
        "current_season_available":False,"current_fixture_forecasts":0,"prospective_validation":False,"verified_forward_sample_credit":0,
        "production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}
def main():
    p=argparse.ArgumentParser()
    for k in ("input-dir","manifest","old-dir","old-manifest","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args()
    old,_=u.load(a.old_dir,decode(Path(a.old_manifest).read_bytes()))
    new,receipts=load(a.input_dir,decode(Path(a.manifest).read_bytes()))
    out=compare(old,new);out["source_receipts"]=receipts
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
