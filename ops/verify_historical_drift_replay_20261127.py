"""Fetch only pinned public Git blobs, verify identity, reproduce drift replay."""
from hashlib import sha1
from json import dumps
from math import isclose
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from time import sleep
from ops.historical_drift_replay_20261127 import MANIFEST,SEASONS,run
LIMIT=2_000_000
EXPECTED=(
    {"one_x_two":1.002816286731799,"exact":3.0754145935632287,"brier":.5987411435806715,
     "tail_p":.19579754208026867,"tail_brier":.1566382630892891,"tail_actual":.1956997084548105},
    {"one_x_two":1.0019501098426136,"exact":3.0774641209214737,"brier":.59821581681019,
     "tail_p":.19879217102471664,"tail_brier":.1571403279177455,"tail_actual":.1956997084548105},
)
UPSTREAM_COMMIT="e6744429ee395bc86f247348c6184bb08d4eb361"

def fetch_blob(blob,season,name):
    allowed={(s,n,b) for n,_,blobs in MANIFEST.values() for s,b in zip(SEASONS,blobs)}
    if (season,name,blob) not in allowed:
        raise ValueError("unregistered source object")
    # Use immutable raw file URL rather than the unauthenticated REST quota.
    url=f"https://raw.githubusercontent.com/openfootball/football.json/{UPSTREAM_COMMIT}/{season}/{name}"
    req=Request(url,headers={"User-Agent":"football-king-offline-research"})
    for attempt in range(3):
        try:
            with urlopen(req,timeout=20) as response:
                raw=response.read(LIMIT+1)
            break
        except HTTPError as e:
            if e.code not in (429,500,502,503,504) or attempt==2: raise
        except (URLError,TimeoutError):
            if attempt==2: raise
        sleep(2**attempt)
    if not 0<len(raw)<=LIMIT: raise ValueError("invalid blob size")
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
                path.write_bytes(fetch_blob(blob,season,name))
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
