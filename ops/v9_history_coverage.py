"""Pinned public-domain historical archive inventory, not independent validation."""
import hashlib
import json
import re
from datetime import date
from pathlib import Path

PIN="e6744429ee395bc86f247348c6184bb08d4eb361"
PATH=re.compile(r"(20[12][0-9])-([0-9]{2})/(de|en|es|fr|it|nl|pt)\.1\.json")
def unique(pairs):
    d={}
    for k,v in pairs:
        if k in d: raise ValueError("DUPLICATE_JSON_KEY")
        d[k]=v
    return d

def parse(raw,year):
    doc=json.loads(raw,object_pairs_hook=unique)
    rows=doc["matches"]
    if type(rows) is not list or not 1<=len(rows)<=650: raise ValueError("ROW_COUNT")
    seen=set(); finished=0; missing=0
    for r in rows:
        h,a=r["team1"],r["team2"]
        if any(type(t) is not str or not 0<len(t.strip())<=109 for t in (h,a)) or h==a: raise ValueError("TEAM")
        day=date.fromisoformat(r["date"])
        if not date(year,7,1)<=day<date(year+1,7,1): raise ValueError("SEASON_BOUNDARY")
        if (h,a) in seen: raise ValueError("DUPLICATE_PAIR")
        seen.add((h,a))
        s=r.get("score")
        if s=={} or (s is None and r.get("status")=="canceled"):
            missing+=1;continue
        s=s.get("ft") if isinstance(s,dict) else s
        if type(s) is not list or len(s)!=2 or any(type(x) is not int or not 0<=x<=20 for x in s): raise ValueError("SCORE")
        finished+=1
    return finished,missing

def audit(root,manifest):
    files=manifest["files"]
    if manifest["commit"]!=PIN or manifest["repository"]!="openfootball/football.json" or len(files)!=87 or len({x["path"] for x in files})!=87:
        raise ValueError("MANIFEST")
    report=[]
    for x in files:
        m=PATH.fullmatch(x["path"])
        if not m: raise ValueError("PATH")
        y=int(m[1])
        if not 2010<=y<=2025 or int(m[2])!=(y+1)%100: raise ValueError("SEASON")
        p=Path(root)/x["path"]
        if p.is_symlink() or not 0<p.stat().st_size<=500000 or p.stat().st_size!=x["bytes"]: raise ValueError("SIZE")
        raw=p.read_bytes()
        blob=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\x00"+raw).hexdigest()
        if blob!=x["git_blob_sha"]: raise ValueError("BLOB")
        try:
            n,missing=parse(raw,y)
        except (ValueError,KeyError,TypeError,AttributeError):
            report.append({"path":x["path"],"status":"QUARANTINE","finished":0})
        else:
            report.append({"path":x["path"],"status":"PARSED","finished":n,"missing":missing})
    old=sum(r["finished"] for r in report if r["path"]<"2021-22")
    recent=sum(r["finished"] for r in report if r["path"]>="2021-22")
    return {"schema":"v9-history-coverage-audit-v1","files":report,"older_finished":old,"original_scope_finished":recent,"domestic_finished":old+recent,"quarantined_files":sum(r["status"]=="QUARANTINE" for r in report),"independent_assessment_count":0,"verified_forward_sample_credit":0,"production_recommendations":"DISABLED","status":"HOLD"}

def selftest():
    def raw(rows): return json.dumps({"matches":rows}).encode()
    row={"team1":"A","team2":"B","date":"2018-08-01","score":{"ft":[1,0]}}
    assert parse(raw([row]),2018)==(1,0)
    for rows in ([row,row],[dict(row,score={"ft":[True,0]})],[dict(row,date="2019-08-01")],[dict(row,team2="A")]):
        try: parse(raw(rows),2018)
        except ValueError: pass
        else: raise AssertionError("UNSAFE_ACCEPTANCE")
    assert parse(raw([dict(row,score={})]),2018)==(0,1)
    return 6

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True);p.add_argument("--manifest",required=True)
    a=p.parse_args()
    print(json.dumps({"synthetic_tests":selftest(),**audit(a.root,json.loads(Path(a.manifest).read_text()))},sort_keys=True))
