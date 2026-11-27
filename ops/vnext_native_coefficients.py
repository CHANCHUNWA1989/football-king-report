"""Retrospective coefficient challenger; no production fitting or promotion.
One league and the earliest 45-59 minute cut per fixture, fixed grid and
chronological split. Source timestamps and final outcomes remain unattested.
"""
import json
import math
from inplay_state_challenger_vnext import _clock, remaining_matrix
from live_snapshot_adapter import hold
from score_distribution_vnext import one_x_two
from vnext_native_postmatch import postmatch
from vnext_native_cohort import CASE_KEYS, MAX_FIXTURES

GRID = tuple((s,r) for s in (0.0,.075,.10) for r in (0.0,.20,.25))
REFERENCE = (.075,.20)
CLASSES = ("HOME","DRAW","AWAY")
MIN_TRAIN = 60
MIN_ASSESSMENT = 30

def _prob(row, params):
    s,r=params
    home,away=row["score"]
    rh,ra=row["red_cards"]
    gap=max(-4,min(4,home-away))
    change=-s*gap+r*(ra-rh)
    remain=(90-row["minute"])/90
    h,a=row["rates"]
    return one_x_two(remaining_matrix(h*remain*math.exp(change),
                                     a*remain*math.exp(-change),home,away))

def _metrics(rows, params):
    losses=[]; briers=[]; correct=0
    for row in rows:
        p=_prob(row,params)
        y=row["outcome"]
        losses.append(-math.log(max(1e-15,p[y])))
        briers.append(math.fsum((p[k]-int(k==y))**2 for k in CLASSES))
        best=max(p.values())
        # Do not arbitrarily credit a tied maximum.
        correct+=int(p[y]==best and sum(v==best for v in p.values())==1)
    n=len(rows)
    return {"n":n,"log_loss":math.fsum(losses)/n,"brier":math.fsum(briers)/n,
            "unique_top_correct":correct,"accuracy":correct/n}

def _select(train):
    # Deterministic fixed-grid selection, penalize moving from the reference.
    # Assessment data is not an argument.
    def objective(pair):
        penalty=(pair[0]-REFERENCE[0])**2+(pair[1]-REFERENCE[1])**2
        return (_metrics(train,pair)["log_loss"]+.1*penalty,penalty,pair)
    return min(GRID,key=objective)

def _coverage(rows, n, affected):
    return (len(rows)>=n and {r["outcome"] for r in rows}==set(CLASSES)
            and sum(r["red_cards"][0]!=r["red_cards"][1] for r in rows)>=affected
            and sum(r["score"][0]!=r["score"][1] for r in rows)>=affected)

def evaluate_coefficients(cases, *, split_utc, as_of_utc):
    """Replay before fitting; pre-split labels must be available before split.
    No independent clock or data authentication; never a certified holdout.
    """
    try:
        split,as_of=_clock(split_utc),_clock(as_of_utc)
        if split>=as_of or type(cases) is not list or not 1<=len(cases)<=MAX_FIXTURES:
            return hold("INVALID_CALIBRATION_COHORT")
        if any(type(c) is not dict or set(c)!=CASE_KEYS
               or type(c["fixture_id"]) is not str for c in cases):
            return hold("INVALID_CALIBRATION_CASE")
        ids=[c["fixture_id"] for c in cases]
        if len(set(ids))!=len(ids):
            return hold("DUPLICATE_CALIBRATION_FIXTURE")
        train=[];assessment=[];leagues=set();excluded=0
        for c in cases:
            report=postmatch(**c,as_of_utc=as_of_utc)
            if report.get("postmatch_status")!="STRUCTURAL_RESEARCH_ONLY":
                return hold("CALIBRATION_CASE_REJECTED")
            leagues.add(json.loads(c["raw"])["league"])
            if len(leagues)!=1:
                return hold("MIXED_LEAGUE_CALIBRATION")
            kickoff=_clock(c["kickoff_utc"])
            receipt=max(_clock(r["received_utc"]) for r in c["results"])
            if kickoff<split and receipt>=split:
                return hold("TRAINING_LABEL_AFTER_SPLIT")
            picked=next(((row,src) for row,src in zip(report["cuts"],c["cuts"])
                         if 45<=row["minute"]<60),None)
            if picked is None:
                excluded+=1
                continue
            row,src=picked
            pre=src["envelope"]["model"]["prematch"]
            item={"score":row["score"],"red_cards":row["red_cards"],
                  "minute":row["minute"],"outcome":row["actual_1x2"],
                  "rates":(pre["expected_home_goals"],pre["expected_away_goals"])}
            (train if kickoff<split else assessment).append(item)
        base={**hold("UNAUTHENTICATED_COEFFICIENT_RESEARCH"),
              "league":next(iter(leagues)),"split_utc":split.isoformat(),
              "minute_band":[45,60],"train_n":len(train),"assessment_n":len(assessment),
              "excluded_no_band":excluded,"verified_forward_sample_credit":0,
              "weight_updates_applied":False,"statistical_promotion_gate":False,
              "candidate_parameters":None,"assessment_metrics":None}
        if not _coverage(train,MIN_TRAIN,10) or not _coverage(assessment,MIN_ASSESSMENT,5):
            return {**base,"reason":"INSUFFICIENT_RESEARCH_COVERAGE"}
        candidate=_select(train)
        return {**base,"calibration_status":"RETROSPECTIVE_RESEARCH_ONLY",
                "candidate_parameters":{"score":candidate[0],"red":candidate[1]},
                "reference_parameters":{"score":REFERENCE[0],"red":REFERENCE[1]},
                "training_metrics":{"candidate":_metrics(train,candidate),
                                    "reference":_metrics(train,REFERENCE)},
                "assessment_metrics":{"candidate":_metrics(assessment,candidate),
                                      "reference":_metrics(assessment,REFERENCE)}}
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return hold("INVALID_CALIBRATION_COHORT")
