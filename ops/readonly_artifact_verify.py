"""Read exact GitHub rehearsal artifact bytes; no forward qualification implied."""
import argparse
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime,timedelta,timezone
from pathlib import Path

try:
    from .opponent_forward_capture import TOP_KEY,attach
except ImportError:
    from opponent_forward_capture import TOP_KEY,attach

MAX_ZIP=8_000_000
MAX_SHADOW=8_000_000
MAX_MANIFEST=32_000


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def unique(pairs):
        obj={}
        for k,v in pairs:
            if k in obj:
                raise ValueError("DUPLICATE_JSON_KEY")
            obj[k]=v
        return obj
    def reject(_):
        raise ValueError("NONFINITE_JSON")
    return json.loads(raw,object_pairs_hook=unique,parse_constant=reject)


def utc(value):
    d=datetime.fromisoformat(value)
    if d.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return d.astimezone(timezone.utc)


def verify_artifact(path,expected_sha256,expected_run_id,expected_attempt,*,include_shadow_bytes=False):
    """The expected ZIP digest must come from trusted run metadata, not the ZIP."""
    if not isinstance(expected_sha256,str) or not re.fullmatch(r"[a-f0-9]{64}",expected_sha256):
        raise ValueError("INVALID_EXPECTED_DIGEST")
    if not all(isinstance(x,str) and re.fullmatch(r"[0-9]{1,20}",x)
               for x in (expected_run_id,expected_attempt)):
        raise ValueError("INVALID_RUN_IDENTITY")
    with Path(path).open("rb") as f:
        raw=f.read(MAX_ZIP+1)
    if len(raw)>MAX_ZIP or digest(raw)!=expected_sha256:
        raise ValueError("ARTIFACT_DIGEST_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos=z.infolist()
        if len(infos)!=2 or {i.filename for i in infos}!={"shadow.json","manifest.json"}:
            raise ValueError("UNEXPECTED_ARTIFACT_MEMBERS")
        for i in infos:
            limit=MAX_MANIFEST if i.filename=="manifest.json" else MAX_SHADOW
            if not 0<i.file_size<=limit or i.flag_bits&1:
                raise ValueError("INVALID_MEMBER_SIZE_OR_ENCRYPTION")
        def read(name,limit):
            with z.open(name) as f:
                data=f.read(limit+1)
            if len(data)>limit:
                raise ValueError("MEMBER_TOO_LARGE")
            return data
        shadow_bytes=read("shadow.json",MAX_SHADOW)
        m=parse(read("manifest.json",MAX_MANIFEST))
    doc=parse(shadow_bytes)
    if (not isinstance(m,dict) or not isinstance(doc,dict)
        or m.get("schema")!="football-king-readonly-research-evidence-v1"
        or m.get("run_id")!=expected_run_id or m.get("run_attempt")!=expected_attempt
        or m.get("shadow_sha256")!=digest(shadow_bytes)
        or type(m.get("shadow_bytes")) is not int or m["shadow_bytes"]!=len(shadow_bytes)
        or m.get("production_recommendations")!="DISABLED"
        or m.get("attestation_performed") is not False
        or m.get("artifact_upload_time_independently_verified") is not False
        or type(m.get("authenticated_forward_samples")) is not int or m["authenticated_forward_samples"]!=0
        or not all(isinstance(m.get(k),str) and re.fullmatch(r"[a-f0-9]{40}",m[k])
                   for k in ("checkout_commit","workflow_sha"))):
        raise ValueError("INVALID_MANIFEST")
    if (doc.get("schema")!="football-king-uncalibrated-shadow-1"
        or doc.get("production_recommendations")!="DISABLED"
        or type(doc.get("predictions_count")) is not int
        or doc["predictions_count"]!=len(doc["predictions"])):
        raise ValueError("INVALID_SHADOW")
    original=dict(doc)
    cap=original.pop(TOP_KEY)
    attach(original,cap)
    rows=cap["predictions"]
    packaged=utc(m["packaged_utc"])
    generated=utc(cap["generated_utc"])
    if not timedelta(0)<=packaged-generated<=timedelta(minutes=30):
        raise ValueError("INVALID_PACKAGING_CLOCK")
    leads=[(utc(r["kickoff_utc"])-packaged).total_seconds() for r in rows]
    if (type(m.get("candidate_count")) is not int or m["candidate_count"]!=len(rows)
        or m.get("candidate_leagues")!=sorted({r["league"] for r in rows})
        or m.get("all_candidates_more_than_10min_at_packaging") is not (bool(leads) and min(leads)>600)
        or m.get("minimum_recorded_kickoff_lead_seconds")!=(min(leads) if leads else None)):
        raise ValueError("INCONSISTENT_CANDIDATE_MANIFEST")
    if rows and not m["all_candidates_more_than_10min_at_packaging"]:
        raise ValueError("PACKAGED_TOO_LATE")
    report={"schema":"football-king-readonly-artifact-audit-v1",
                "status":"RESEARCH_BYTES_VERIFIED","run_id":expected_run_id,
                "run_attempt":expected_attempt,"zip_sha256":expected_sha256,
                "shadow_sha256":m["shadow_sha256"],"candidate_count":len(rows),
                "candidate_leagues":m["candidate_leagues"],"packaged_utc":m["packaged_utc"],
                "authenticated_forward_samples":0,"attestation_verified":False,
                "artifact_upload_time_independently_verified":False,
                "production_recommendations":"DISABLED"}
    return (doc,report,shadow_bytes) if include_shadow_bytes else (doc,report)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--artifact",required=True);p.add_argument("--sha256",required=True)
    p.add_argument("--run-id",required=True);p.add_argument("--attempt",required=True)
    a=p.parse_args()
    _,report=verify_artifact(a.artifact,a.sha256,a.run_id,a.attempt)
    print(json.dumps(report,sort_keys=True))


if __name__=="__main__":
    main()
