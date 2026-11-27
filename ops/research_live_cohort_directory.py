"""Private, bounded, manifest-indexed cohort loader for V10 research.
Local hashes bind bytes, not time, publisher authenticity or cohort completeness.
"""
import argparse
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from .research_live_intake_v4 import decode, MAX_BYTES
from .research_live_pipeline_v10 import review, safety, MAX_CASES

MAX_TOTAL=64*1024*1024
SCHEMA="private-live-cohort-manifest-v1"

def read_at(fd,name,limit):
    if not isinstance(name,str) or not re.fullmatch(r"(manifest|[0-9a-f]{64})\.json",name):
        raise ValueError("invalid member name")
    flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK
    with os.fdopen(os.open(name,flags,dir_fd=fd),"rb") as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or not 0<info.st_size<=limit:
            raise ValueError("invalid member")
        raw=stream.read(limit+1)
        if len(raw)!=info.st_size or len(raw)>limit:
            raise ValueError("member size changed")
        return raw

def open_root(root):
    root=Path(root).absolute()
    if ".." in root.parts:
        raise ValueError("invalid root")
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
    fd=os.open(root.anchor,flags)
    try:
        for part in root.parts[1:]:
            child=os.open(part,flags,dir_fd=fd)
            os.close(fd);fd=child
        return fd
    except BaseException:
        os.close(fd);raise

def load(root):
    """Strict directory roster, byte hashes, per-file and aggregate limits."""
    fd=open_root(root)
    try:
        manifest_raw=read_at(fd,"manifest.json",MAX_BYTES)
        manifest=decode(manifest_raw)
        if manifest["schema"]!=SCHEMA or set(manifest)!={"schema","model_release","train_start","train_cutoff","test_end","members"}:
            raise ValueError("invalid manifest")
        members=manifest["members"]
        if not isinstance(members,list) or len(members)>MAX_CASES:
            raise ValueError("invalid roster")
        if any(not isinstance(x,str) or not re.fullmatch("[0-9a-f]{64}",x) for x in members):
            raise ValueError("invalid digest")
        if len(members)!=len(set(members)):
            raise ValueError("duplicate member")
        expected={"manifest.json",*(x+".json" for x in members)}
        if set(os.listdir(fd))!=expected:
            raise ValueError("directory roster mismatch")
        total=len(manifest_raw);cases=[]
        for sha in sorted(members):
            raw=read_at(fd,sha+".json",min(MAX_BYTES,MAX_TOTAL-total))
            total+=len(raw)
            if total>MAX_TOTAL or hashlib.sha256(raw).hexdigest()!=sha:
                raise ValueError("member digest or total size")
            case=decode(raw)
            captures=case["raw_captures"]
            if not isinstance(captures,list) or len(captures) not in (5,6):
                raise ValueError("invalid capture roster")
            if any(not isinstance(x,str) or not re.fullmatch(r"(?:[0-9a-fA-F]{2})+",x) for x in captures):
                raise ValueError("invalid capture encoding")
            case["raw_captures"]=[bytes.fromhex(x) for x in captures]
            cases.append(case)
        if set(os.listdir(fd))!=expected or read_at(fd,"manifest.json",MAX_BYTES)!=manifest_raw:
            raise ValueError("manifest changed during read")
        return manifest,cases,total,hashlib.sha256(manifest_raw).hexdigest()
    finally:
        os.close(fd)

def run(root, *, as_of, require_source_binding=False):
    try:
        m,cases,size,sha=load(root)
        out=review(cases,model_release=m["model_release"],train_start=m["train_start"],
                   train_cutoff=m["train_cutoff"],test_end=m["test_end"],as_of=as_of,
                   require_source_binding=require_source_binding)
        out.update(manifest_sha256=sha,submitted_member_count=len(cases),submitted_bytes=size,
                   directory_roster_verified=True,external_anchor_verified=False)
        return out
    except (OSError,KeyError,TypeError,ValueError,AttributeError,OverflowError,RecursionError):
        return {**safety(),"pipeline_replay_passed":False,"reason":"INVALID_PRIVATE_COHORT"}

def public_summary(report):
    """Avoid presenting a redacted policy as a replay-verifiable full policy."""
    import copy
    out=copy.deepcopy(report)
    cal=out.get("calibration_research")
    if cal and "frozen_policy" in cal:
        policy=cal.pop("frozen_policy")
        cal["policy_summary"]={"weight":policy["weight"],"train_cutoff":policy["train_cutoff"],
                               "full_private_policy_sha256":policy["sha256"],
                               "training_event_count":len(policy["training_event_ids"]),
                               "redacted_not_replayable":True}
    return out

def main():
    p=argparse.ArgumentParser(description="Private local manifest cohort research review")
    p.add_argument("--directory",type=Path,required=True)
    p.add_argument("--require-source-binding",action="store_true")
    a=p.parse_args()
    report=run(a.directory,as_of=datetime.now(timezone.utc).isoformat(),
               require_source_binding=a.require_source_binding)
    print(json.dumps(public_summary(report),sort_keys=True,allow_nan=False))
    return 0 if report.get("pipeline_replay_passed") else 2

if __name__=="__main__":
    raise SystemExit(main())
