"""Private, offline real-capture bundle runner for LIVE-CORE.

Input is an explicitly authorized local directory, never a repository of raw
commercial provider data. This does not fetch providers or verify entitlement.
No secrets, raw payloads or price values are emitted. No forward/EV credit.
"""
import argparse
import hashlib
import json
from pathlib import Path
from live_core_sportmonks_capture import dual_run
from live_snapshot_adapter import hold
from vnext_direct_transport_offline import unique_object,reject_constant

LIMIT=1200000
MANIFEST_LIMIT=100000
FILES=("api-football.json","sportmonks.json")
FIELDS={"schema","primary_sha256","secondary_sha256","primary_mapping",
        "secondary_mapping","primary_clock","secondary_clock","decision_epoch",
        "prematch","markets","quotes","capture_rights_confirmed_by_operator"}


def read_local(root,name,limit):
    p=root/name
    if p.is_symlink() or not p.is_file():
        raise ValueError("MISSING_OR_UNSAFE_FILE")
    with p.open("rb") as f:
        b=f.read(limit+1)
    if not 0<len(b)<=limit:
        raise ValueError("FILE_SIZE")
    return b


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_bundle(directory):
    root=Path(directory).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("BUNDLE_DIRECTORY")
    manifest=read_local(root,"manifest.json",MANIFEST_LIMIT)
    m=json.loads(manifest.decode("utf-8"),object_pairs_hook=unique_object,
                 parse_constant=reject_constant)
    if type(m) is not dict or set(m)!=FIELDS or m["schema"]!="live-core-private-capture-v1":
        raise ValueError("MANIFEST_SCHEMA")
    if m["capture_rights_confirmed_by_operator"] is not True:
        raise ValueError("CAPTURE_RIGHTS_NOT_CONFIRMED")
    a,b=(read_local(root,n,LIMIT) for n in FILES)
    if digest(a)!=m["primary_sha256"] or digest(b)!=m["secondary_sha256"]:
        raise ValueError("CAPTURE_DIGEST_MISMATCH")
    if type(m["decision_epoch"]) is not int:
        raise ValueError("DECISION_EPOCH")
    return m,a,b,digest(manifest)


def run_bundle(directory):
    try:
        m,a,b,manifest_digest=load_bundle(directory)
        out=dual_run(a,m["primary_mapping"],b,m["secondary_mapping"],
                     primary_clock=m["primary_clock"],secondary_clock=m["secondary_clock"],
                     now=m["decision_epoch"],prematch=m["prematch"],markets=m["markets"],
                     quotes=m["quotes"])
        # Never echo input URLs or raw price claims.
        out.pop("xg_claim_same_cut",None)
        out.pop("quote_reviews",None)
        return {**out,"bundle_manifest_sha256":manifest_digest,
                "historical_replay":True,"capture_rights_independently_verified":False,
                "source_authenticated":False,"source_independence_verified":False,
                "actual_xg_verified":False,"actual_live_odds_verified":False,
                "positive_ev_verified":False,"verified_forward_sample_credit":0,
                "production_recommendations":"DISABLED","status":"HOLD"}
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return hold("PRIVATE_CAPTURE_BUNDLE_REJECTED")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory",type=Path)
    args=p.parse_args()
    print(json.dumps(run_bundle(args.directory),allow_nan=False,sort_keys=True))


if __name__=="__main__":
    main()
