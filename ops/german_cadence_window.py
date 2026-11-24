"""Consecutive scheduled-run and archived-publication evidence, read-only."""
import argparse
import gzip
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path
from ops.german_publication_monitor import inspect, json_read, LEAGUES, LIMIT, WORKFLOW
from ops.german_schedule_gap import stamp
from ops.history_blob_retention_preflight import _git, RetentionHold

REPO_ID=1411226578
MIN_RUNS=6
MAX_GAP=7200
MAX_AGE=7200


def evaluate(repo, main_sha, rows, now):
    if not isinstance(rows,list) or not 1 <= len(rows) <= 100:
        raise ValueError("INVALID_RUN_INVENTORY")
    ids=set()
    for r in rows:
        if (r["repository"]["id"] != REPO_ID or r["head_repository"]["id"] != REPO_ID
                or r["path"] != WORKFLOW or r["head_branch"] != "main"
                or r["event"] != "schedule" or type(r["id"]) is not int or r["id"] <= 0
                or r["id"] in ids or type(r["run_attempt"]) is not int or r["run_attempt"] <= 0
                or stamp(r["created_at"]) > now):
            raise ValueError("UNTRUSTED_OR_DUPLICATE_RUN")
        ids.add(r["id"])
    ordered=sorted(rows,key=lambda r:stamp(r["created_at"]),reverse=True)[:MIN_RUNS]
    gaps=[int((stamp(a["created_at"])-stamp(b["created_at"])).total_seconds())
          for a,b in zip(ordered,ordered[1:])]
    if any(g <= 0 for g in gaps):
        raise ValueError("NONINCREASING_SCHEDULE_CLOCK")
    latest=inspect(repo,main_sha,ordered[0],now)
    checked=[]
    for r in ordered:
        if r["status"] != "completed" or r["conclusion"] != "success" or r["run_attempt"] != 1:
            continue
        start,end=stamp(r["created_at"]),stamp(r["updated_at"])
        if not start <= end <= now or (end-start).total_seconds()>3600:
            continue
        # A run may cross an hour boundary; bounded set of possible published paths.
        for hour in sorted({start.strftime("%Y/%m/%d/%H-"),end.strftime("%Y/%m/%d/%H-")}):
            path="sources/live_germany/history/"+hour+str(r["id"])+".json.gz"
            try:
                packed=_git(repo,"show",main_sha+":"+path,limit=LIMIT)
            except RetentionHold:
                continue
            with gzip.GzipFile(fileobj=io.BytesIO(packed)) as f:
                raw=f.read(LIMIT+1)
            if len(raw)>LIMIT:
                raise ValueError("OVERSIZED_ARCHIVED_SNAPSHOT")
            doc=json_read(raw)
            t=stamp(doc["collected_utc"])
            coverage=doc["league_coverage"]
            if (doc.get("schema")=="football-king-openligadb-hourly-v1"
                    and doc.get("status")=="RESEARCH_ONLY"
                    and doc.get("production_recommendations")=="DISABLED"
                    and start <= t <= end and len(coverage)==3
                    and {v["league"] for v in coverage}==LEAGUES
                    and all(v.get("status")=="AVAILABLE" and v.get("production_recommendations")=="DISABLED" for v in coverage)):
                checked.append(dict(id=r["id"],archive_path=path,sha256=hashlib.sha256(raw).hexdigest()))
                break
    age=(now-stamp(ordered[0]["created_at"])).total_seconds()
    stable=(len(ordered)==MIN_RUNS and len(checked)==MIN_RUNS and max(gaps,default=MAX_GAP+1)<=MAX_GAP
            and age<=MAX_AGE and latest["status"]=="HOLD_FRESH_RESEARCH_PUBLICATION_CORRELATED")
    return dict(status="HOLD_CADENCE_EVIDENCE_WINDOW_PASSED" if stable else "HOLD_CADENCE_NOT_ESTABLISHED",
                observed_scheduled_runs=len(ordered),required_runs=MIN_RUNS,
                archived_publications_verified=len(checked),max_gap_seconds=max(gaps,default=None),
                schedule_gaps_seconds=gaps,latest_run_age_seconds=round(age),
                latest_publication_correlated=latest["publication_correlated"],
                research_cadence_window_passed=stable,scheduled_cadence_restored=False,
                archived_observations=checked,provider_failure_proven=False,
                fallback_allowed=False,production_recommendations="DISABLED")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo",type=Path,required=True)
    p.add_argument("--main-sha",required=True)
    p.add_argument("--observations",type=Path,required=True)
    a=p.parse_args()
    try:
        d=json_read(a.observations.read_bytes())
        print(json.dumps(evaluate(a.repo,a.main_sha,d["german_runs"],stamp(d["observed_utc"])),sort_keys=True))
    except (ValueError,OSError,KeyError,TypeError,AttributeError,EOFError):
        print(json.dumps(dict(status="HOLD_CADENCE_OBSERVATION_INVALID",production_recommendations="DISABLED")))
        return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
