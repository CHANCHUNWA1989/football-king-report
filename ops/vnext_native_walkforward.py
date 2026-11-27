"""Retrospective walk-forward coefficient research, no live promotion."""
import json
import math
from inplay_state_challenger_vnext import _clock
from live_snapshot_adapter import hold
from vnext_native_postmatch import postmatch
from vnext_native_cohort import CASE_KEYS, MAX_FIXTURES
from vnext_native_coefficients import (_coverage, _select, _metrics, REFERENCE,
                                       MIN_TRAIN, MIN_ASSESSMENT)

def _walk(rows, boundaries):
    """Expanding training windows; disjoint assessment windows.
    Unavailable past labels are excluded until their claimed receipt time.
    """
    folds=[]
    for start,end in zip(boundaries,boundaries[1:]):
        train=[r for r in rows if r["kickoff"]<start and r["receipt"]<start]
        delayed=sum(r["kickoff"]<start<=r["receipt"] for r in rows)
        test=[r for r in rows if start<=r["kickoff"]<end]
        # Assessment outcome must be available by the declared end of this fold.
        if any(r["receipt"]>=end for r in test):
            return None,"ASSESSMENT_LABEL_AFTER_WINDOW"
        if not _coverage(train,MIN_TRAIN,10) or not _coverage(test,MIN_ASSESSMENT,5):
            return None,"INSUFFICIENT_FOLD_COVERAGE"
        params=_select(train)
        folds.append({"start_utc":start.isoformat(),"end_utc":end.isoformat(),
            "train_n":len(train),"delayed_train_labels_excluded":delayed,
            "assessment_n":len(test),"candidate_parameters":list(params),
            "candidate":_metrics(test,params),"reference":_metrics(test,REFERENCE)})
    return folds,None

def evaluate_walkforward(cases, *, boundaries_utc, as_of_utc):
    """Caller declares 2-4 consecutive assessment windows before evaluation.
    This does not establish that boundaries were actually chosen prospectively.
    """
    try:
        as_of=_clock(as_of_utc)
        if type(boundaries_utc) is not list or not 3<=len(boundaries_utc)<=5:
            return hold("INVALID_WALKFORWARD_BOUNDARIES")
        bounds=[_clock(t) for t in boundaries_utc]
        if any(a>=b for a,b in zip(bounds,bounds[1:])) or bounds[-1]>as_of:
            return hold("INVALID_WALKFORWARD_BOUNDARIES")
        if type(cases) is not list or not 1<=len(cases)<=MAX_FIXTURES:
            return hold("INVALID_WALKFORWARD_CASES")
        if any(type(c) is not dict or set(c)!=CASE_KEYS
               or type(c["fixture_id"]) is not str for c in cases):
            return hold("INVALID_WALKFORWARD_CASES")
        ids=[c["fixture_id"] for c in cases]
        if len(set(ids))!=len(ids):
            return hold("DUPLICATE_WALKFORWARD_FIXTURE")
        rows=[];leagues=set();excluded=0
        for c in cases:
            kickoff=_clock(c["kickoff_utc"])
            if kickoff>=bounds[-1]:
                return hold("FIXTURE_OUTSIDE_WALKFORWARD")
            report=postmatch(**c,as_of_utc=as_of_utc)
            if report.get("postmatch_status")!="STRUCTURAL_RESEARCH_ONLY":
                return hold("WALKFORWARD_CASE_REJECTED")
            leagues.add(json.loads(c["raw"])["league"])
            if len(leagues)!=1:
                return hold("MIXED_LEAGUE_WALKFORWARD")
            selected=next(((r,s) for r,s in zip(report["cuts"],c["cuts"])
                           if 45<=r["minute"]<60),None)
            if selected is None:
                excluded+=1;continue
            row,src=selected
            pre=src["envelope"]["model"]["prematch"]
            rows.append({"kickoff":kickoff,
                "receipt":max(_clock(r["received_utc"]) for r in c["results"]),
                "score":row["score"],"red_cards":row["red_cards"],
                "minute":row["minute"],"outcome":row["actual_1x2"],
                "rates":(pre["expected_home_goals"],pre["expected_away_goals"])})
        rows.sort(key=lambda r:(r["kickoff"],r["receipt"],r["outcome"],
                               r["score"],r["red_cards"],r["rates"],r["minute"]))
        folds,reason=_walk(rows,bounds)
        if reason:
            return {**hold(reason),"fixture_count":len(ids),"excluded_no_band":excluded,
                    "verified_forward_sample_credit":0,"weight_updates_applied":False}
        n=sum(f["assessment_n"] for f in folds)
        def pooled(name,metric):
            return math.fsum(f["assessment_n"]*f[name][metric] for f in folds)/n
        return {**hold("UNAUTHENTICATED_WALKFORWARD_RESEARCH"),
            "walkforward_status":"RETROSPECTIVE_RESEARCH_ONLY",
            "league":next(iter(leagues)),"fixture_count":len(ids),
            "assessment_unique_fixture_count":n,"excluded_no_band":excluded,
            "minute_band":[45,60],"folds":folds,
            "paired_logloss_delta":pooled("reference","log_loss")-pooled("candidate","log_loss"),
            "paired_brier_delta":pooled("reference","brier")-pooled("candidate","brier"),
            "boundaries_prospectively_attested":False,"confidence_intervals":None,
            "verified_forward_sample_credit":0,"weight_updates_applied":False,
            "statistical_promotion_gate":False,"model_edge":None}
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return hold("INVALID_WALKFORWARD_CASES")
