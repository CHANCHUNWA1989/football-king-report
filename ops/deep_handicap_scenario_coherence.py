"""Correlated DHE scenario consistency audit; not an ensemble forecast.

Three pace scenarios share the same input rates and model family. Their
agreement is not independent evidence; their range is not a confidence interval.
"""
import math
from collections import defaultdict
from asian_handicap_research import TYPES, quarter_units
from deep_handicap_joint_score import score_distribution, _project_score, _total_units, PACE

SCHEMA="football-king-dhe-scenario-coherence-v1"
TOL=1e-9
AH_LINES=tuple(range(-6,-21,-1))
TOTAL_LINES=tuple(range(41))


def _require(ok,reason):
    if not ok:
        raise ValueError(reason)


def _distribution(score):
    _require(type(score) is dict and bool(score),"BAD_SCORE_MATRIX")
    for k,p in score.items():
        _require(type(k) is tuple and len(k)==2 and
                 all(type(n) is int and 0<=n<=48 for n in k) and
                 type(p) in (int,float) and math.isfinite(p) and 0<=p<=1,
                 "BAD_SCORE_CELL")
    _require(abs(math.fsum(score.values())-1)<=TOL,"BAD_SCORE_MASS")


def _grade(m,units):
    """Independent integer-quarter settlement oracle, no shared grader."""
    legs=(units,) if units%2==0 else (units-1,units+1)
    signed=sum((4*m+l>0)-(4*m+l<0) for l in legs)/len(legs)
    return {1:"FULL_WIN",.5:"HALF_WIN",0:"PUSH",-.5:"HALF_LOSS",-1:"FULL_LOSS"}[signed]


def _oracle(hist,units,reverse=False):
    out=dict.fromkeys(TYPES,0.0)
    for m,p in hist.items():
        out[_grade(-m if reverse else m,units)]+=p
    return out


def _same(a,b):
    return set(a)==set(b) and all(abs(a[k]-b[k])<=TOL for k in a)


def audit_projection(score,side,ah,tu,pace):
    """Check exact-score matrix and market projections using independent oracle."""
    _distribution(score)
    margin,total=defaultdict(float),defaultdict(float)
    for (h,a),p in score.items():
        margin[h-a if side=="HOME" else a-h]+=p
        total[h+a]+=p
    report=_project_score(score,side,ah,tu,pace)
    fav=report["one_x_two"][side]
    _require(abs(fav-math.fsum(p for m,p in margin.items() if m>0))<=TOL,
             "MATCH_WIN_MISMATCH")
    for name,expected in (("handicap",_oracle(margin,ah)),("over",_oracle(total,-tu)),
                          ("under",_oracle(total,tu,True))):
        _require(_same(report[name],expected),"SETTLEMENT_ORACLE_MISMATCH")
    for values in (report["one_x_two"],report["handicap"],report["over"],report["under"]):
        _require(abs(math.fsum(values.values())-1)<=TOL,"MARKET_MASS_MISMATCH")
    for units,hist in ((AH_LINES,margin),(TOTAL_LINES,total)):
        previous=1.0
        for line in units:
            d=_oracle(hist,line if hist is margin else -line)
            p=d["FULL_WIN"]
            _require(p<=previous+TOL,"LINE_LADDER_NONMONOTONE")
            if hist is margin:
                _require(p+d["HALF_WIN"]<=fav+TOL,"COVER_EXCEEDS_MATCH_WIN")
            previous=p
    # Direct joint-cell oracle, not a product of marginal probabilities.
    joint={g:dict.fromkeys(TYPES,0.0) for g in TYPES}
    for (h,a),p in score.items():
        m=h-a if side=="HOME" else a-h
        joint[_grade(m,ah)][_grade(h+a,-tu)]+=p
    _require(all(_same(joint[g],report["handicap_and_over_joint"][g]) for g in TYPES),
             "JOINT_ORACLE_MISMATCH")
    _require(abs(math.fsum(r["probability"] for r in report["top_scores"])
                 +report["other_score_probability"]-1)<=TOL,"TOP_SCORE_MASS_MISMATCH")
    return report


def analyze(home,away,side,handicap,total_line):
    out={"schema":SCHEMA,"status":"HOLD","production_recommendations":"DISABLED",
         "research_only":True,"qualifies_for_betting":False,"calibrated":False,
         "positive_expected_value_verified":False,"true_forward_sample_count":0,
         "independent_model_evidence_count":0,"independent_model_agreement_verified":False,
         "confidence_interval_available":False,"combined_forecast":None,
         "scenario_diagnostics":None}
    try:
        ah,tu=quarter_units(handicap),_total_units(total_line)
        _require(ah<=-6 and side in ("HOME","AWAY"),"INVALID_MARKET")
        scenarios=[]
        previous=None
        for pace in PACE:
            score=score_distribution(home,away,side,pace)
            report=audit_projection(score,side,ah,tu,pace)
            p=report["handicap"]["FULL_WIN"]
            if previous is not None:
                _require(p+TOL>=previous,"PACE_DIRECTION_MISMATCH")
            previous=p
            scenarios.append((pace,score,report))
        reference=scenarios[-1][1]
        details=[]
        for pace,score,report in scenarios:
            tv=.5*math.fsum(abs(score.get(k,0)-reference.get(k,0))
                             for k in set(score)|set(reference))
            details.append({"pace":pace,"score_total_variation_vs_baseline":tv,
                            "full_win_probability":report["handicap"]["FULL_WIN"],
                            "match_win_probability":report["one_x_two"][side]})
        vals=[d["full_win_probability"] for d in details]
        out.update(reason="CORRELATED_SCENARIO_DIAGNOSTICS_ONLY",
                   scenario_count=len(details),scenario_diagnostics=details,
                   full_win_sensitivity_range={"min":min(vals),"max":max(vals)},
                   line_ladder_count_per_scenario=len(AH_LINES)+len(TOTAL_LINES),
                   shared_model_family_count=1,range_is_not_confidence_interval=True)
    except (ValueError,TypeError,KeyError,OverflowError,AttributeError) as exc:
        out["reason"]="SCENARIO_OR_COHERENCE_GATE_REJECTED"
    return out
