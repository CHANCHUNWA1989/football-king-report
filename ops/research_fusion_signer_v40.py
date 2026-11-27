"""Prepare and verify a run-scoped fusion proof from sanitized committed input.

No provider calls, secrets, automatic publication or production promotion.
The source claims in the input remain unverified.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
from .research_live_intake_v4 import decode,MAX_BYTES
from .research_prospective_fusion_v38 import capture,canonical,sha,exact
from .research_fusion_witness_v39 import verify

def read(path):
    if path.is_symlink() or not path.is_file():raise ValueError("unsafe input")
    with path.open("rb") as f:b=f.read(MAX_BYTES+1)
    if not 0<len(b)<=MAX_BYTES:raise ValueError("input size")
    return b

def prepare(root,digest,*,now):
    if not isinstance(digest,str) or not re.fullmatch("[0-9a-f]{64}",digest):
        raise ValueError("invalid input digest")
    directory=root/"research"/"fusion-inputs"
    if any(p.is_symlink() for p in (root,root/"research",directory)):
        raise ValueError("unsafe source directory")
    body=read(directory/(digest+".json"))
    if sha(body)!=digest:raise ValueError("input digest mismatch")
    d=decode(body)
    exact(d,"schema event_id league home away kickoff_utc market history")
    if d["schema"]!="prospective-fusion-draft-v40":raise ValueError("draft schema")
    # The actual trusted runner clock, not a user supplied forecast timestamp.
    d.update(schema="prospective-fusion-input-v38",forecast_utc=now)
    raw=canonical(d)
    receipt=capture(raw,as_of=now)
    if receipt["candidate"]["state"]!="RESEARCH_CANDIDATE":
        raise ValueError("no fresh market candidate")
    return raw,canonical(receipt)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("prepare");a.add_argument("--digest",required=True);a.add_argument("--output",type=Path,required=True)
    b=sub.add_parser("verify");b.add_argument("--proof",type=Path,required=True)
    for flag in ("source-sha","workflow-sha","run-id","attempt"):b.add_argument("--"+flag,required=True)
    args=p.parse_args()
    now=datetime.now(timezone.utc).isoformat()
    try:
        if args.command=="prepare":
            raw,receipt=prepare(Path("."),args.digest,now=now)
            args.output.mkdir(mode=0o700,parents=False,exist_ok=False)
            (args.output/"fusion-input.json").write_bytes(raw)
            (args.output/"fusion-receipt.json").write_bytes(receipt)
            print("FUSION_LOCAL_RECEIPT_PREPARED")
        else:
            d=args.proof
            r=verify(read(d/"fusion-input.json"),read(d/"fusion-receipt.json"),
                     read(d/"fusion.sigstore.json"),source_sha=args.source_sha,
                     workflow_sha=args.workflow_sha,run_id=args.run_id,attempt=args.attempt,as_of=now)
            (d/"witness-audit.json").write_bytes(canonical(r))
            print(json.dumps({"verification_completed":r["verification_completed"],"status":"HOLD",
                              "authenticated_samples":0,"production_recommendations":"DISABLED"}))
            if not r["verification_completed"]:return 1
    except (OSError,KeyError,ValueError,TypeError,AttributeError,OverflowError,RecursionError):
        print("FUSION_WITNESS_INPUT_OR_VERIFICATION_REJECTED")
        return 1
    return 0
if __name__=="__main__":
    raise SystemExit(main())
