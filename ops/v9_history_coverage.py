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

# Exact archived delayed-season exceptions; no blanket extension.
LATE_SEASONS={
    "2019-20/es.1.json":("64307d5017689bbe5e099e2f1162a05a56bc47c5",date(2020,7,20),date(2020,9,12)),
    "2019-20/it.1.json":("5858e492e536affca47beb6182dea468b5ac7aff",date(2020,8,3),date(2020,9,19)),
    "2019-20/pt.1.json":("9fde4ef04aef0cada769d10d027e272bb2ce841d",date(2020,7,27),date(2020,9,18)),
}

def season_end(path,blob,year):
    if path in LATE_SEASONS:
        expected,end,next_start=LATE_SEASONS[path]
        if blob!=expected or year!=2019 or end>next_start:
            raise ValueError("UNEXPECTED_LATE_SEASON_PIN")
        return end
    return date(year+1,7,1)

def parse(raw,year,*,end=None):
    doc=json.loads(raw,object_pairs_hook=unique)
    rows=doc["matches"]
    if type(rows) is not list or not 1<=len(rows)<=650: raise ValueError("ROW_COUNT")
    seen=set(); finished=0; missing=0
    for r in rows:
        h,a=r["team1"],r["team2"]
        if any(type(t) is not str or not 0<len(t.strip())<=109 for t in (h,a)) or h==a: raise ValueError("TEAM")
        day=date.fromisoformat(r["date"])
        if not date(year,7,1)<=day<(end or date(year+1,7,1)): raise ValueError("SEASON_BOUNDARY")
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
            n,missing=parse(raw,y,end=season_end(x["path"],blob,y))
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
    late=dict(row,date="2020-07-19")
    for path,(pin,end,next_start) in LATE_SEASONS.items():
        assert parse(raw([late]),2019,end=season_end(path,pin,2019))==(1,0)
        try: parse(raw([dict(late,date=end.isoformat())]),2019,end=end)
        except ValueError: pass
        else: raise AssertionError("LATE_BOUNDARY_ACCEPTED")
    try: season_end("2019-20/es.1.json","wrong",2019)
    except ValueError: pass
    else: raise AssertionError("UNPINNED_EXCEPTION")
    try: parse(raw([late]),2019,end=season_end("2019-20/de.1.json","unused",2019))
    except ValueError: pass
    else: raise AssertionError("UNRELATED_SEASON_EXTENDED")
    return 14

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True);p.add_argument("--manifest",required=True)
    a=p.parse_args()
    print(json.dumps({"synthetic_tests":selftest(),**audit(a.root,json.loads(Path(a.manifest).read_text()))},sort_keys=True))
