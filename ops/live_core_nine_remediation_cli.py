"""Private CLI for the multi-cut repair; no network or credentials.

python ops/live_core_nine_remediation_cli.py /private/authorized-history
"""
import argparse
import hashlib
import json
from pathlib import Path
from live_core_nine_remediation import review
from live_core_provider_evidence import MAX_BYTES
from live_snapshot_adapter import hold
from vnext_direct_transport_offline import unique_object,reject_constant

MANIFEST_KEYS={"schema","capture_rights_confirmed_by_operator","primary_mapping",
               "secondary_mapping","prematch","markets","quotes","context","cuts"}
CUT_KEYS={"now","primary_clock","secondary_clock","primary_sha256","secondary_sha256"}


def bounded(root,name,limit):
    p=root/name
    if p.is_symlink() or not p.is_file():
        raise ValueError("INVALID_LOCAL_FILE")
    with p.open("rb") as f:
        raw=f.read(limit+1)
    if not 0<len(raw)<=limit:
        raise ValueError("FILE_SIZE")
    return raw


def run_bundle(path):
    try:
        root=Path(path).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("BUNDLE_DIRECTORY")
        raw=bounded(root,"manifest.json",256000)
        m=json.loads(raw.decode("utf-8"),object_pairs_hook=unique_object,parse_constant=reject_constant)
        if type(m) is not dict or set(m)!=MANIFEST_KEYS or m["schema"]!="nine-core-private-history-v1" or m["capture_rights_confirmed_by_operator"] is not True:
            raise ValueError("MANIFEST")
        if type(m["cuts"]) is not list or not 2<=len(m["cuts"])<=48:
            raise ValueError("CUT_COUNT")
        cuts=[]
        for i,c in enumerate(m["cuts"],1):
            if type(c) is not dict or set(c)!=CUT_KEYS:
                raise ValueError("CUT_SCHEMA")
            a=bounded(root,f"{i:02d}-api-football.json",MAX_BYTES)
            b=bounded(root,f"{i:02d}-sportmonks.json",MAX_BYTES)
            if hashlib.sha256(a).hexdigest()!=c["primary_sha256"] or hashlib.sha256(b).hexdigest()!=c["secondary_sha256"]:
                raise ValueError("CAPTURE_DIGEST_MISMATCH")
            cuts.append(dict(primary_raw=a,secondary_raw=b,
                             now=c["now"],primary_clock=c["primary_clock"],secondary_clock=c["secondary_clock"]))
        result=review(cuts,primary_mapping=m["primary_mapping"],secondary_mapping=m["secondary_mapping"],
                      prematch=m["prematch"],markets=m["markets"],quotes=m["quotes"],context=m["context"])
        return {**result,"manifest_sha256_unattested":hashlib.sha256(raw).hexdigest(),
                "capture_rights_independently_verified":False}
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return hold("INVALID_PRIVATE_HISTORY_BUNDLE")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory",type=Path)
    args=p.parse_args()
    print(json.dumps(run_bundle(args.directory),allow_nan=False,sort_keys=True))


if __name__=="__main__":
    main()
