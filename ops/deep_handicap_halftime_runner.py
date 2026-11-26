"""Bounded private historical compatibility runner.

Only compatibility counts and HOLD flags reach CI logs. No raw data or
research metrics are emitted. No data is written to disk.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from deep_handicap_historical_smoke import fetch, INDEX_LIMIT,GROUP_IDS
from deep_handicap_historical_inputs import _decode,MAX_BYTES
from deep_handicap_halftime_study import extract,evaluate


def run():
    summary={"status":"HOLD","production_recommendations":"DISABLED",
             "data_source":"StatsBomb Open Data","attempted":0,"structural_pass":0,
             "failed":0,"true_forward_sample_count":0,"research_metrics_published":False}
    try:
        index=_decode(fetch("data/matches/43/106.json",INDEX_LIMIT),INDEX_LIMIT)
        if type(index) is not list or len(index)!=64:
            raise ValueError("BAD_INDEX")
        group=sorted((m for m in index if m["competition_stage"]["name"]=="Group Stage"),
                     key=lambda m:(m["match_date"],m["match_id"]))
        if (len(group)!=48 or any(type(m["match_id"]) is not int for m in group)
                or {m["match_id"] for m in group}!=set(GROUP_IDS)):
            raise ValueError("BAD_GROUP_COHORT")
        summary["attempted"]=len(group)
        def one(m):
            try:
                raw=fetch(f"data/events/{m['match_id']}.json",MAX_BYTES,full_group=True)
                return extract(raw,m)
            except Exception:
                return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            rows=list(pool.map(one,group))
        passed=[r for r in rows if r is not None]
        summary["structural_pass"]=len(passed)
        summary["failed"]=len(rows)-len(passed)
        if len(passed)!=48:
            raise ValueError("INCOMPLETE_REAL_FILE_COHORT")
        report=evaluate(passed)
        if report["reason"]=="INVALID_HISTORICAL_COHORT":
            raise ValueError("COHORT_EVALUATION_REJECTED")
        summary["evaluation_logic_completed"]=True
        # Never emit observed leader counts, ratio, errors, or player/team data.
    except Exception as exc:
        summary["failure_type"]=type(exc).__name__
    print(json.dumps(summary),flush=True)
    return 0 if (summary.get("evaluation_logic_completed") is True and summary["attempted"]==48
                 and summary["structural_pass"]==48 and summary["failed"]==0
                 and "failure_type" not in summary) else 1


if __name__=="__main__":
    sys.exit(run())
