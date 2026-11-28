"""Locate archived forecast proof inputs, without treating their existence as verification."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
from .research_candidate_gap_v6 import audit, stamp
from .research_live_intake_v4 import decode, MAX_BYTES
from .team_identity import folded

MAX_RUNS=2500
MAX_COMPRESSED=2_000_000
MEMBERS=("paired.json.gz","shadow.json.gz","slate.json.gz","research.sigstore.json.gz")

def index(raw):
    if not audit(raw).get("structural_audit_passed"):
        raise ValueError("invalid ledger")
    out={}
    for row in decode(raw)["samples"]:
        key=json.loads(row["key"])
        k=(*key[:3],stamp(key[3]),stamp(row["forecast_utc"]),stamp(row["market_utc"]))
        if k in out:raise ValueError("duplicate forecast identity")
        out[k]=row
    return out

def scan(root,raw):
    wanted=index(raw)
    days={k[4].date()+timedelta(days=i) for k in wanted for i in (0,1)}
    n=0
    for day in sorted(days):
        folder=root/day.strftime("%Y/%m/%d")
        if not folder.is_dir() or folder.is_symlink():continue
        for p in sorted(folder.iterdir()):
            if not re.fullmatch(r"[1-9][0-9]{0,19}-[1-9][0-9]{0,9}",p.name) or p.is_symlink() or not p.is_dir():continue
            n+=1
            if n>MAX_RUNS:raise ValueError("proof run budget")
            label=str(p.relative_to(root))
            try:
                paths=[p/x for x in MEMBERS]
                if any(x.is_symlink() or not x.is_file() or not 0<x.stat().st_size<=MAX_COMPRESSED for x in paths):
                    raise ValueError("incomplete proof input")
                with gzip.open(paths[0],"rb") as f:body=f.read(MAX_BYTES+1)
                yield label,body,True
            except (OSError,EOFError,ValueError):yield label,b"",False

def locate(raw,archives,*,as_of):
    wanted=index(raw); now=stamp(as_of)
    found=defaultdict(list); conflicts=set(); seen=set(); n=invalid=0
    for path,body,complete in archives:
        n+=1
        if n>MAX_RUNS:raise ValueError("proof run budget")
        try:
            if not complete or path in seen:raise ValueError("missing or repeated proof path")
            seen.add(path)
            doc=decode(body)
            if doc.get("production_recommendations")!="DISABLED" or doc.get("status") not in ("HOLD","RESEARCH_ONLY"):
                raise ValueError("unsafe paired document")
            rows=doc["comparisons"]
            if not isinstance(rows,list) or len(rows)>3000 or type(doc.get("matched_count")) is not int or doc["matched_count"]!=len(rows):
                raise ValueError("invalid pair roster")
            staged=defaultdict(list)
            for i,r in enumerate(rows):
                if not isinstance(r,dict):continue
                try:
                    k=(r["league"],folded(r["home"]),folded(r["away"]),stamp(r["kickoff_utc"]),
                        stamp(r["prediction_utc"]),stamp(r["market_snapshot_utc"]))
                    if k in wanted:staged[k].append((i,r))
                except (KeyError,TypeError,ValueError,OverflowError):continue
            sha=hashlib.sha256(body).hexdigest()
            for k,rs in staged.items():
                old=wanted[k]
                if len(rs)!=1:
                    conflicts.add(k);continue
                i,r=rs[0]
                if (k[4]>now or not k[5]<=k[4]<=k[3]-timedelta(minutes=10)
                    or r.get("production_recommendations")!="DISABLED" or r.get("available_for_betting") is not False
                    or any(r.get(x) is not None for x in ("result","historical_outcome","score_ft"))
                    or r.get("model")!=old["p"] or r.get("market")!=old["m"]
                    or any(type(x) not in (int,float) for v in (r["model"],r["market"]) for x in v)
                    or not isinstance(r.get("case_id"),str) or not r["case_id"]):
                    conflicts.add(k);continue
                if any(old.get(f)!=r.get(f) for f in ("ab","ab_model","c","c_model") if f in old):
                    conflicts.add(k);continue
                if "forecast_event_id" in old and old["forecast_event_id"]!=r.get("forecast_event_id"):
                    conflicts.add(k);continue
                found[k].append({"archive_run":path,"pair_index":i,"case_id":r["case_id"],
                                 "paired_decoded_sha256":sha})
        except (KeyError,TypeError,ValueError,AttributeError,OverflowError,RecursionError):
            invalid+=1
    cases=[]
    for k,old in wanted.items():
        links=found[k]
        state="NO_MATCHING_PROOF_INPUT"
        if k in conflicts:state="PAIR_CONTENT_CONFLICT_REVIEW"
        elif links:state="MATCHING_PROOF_INPUT_CANDIDATE"
        cases.append({"key":old["key"],"state":state,"proof_candidates":links,
                      "signature_reverified":False,"forecast_witness_verified":False})
    return {"schema":"forecast-proof-locator-v19","status":"HOLD","production_recommendations":"DISABLED",
            "ledger_sha256":hashlib.sha256(raw).hexdigest(),"ledger_rows":len(cases),"runs_examined":n,
            "invalid_runs":invalid,"states":dict(Counter(x["state"] for x in cases)),
            "fresh_cryptographic_verifications":0,"authenticated_samples":0,"cases":cases}

def from_root(root,*,as_of):
    with (root/"evidence/settled.json").open("rb") as f:raw=f.read(MAX_BYTES+1)
    return locate(raw,scan(root/"forecast_provenance",raw),as_of=as_of)

def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,default=Path("."))
    a=p.parse_args()
    print(json.dumps(from_root(a.root,as_of=datetime.now(timezone.utc).isoformat()),sort_keys=True,allow_nan=False))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
