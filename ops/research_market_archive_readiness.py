"""Read-only diagnostic: distinguish archive activity from fresh market data.
Never select an older snapshot for prediction, refresh a feed, or mutate latest.
"""
from collections import Counter
from datetime import datetime,timedelta,timezone
import gzip
import json
from pathlib import Path
import re
from .research_candidate_gap_v6 import stamp
from .research_live_intake_v4 import decode,MAX_BYTES
from .research_prospective_market_v41 import audit
from .research_prospective_fusion_v38 import sha

MAX_FILES=256

def scan(root,*,as_of):
    now=stamp(as_of)
    root=Path(root).absolute()
    base=root/"market"
    if any(p.is_symlink() for p in (root,*root.parents,base,base/"history")):
        raise ValueError("unsafe archive root")
    latest=base/"latest.json"
    if latest.is_symlink() or not latest.is_file():
        raise ValueError("missing latest")
    with latest.open("rb") as f:raw=f.read(MAX_BYTES+1)
    current=audit(raw,as_of=as_of)
    clock=stamp(current["snapshot_captured_utc"])
    counts=Counter();states=Counter();reasons=Counter();seen=set();newest=None
    for day in (now.date()-timedelta(days=1),now.date()):
        folder=base/"history"/day.strftime("%Y/%m/%d")
        if any(p.is_symlink() for p in (folder,*folder.parents)):
            raise ValueError("unsafe archive directory")
        if not folder.is_dir():continue
        for p in sorted(folder.iterdir()):
            if not re.fullmatch(r"[1-9][0-9]{0,19}-[1-9][0-9]{0,9}\.json\.gz",p.name):continue
            counts["files_seen"]+=1
            if counts["files_seen"]>MAX_FILES:raise ValueError("archive budget")
            try:
                if p.is_symlink() or not p.is_file() or not 0<p.stat().st_size<=MAX_BYTES:
                    raise ValueError("unsafe file")
                with gzip.open(p,"rb") as f:body=f.read(MAX_BYTES+1)
                r=audit(body,as_of=as_of);doc=decode(body)
                t=stamp(r["snapshot_captured_utc"])
                counts["valid_files"]+=1
                states[doc["status"]]+=1
                if doc["status"]=="HOLD":
                    reason=doc.get("reason")
                    if isinstance(reason,str) and re.fullmatch("[A-Z0-9_]{1,80}",reason):
                        reasons[reason]+=1
                    else:reasons["OTHER_OR_MISSING"]+=1
                digest=sha(body)
                seen.add(digest)
                if t>clock:counts["newer_than_latest"]+=1
                if r["market_components"]:counts["fresh_component_files"]+=1
                if newest is None or t>newest:newest=t
            except (OSError,EOFError,ValueError,KeyError,TypeError,AttributeError,OverflowError,RecursionError):
                counts["invalid_files"]+=1
    return {"schema":"market-archive-readiness-v48","status":"HOLD","production_recommendations":"DISABLED",
            "latest":current,"archive_counts":dict(counts),"archive_statuses":dict(states),
            "archive_hold_reasons":dict(reasons),"unique_decoded_archives":len(seen),
            "newest_archive_capture_utc":newest.isoformat() if newest else None,
            "window_utc_dates":2,"provider_calls_made":0,"latest_modified":False,
            "source_authenticity_verified":False,"authenticated_samples":0}

def main():
    print(json.dumps(scan(Path("."),as_of=datetime.now(timezone.utc).isoformat()),sort_keys=True,allow_nan=False))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
