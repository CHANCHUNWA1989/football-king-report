"""Fill historical archive date gaps and prioritize missing team history.

The scan selectors are calendar dates, not invented fixture records.
No new forecasts, source requests, training admission or production changes.
"""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
from .research_candidate_gap_v6 import stamp
from .research_missing_fixture_discovery_v16 import candidates
from .research_live_intake_v4 import MAX_BYTES
from .research_archive_score_recovery_v14 import archive_snapshots
from .research_two_publisher_recovery_v15 import secondary_snapshots
from .research_supplemental_history_v32 import inventory

MAX_DAYS=90
def selectors(rows,*,primary):
    if not rows:raise ValueError("empty ledger")
    first=min(stamp(r["forecast_utc"]).date() for r in rows.values())
    last=max(stamp(r["forecast_utc"]).date() for r in rows.values())
    n=(last-first).days+1
    if not 1<=n<=MAX_DAYS:raise ValueError("calendar scan budget")
    selected={k:r for k,r in rows.items() if not primary or k[0]=="bundesliga"}
    window=4 if primary else 8
    covered={stamp(r["kickoff_utc"]).date()+timedelta(days=i)
             for r in selected.values() for i in range(window)}
    missing=[first+timedelta(days=i) for i in range(n) if first+timedelta(days=i) not in covered]
    # Existing iterators only read kickoff_utc to select date folders.
    # Strings below are date selectors; never passed into the fixture ledger.
    for day in missing:
        selected[("calendar-selector",day)]={"kickoff_utc":day.isoformat()+"T00:00:00Z"}
    return selected,[x.isoformat() for x in missing]

def from_root(root,*,as_of):
    with (root/"evidence/settled.json").open("rb") as f:raw=f.read(MAX_BYTES+1)
    rows=candidates(raw)
    a,missing_a=selectors(rows,primary=True)
    b,missing_b=selectors(rows,primary=False)
    report=inventory(raw,archive_snapshots(root/"sources/live_germany/history",a),
        secondary_snapshots(root/"sources/history",b),as_of=as_of,include_gap_detail=True)
    return {"schema":"historical-calendar-gap-priority-v33",
            "status":"HOLD","production_recommendations":"DISABLED",
            "primary_added_date_selectors":missing_a,"secondary_added_date_selectors":missing_b,
            "inventory":report,"authenticated_samples":0,"training_admission":False,
            "model_promotion_allowed":False}

def main():
    print(json.dumps(from_root(Path("."),as_of=datetime.now(timezone.utc).isoformat()),sort_keys=True,allow_nan=False))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
