"""Offline paired cross-fixture error diagnostics. No fitting or sample certification."""
import json
import math
from collections import Counter, defaultdict
from inplay_state_challenger_vnext import _clock
from live_snapshot_adapter import hold
from vnext_native_postmatch import postmatch, BANDS

MAX_FIXTURES = 300
MIN_REPORT_N = 20
CASE_KEYS = {"raw","archive_sha256","fixture_id","home_native_id","away_native_id",
             "kickoff_utc","cuts","results"}
METRICS = ("brier_1x2","brier_market","log_loss_1x2")

def _report(values, names):
    n=len(values)
    return {"fixture_count":n,"minimum_diagnostic_n":MIN_REPORT_N,
            "mean_paired_delta":({k:math.fsum(v[k] for v in values)/n for k in names}
                                 if n>=MIN_REPORT_N else None),
            "status":"DESCRIPTIVE_ONLY" if n>=MIN_REPORT_N else "INSUFFICIENT_RESEARCH_N"}

def evaluate_cohort(cases, *, as_of_utc):
    """One fixture per band; replay inputs rather than trusting pasted metrics.
    Counts are unauthenticated retrospective research, not a holdout.
    No pooling across time bands, leagues, or different market sides/lines.
    """
    try:
        _clock(as_of_utc)
        if type(cases) is not list or not 1<=len(cases)<=MAX_FIXTURES:
            return hold("INVALID_COHORT")
        if any(type(c) is not dict or set(c)!=CASE_KEYS
               or type(c["fixture_id"]) is not str for c in cases):
            return hold("INVALID_COHORT_CASE")
        ids=[c["fixture_id"] for c in cases]
        if len(set(ids))!=len(ids):
            return hold("DUPLICATE_COHORT_FIXTURE")
        groups=defaultdict(list)
        market_groups=defaultdict(list)
        league_counts=Counter()
        for c in cases:
            report=postmatch(**c,as_of_utc=as_of_utc)
            if report.get("postmatch_status")!="STRUCTURAL_RESEARCH_ONLY":
                return hold("COHORT_CASE_REJECTED")
            league=json.loads(c["raw"])["league"]
            league_counts[league]+=1
            # Re-select earliest cut independently from the full scored replay.
            for start,end in BANDS:
                row=next((r for r in report["cuts"] if start<=r["minute"]<end),None)
                if row is None:
                    continue
                delta=row["paired_delta_baseline_minus_challenger"]
                red="CARD_PRESENT" if any(row["red_cards"]) else "NO_CARD"
                groups[(league,start,end,red)].append(delta)
                market_groups[(league,start,end,red,row["market"],row["side"],row["line"])].append(delta)
        return {**hold("UNAUTHENTICATED_COHORT_RESEARCH"),
                "cohort_status":"STRUCTURAL_RESEARCH_ONLY",
                "fixture_count":len(ids),"league_counts":dict(sorted(league_counts.items())),
                "paired_1x2_groups":[{"league":l,"minute_band":[s,e],"red_card_state":r,
                    **_report(vals,("brier_1x2","log_loss_1x2"))}
                    for (l,s,e,r),vals in sorted(groups.items())],
                "paired_market_groups":[{"league":l,"minute_band":[s,e],"red_card_state":r,
                    "market":m,"side":side,"line":line,**_report(vals,("brier_market",))}
                    for (l,s,e,r,m,side,line),vals in sorted(market_groups.items())],
                "pooled_accuracy":None,"weight_updates_applied":False,
                "statistical_promotion_gate":False,"verified_forward_sample_credit":0,
                "confidence_intervals":None,"realized_roi":None,"model_edge":None}
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return hold("INVALID_COHORT")
