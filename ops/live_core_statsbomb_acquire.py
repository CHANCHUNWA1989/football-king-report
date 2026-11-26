"""Explicit opt-in, private acquisition of frozen StatsBomb WC2022 Git blobs.

No network in tests, no credentials, no publication. Operator must separately
confirm permitted research use and comply with attribution requirements.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.request import Request, build_opener, HTTPRedirectHandler

from live_core_statsbomb_wc2022_pins import INDEX_BLOB, EVENT_BLOBS

INDEX_SIZE=119132
MAX_BLOB=12_000_000
MAX_BATCH=210_000_000

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError("UNEXPECTED_REDIRECT")

def _open(request,timeout):
    return build_opener(NoRedirect()).open(request,timeout=timeout)

def fetch_blob(pin,size,path):
    if not isinstance(pin,str) or not re.fullmatch(r"[a-f0-9]{40}",pin):
        raise ValueError("INVALID_BLOB_PIN")
    if type(size) is not int or not 0<size<=MAX_BLOB:
        raise ValueError("INVALID_BLOB_SIZE")
    if not isinstance(path,str) or not (path=="data/matches/43/106.json" or re.fullmatch(r"data/events/[0-9]{1,12}\.json",path)):
        raise ValueError("INVALID_SOURCE_PATH")
    # Public raw endpoint avoids 65 calls to the anonymous REST API. The
    # mutable branch is transport only: every byte must match its frozen pin.
    request=Request("https://raw.githubusercontent.com/hudl/open-data/master/"+path,
                    headers={"Accept":"application/octet-stream",
                             "User-Agent":"football-king-private-research"})
    with _open(request,timeout=20) as response:
        raw=response.read(size+1)
    if len(raw)!=size:
        raise ValueError("BLOB_LENGTH_MISMATCH")
    if hashlib.sha1(("blob "+str(size)+"\0").encode()+raw).hexdigest()!=pin:
        raise ValueError("BLOB_DIGEST_MISMATCH")
    return raw

def acquire(destination,*,rights_confirmed=False):
    if rights_confirmed is not True:
        raise ValueError("OPERATOR_RIGHTS_CONFIRMATION_REQUIRED")
    target=Path(destination).absolute()
    if target.exists() or target.is_symlink():
        raise ValueError("DESTINATION_EXISTS")
    parent=target.parent.resolve(strict=True)
    target=parent/target.name
    repo=Path(__file__).resolve().parents[1]
    if target==repo or repo in target.parents:
        raise ValueError("DESTINATION_MUST_BE_OUTSIDE_REPOSITORY")
    if not parent.is_dir():
        raise ValueError("INVALID_DESTINATION_PARENT")
    if len(EVENT_BLOBS)>64 or INDEX_SIZE+sum(size for _,size in EVENT_BLOBS.values())>MAX_BATCH:
        raise ValueError("BATCH_LIMIT")
    if any(not re.fullmatch(r"[0-9]{1,12}",mid) for mid in EVENT_BLOBS):
        raise ValueError("INVALID_MATCH_ID")
    staging=Path(tempfile.mkdtemp(prefix=".wc2022-private-",dir=parent))
    try:
        def save(name,data):
            with (staging/name).open("xb") as f:
                os.fchmod(f.fileno(),0o600)
                f.write(data)
        save("matches.json",fetch_blob(INDEX_BLOB,INDEX_SIZE,"data/matches/43/106.json"))
        for mid,(pin,size) in sorted(EVENT_BLOBS.items()):
            save(mid+".json",fetch_blob(pin,size,"data/events/"+mid+".json"))
        manifest={"schema":"statsbomb-private-wc2022-v1","rights_confirmed":True,
                  "event_blob_pins":{mid:pin for mid,(pin,_) in EVENT_BLOBS.items()}}
        save("manifest.json",json.dumps(manifest,sort_keys=True).encode())
        # Reserve the destination exclusively before moving files. Never replace
        # an existing operator directory, even if it appeared during downloads.
        target.mkdir(mode=0o700,exist_ok=False)
        try:
            for item in sorted(staging.iterdir(),key=lambda p:p.name=="manifest.json"):
                os.link(item,target/item.name)
        except BaseException:
            shutil.rmtree(target)
            raise
    finally:
        shutil.rmtree(staging)
    return {"downloaded":len(EVENT_BLOBS),"index_verified":True,
            "byte_identity_verified":True,"source_authenticated":False,
            "production_recommendations":"DISABLED","status":"HOLD"}

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("destination",type=Path)
    p.add_argument("--confirm-research-rights",action="store_true")
    args=p.parse_args()
    print(json.dumps(acquire(args.destination,rights_confirmed=args.confirm_research_rights),sort_keys=True))
