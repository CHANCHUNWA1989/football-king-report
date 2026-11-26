"""V6.2 archive integrity verification, never independent outcome authentication."""
import argparse
import io
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zipfile import ZipFile
from ops.v6_forward_bundle import utc,decode,digest
from ops.v6_forward_comparison import seal,score,sha

FILES=("forward-comparison.json","forward-bundle.json","league-calibration.json")
LIMIT=3_000_000

def audit(raw,expected,created):
    if not 0<len(raw)<=LIMIT or sha(raw)!=digest(expected):raise ValueError("ARCHIVE_DIGEST_MISMATCH")
    with ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist()
        if len(names)>50 or len(names)!=len(set(names)):raise ValueError("DUPLICATE_OR_OVERSIZED_ARCHIVE")
        parts={}
        for name in FILES:
            if name not in names:raise ValueError("MISSING_COMPONENT")
            member=z.getinfo(name)
            if not 0<member.file_size<=LIMIT or member.is_dir():raise ValueError("BAD_COMPONENT_SIZE")
            parts[name]=z.read(member)
    record,bundle,cal=[decode(parts[k]) for k in FILES]
    if record.get("input_sha256")!=[sha(parts[FILES[1]]),sha(parts[FILES[2]])]:raise ValueError("INPUT_DIGEST_MISMATCH")
    stamp=utc(record["sealed_utc"])
    if created.utcoffset() is None or not 0<=(created-stamp).total_seconds()<=600:raise ValueError("ARTIFACT_CLOCK")
    rebuilt=seal(bundle,cal,stamp)
    if rebuilt!={k:v for k,v in record.items() if k!="input_sha256"}:raise ValueError("SEALED_RECORD_MISMATCH")
    if any(utc(r["kickoff_utc"])<=created+timedelta(minutes=10) for r in record["rows"]):raise ValueError("LATE_ARTIFACT")
    return record,{"archive_sha256":expected,"artifact_created_utc":created.isoformat(),
        "sealed_utc":stamp.isoformat(),"sealed_count":len(record["rows"]),
        "component_sha256":{k:sha(v) for k,v in parts.items()},
        "archive_and_component_integrity_checked":True,
        "expected_digest_origin_independently_authenticated":False,
        "external_capture_witness_verified":False,"verified_forward_sample_credit":0,
        "production_recommendations":"DISABLED","status":"HOLD"}

def main():
    p=argparse.ArgumentParser()
    for k in ("archive","sha256","created-utc","output"):p.add_argument("--"+k,required=True)
    p.add_argument("--results");a=p.parse_args()
    f=Path(a.archive)
    if not 0<f.stat().st_size<=LIMIT:raise ValueError("ARCHIVE_SIZE")
    record,out=audit(f.read_bytes(),a.sha256,utc(a.created_utc))
    if a.results:
        f=Path(a.results)
        if not 0<f.stat().st_size<=LIMIT:raise ValueError("RESULT_SIZE")
        raw=f.read_bytes()
        out["result_sha256"]=sha(raw)
        out["settlement"]=score(record,decode(raw),datetime.now(timezone.utc))
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
