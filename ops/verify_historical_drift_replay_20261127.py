"""Fetch only pinned public Git blobs, verify identity, reproduce drift replay."""
from base64 import b64decode
from hashlib import sha1
from json import loads,dumps
from math import isclose
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import Request,urlopen
from ops.historical_drift_replay_20261127 import MANIFEST,SEASONS,run
LIMIT=2_000_000
EXPECTED=(
    {"one_x_two":1.002816286731799,"exact":3.0754145935632287,"brier":.5987411435806715,
     "tail_p":.19579754208026867,"tail_brier":.1566382630892891,"tail_actual":.1956997084548105},
    {"one_x_two":1.0019501098426136,"exact":3.0774641209214737,"brier":.59821581681019,
     "tail_p":.19879217102471664,"tail_brier":.1571403279177455,"tail_actual":.1956997084548105},
)
def fetch_blob(blob):
    if len(blob)!=40 or any(c not in "0123456789abcdef" for c in blob):
        raise ValueError("invalid pinned SHA")
    url="https://api.github.com/repos/openfootball/football.json/git/blobs/"+blob
    req=Request(url,headers={"Accept":"application/vnd.github+json","User-Agent":"football-king-offline-research"})
    with urlopen(req,timeout=20) as response:
        data=response.read(LIMIT+1)
    if len(data)>LIMIT: raise ValueError("response too large")
    obj=loads(data)
    if obj.get("sha")!=blob or obj.get("encoding")!="base64": raise ValueError("unexpected blob response")
    raw=b64decode("".join(obj["content"].split()),validate=True)
    if len(raw)>LIMIT or len(raw)!=obj.get("size"): raise ValueError("invalid blob size")
    if sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()!=blob:
        raise ValueError("pinned content mismatch")
    return raw

def main():
    with TemporaryDirectory() as temp:
        root=Path(temp)
        for name,_,blobs in MANIFEST.values():
            for season,blob in zip(SEASONS,blobs):
                path=root/season/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(fetch_blob(blob))
        report=run(root)
        if report["test"]!=2744 or report["correct"]!=[1411,1410]:
            raise AssertionError("fixture or hit count mismatch")
        for actual,expected in zip(report["combined"],EXPECTED):
            for k,v in expected.items():
                if not isclose(actual[k],v,rel_tol=0,abs_tol=1e-9):
                    raise AssertionError(f"replay mismatch: {k} {actual[k]} != {v}")
        print(dumps({"pinned_blobs":10,"matches":report["test"],"correct":report["correct"],
                     "metrics":report["combined"],"numeric_reproduction":True,
                     "prospective_verified":False,"positive_ev_verified":False,
                     "deployment":"HOLD","recommendations":"DISABLED"},indent=2))
if __name__=="__main__": main()
