"""Prepare three immutable research archives without editing predictions."""
import argparse
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

FOLDERS={"asof":"history","shadow":"shadow","paired":"research_pairs"}

def prepare(snapshot, destination, run_id, attempt, *, day=None):
    if not str(run_id).isdigit() or not str(attempt).isdigit():
        raise ValueError("INVALID_RUN_ID")
    day=day or datetime.now(timezone.utc).strftime("%Y/%m/%d")
    if len(day)!=10 or day[4]!="/" or day[7]!="/" or not day.replace("/","").isdigit():
        raise ValueError("INVALID_DAY")
    created=[]
    for kind,folder in FOLDERS.items():
        raw=(Path(snapshot)/(kind+".json")).read_bytes()
        if not raw or len(raw)>8_000_000 or not isinstance(json.loads(raw),dict):
            raise ValueError("INVALID_SNAPSHOT")
        target=Path(destination)/folder/day/(str(run_id)+"-"+str(attempt)+".json.gz")
        payload=gzip.compress(raw,mtime=0)
        if target.exists():
            if target.read_bytes()!=payload:
                raise ValueError("IMMUTABLE_ARCHIVE_COLLISION")
            continue
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(payload)
        created.append(str(target.relative_to(destination)))
    return created

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--snapshot",required=True)
    p.add_argument("--destination",required=True)
    p.add_argument("--run-id",required=True)
    p.add_argument("--attempt",required=True)
    a=p.parse_args()
    print(json.dumps({"created":prepare(a.snapshot,a.destination,a.run_id,a.attempt)}))

if __name__=="__main__":
    main()
