"""Bounded long-horizon inventory of already captured research forecasts.

This is a coverage inventory, not a settlement, signature verifier, or model
qualification. No network, outcome labels, or historical forecast rewrites.
"""
import argparse
import gzip
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from .opponent_forward_audit import candidates, matching_dc, dc_candidates, fixture, parse, capture
except ImportError:
    from opponent_forward_audit import candidates, matching_dc, dc_candidates, fixture, parse, capture

WINDOW_DAYS=98
MAX_FILES=500
MAX_FILE_BYTES=8_000_000
MAX_DECODED_BYTES=64_000_000
ARCHIVE_NAME=re.compile(r"[0-9]+-[0-9]+\.json\.gz\Z")


def inventory(root, now):
    if now.tzinfo is None:
        raise ValueError("NAIVE_INVENTORY_CLOCK")
    now=now.astimezone(timezone.utc)
    root=Path(root)
    found=defaultdict(list)
    native=defaultdict(set)
    fixture_ids=defaultdict(set)
    counts=Counter()
    days=set()
    decoded=0
    budget_hit=False
    for offset in range(WINDOW_DAYS):
        day=now.date()-timedelta(days=offset)
        folder=root/day.strftime("%Y/%m/%d")
        # A symlink at the year or month level must not escape the archive root.
        if any(p.is_symlink() for p in (root,folder.parent.parent,folder.parent,folder)):
            counts["symlink_archive_paths_rejected"]+=1
            continue
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json.gz"),reverse=True):
            if counts["files_examined"]>=MAX_FILES:
                budget_hit=True
                break
            counts["files_examined"]+=1
            try:
                if not ARCHIVE_NAME.fullmatch(path.name) or path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_FILE_BYTES:
                    raise ValueError("INVALID_ARCHIVE_FILE")
                with gzip.open(path,"rb") as f:
                    raw=f.read(min(MAX_FILE_BYTES,MAX_DECODED_BYTES-decoded)+1)
                if decoded+len(raw)>MAX_DECODED_BYTES:
                    budget_hit=True
                    break
                decoded+=len(raw)
                if len(raw)>MAX_FILE_BYTES:
                    raise ValueError("OVERSIZED_ARCHIVE")
                doc=parse(raw)
                rows=candidates(doc)
                if not rows:
                    counts["no_valid_opponent_capture"]+=1
                    continue
                dc=dc_candidates(doc)
                staged=[]
                for row in rows:
                    key=fixture(row["league"],row["home"],row["away"],row["kickoff_utc"])
                    stamp=capture.utc(row["candidate_prediction_utc"])
                    if stamp>now or abs((stamp.date()-day).days)>1:
                        counts["clock_or_archive_day_rejected"]+=1
                        continue
                    staged.append((key,stamp,row,matching_dc(row,dc)))
                # Do not retain a partial archive if a later row raises.
                for key,stamp,row,match in staged:
                    native[(row["league"],row["event_id"])].add(key)
                    fixture_ids[key].add(row["event_id"])
                    found[key].append((stamp,row,match))
                    counts["candidate_observations"]+=1
                days.add(day.isoformat())
                counts["validated_capture_documents"]+=1
            except (OSError,EOFError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):
                counts["invalid_files"]+=1
        if budget_hit:
            break
    conflicts={key for keys in native.values() if len(keys)>1 for key in keys}
    conflicts.update(key for key,ids in fixture_ids.items() if len(ids)>1)
    leagues=defaultdict(Counter)
    weeks=set()
    elapsed_weeks=set()
    for key,entries in sorted(found.items()):
        league=leagues[key[0]]
        league["unique_fixtures"]+=1
        if key in conflicts:
            league["identity_conflicts"]+=1
            continue
        first=min(entry[0] for entry in entries)
        earliest=[entry for entry in entries if entry[0]==first]
        if any(entry[1:]!=earliest[0][1:] for entry in earliest):
            league["earliest_capture_conflicts"]+=1
            continue
        if earliest[0][2] is None:
            league["missing_same_source_dc"]+=1
            continue
        league["three_model_ready"]+=1
        iso=key[3].isocalendar()
        week=f"{iso.year}-W{iso.week:02}"
        weeks.add(week)
        if key[3]+timedelta(hours=2)<=now:
            league["recorded_kickoff_plus_two_hours_elapsed"]+=1
            elapsed_weeks.add(week)
    ready=sum(v["three_model_ready"] for v in leagues.values())
    return {"schema":"football-king-long-horizon-shadow-inventory-v1",
            "as_of_utc":now.isoformat(),"status":"HOLD",
            "window_days":WINDOW_DAYS,"file_limit":MAX_FILES,
            "decoded_byte_limit":MAX_DECODED_BYTES,"decoded_bytes":decoded,
            "budget_limit_reached":budget_hit,"archive_history_complete":False,
            "archive_days_with_valid_capture_documents":len(days),
            "earliest_archive_day":min(days,default=None),"latest_archive_day":max(days,default=None),
            "scan_counts":dict(counts),"unique_fixture_count":len(found),
            "three_model_ready":ready,"by_league":{k:dict(v) for k,v in sorted(leagues.items())},
            "recorded_kickoff_weeks":sorted(weeks),
            "elapsed_recorded_kickoff_weeks":sorted(elapsed_weeks),
            "coverage_is_not_settlement":True,"archive_authentication_verified":False,
            "authenticated_forward_samples":0,"independent_oos_verified":False,
            "positive_ev_verified":False,"production_recommendations":"DISABLED"}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archives",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    result=inventory(a.archives,datetime.now(timezone.utc))
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("status","unique_fixture_count","three_model_ready","budget_limit_reached","production_recommendations")}))


if __name__=="__main__":
    main()
