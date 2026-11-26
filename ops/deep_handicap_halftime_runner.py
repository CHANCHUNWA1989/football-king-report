"""Bounded private historical compatibility runner.

Only compatibility counts and HOLD flags reach CI logs. No raw data or
research metrics are emitted. No data is written to disk.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from deep_handicap_historical_smoke import fetch, INDEX_LIMIT,GROUP_IDS
from deep_handicap_historical_inputs import _decode,MAX_BYTES,_id
from deep_handicap_halftime_study import extract,evaluate
from deep_handicap_red_card_windows import inspect as red_windows,classify_window,reconcile_dispositions


def select_group(index):
    if type(index) is not list or len(index)!=64:
        raise ValueError("BAD_INDEX")
    ids=[_id(m["match_id"]) for m in index]
    if len(set(ids))!=64:
        raise ValueError("DUPLICATE_INDEX_ID")
    group=sorted((m for m in index if m["competition_stage"]["name"]=="Group Stage"),
                 key=lambda m:(m["match_date"],m["match_id"]))
    if len(group)!=48 or {m["match_id"] for m in group}!=set(GROUP_IDS):
        raise ValueError("BAD_GROUP_COHORT")
    return group

def run():
    summary={"status":"HOLD","production_recommendations":"DISABLED",
             "data_source":"StatsBomb Open Data","attempted":0,"structural_pass":0,
             "failed":0,"true_forward_sample_count":0,"research_metrics_published":False}
    try:
        index=_decode(fetch("data/matches/43/106.json",INDEX_LIMIT),INDEX_LIMIT)
        group=select_group(index)
        summary["attempted"]=len(group)
        def one(m):
            try:
                raw=fetch(f"data/events/{m['match_id']}.json",MAX_BYTES,full_group=True)
                row=extract(raw,m)
                try:
                    red=red_windows(raw,m)
                    reason=classify_window(red)
                except (ValueError,TypeError,KeyError,OverflowError,AttributeError):
                    reason="STRUCTURE_REJECTED"
                return row,reason
            except Exception:
                return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            rows=list(pool.map(one,group))
        passed=[r[0] for r in rows if r is not None]
        counts=reconcile_dispositions([r[1] for r in rows if r is not None],len(passed))
        summary['red_card_clock_review_attempted']=len(passed)
        summary['red_card_clock_review_rejected']=counts["STRUCTURE_REJECTED"]
        summary['red_card_clock_review_structural_pass']=len(passed)-counts["STRUCTURE_REJECTED"]
        summary['red_card_disposition_partition_reconciled']=True
        summary['red_card_eligible_window_counts_published']=False
        summary['red_card_calibration_verified']=False
        summary["structural_pass"]=len(passed)
        summary["failed"]=len(rows)-len(passed)
        if len(passed)!=48:
            raise ValueError("INCOMPLETE_REAL_FILE_COHORT")
        report=evaluate(passed)
        if report["reason"] not in ("RETROSPECTIVE_DESCRIPTIVE_ONLY","INSUFFICIENT_HALFTIME_LEADER_SAMPLE"):
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
