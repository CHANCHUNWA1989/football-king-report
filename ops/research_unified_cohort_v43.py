"""V43: strict local cohort review on V42-executed fixtures.

This connects local replays to paired outcome scoring. It does not establish
external timestamps, authentic sources, complete real-world coverage, or OOS.
The two pricing paths share a score engine, so agreement is a regression check,
not independent model validation. No market or model promotion permission.
"""
from math import isfinite
from .research_unified_market_evidence_v42 import run as execute
from .research_unified_cohort_review_v5 import review
from .research_unified_pricing_v1 import unified_research_pricing
from .research_snapshot_replay_v3 import _decode
from .research_unified_batch_replay_v38 import valid_id
from .research_unified_prematch_replay_v35 import digest

MAX_CASES=256
KEYS=("home","draw","away")
TOL=1e-10

def probability_check(record, case):
    p=_decode(case["inputs"]["prematch_raw"])
    forecasts=[f for f in record["forecasts"] if f["model"]==case["model"]]
    if len(forecasts)!=1:
        raise ValueError("ambiguous model")
    f=forecasts[0]
    prices={(q["market"],q["selection"]):q["decimal_odds"]
            for q in p["snapshots"][0]["asian"]}
    result=unified_research_pricing(f["home"],f["away"],
        handicap_line=record["handicap_line"],totals_line=record["totals_line"],
        handicap_home_odds=prices["handicap","home"],handicap_away_odds=prices["handicap","away"],
        over_odds=prices["totals","over"],under_odds=prices["totals","under"])
    a=result["one_x_two"]
    b=case["inputs"]["prematch_receipt"]["result"]["scenario"]["one_x_two"]
    if set(a)!=set(KEYS) or set(b)!=set(KEYS):
        raise ValueError("incomplete probability")
    diffs=[]
    for k in KEYS:
        x,y=a[k],b[k]["scenario_probability"]
        if not all(type(v) in (float,int) and isfinite(v) and 0<=v<=1 for v in (x,y)):
            raise ValueError("invalid probability")
        diffs.append(abs(x-y))
    if max(diffs)>TOL or abs(sum(a.values())-1)>TOL:
        raise ValueError("probability disagreement")
    return max(diffs)

def run(*, expected_ids, executions, finals, model_release, train_start,
        train_cutoff,test_end,as_of):
    out={"schema":"unified-cohort-v43","status":"HOLD","production_recommendations":"DISABLED",
         "structural_review_passed":False,"source_authenticity_verified":False,
         "external_timestamp_verified":False,"cohort_completeness_proven":False,
         "independent_oos_proven":False,"certified_ev":False,"model_promotion_allowed":False,
         "cross_path_1x2_quote_equality_verified":False,
         "shared_engine_probability_consistency_verified":False}
    try:
        if (type(expected_ids) is not list or not 1<=len(expected_ids)<=MAX_CASES
                or any(not valid_id(e) for e in expected_ids)
                or len(set(expected_ids))!=len(expected_ids)
                or type(finals) is not dict or set(finals)!=set(expected_ids)
                or type(executions) is not list or not 1<=len(executions)<=MAX_CASES):
            raise ValueError("invalid declared cohort")
        seen=set(); cases=[]; receipts=[]; diffs=[]
        for args in executions:
            if type(args) is not dict or args.get("model_release")!=model_release:
                raise ValueError("mixed model release")
            result=execute(**args)
            if (result.get("execution_passed") is not True
                    or result.get("cross_path_asian_equality_verified") is not True
                    or result.get("production_recommendations")!="DISABLED"
                    or result.get("status")!="HOLD"):
                raise ValueError("V42 evidence rejected")
            records={r["event_id"]:r for r in args["records"]}
            links=args["live_cases"]
            if set(links)!=set(result["asian_evidence_sha256"]):
                raise ValueError("execution coverage mismatch")
            for event,case in sorted(links.items()):
                if event in seen or event not in finals:
                    raise ValueError("duplicate or unexpected fixture")
                final=finals[event]
                if type(final) is not dict or set(final)!={"final_observations","settled_at"}:
                    raise ValueError("invalid final record")
                seen.add(event)
                diffs.append(probability_check(records[event],case))
                cases.append({"link_inputs":case["inputs"],**final})
                receipts.append((event,result["local_execution_sha256"]))
        if seen!=set(expected_ids):
            raise ValueError("incomplete cohort")
        report=review(cases,model_release=model_release,train_start=train_start,
                      train_cutoff=train_cutoff,test_end=test_end,as_of=as_of)
        if (report.get("structural_review_passed") is not True
                or report.get("candidate_pairs")!=len(seen)
                or report.get("production_recommendations")!="DISABLED"
                or report.get("status")!="HOLD"
                or any(report.get(k) is not False for k in (
                    "source_authenticity_verified","independent_oos_proven",
                    "certified_ev","model_promotion_allowed","cohort_completeness_proven"))):
            raise ValueError("paired review rejected")
        result={**out,"structural_review_passed":True,
                "shared_engine_probability_consistency_verified":True,
                "declared_fixture_count":len(seen),"max_probability_difference":max(diffs),
                "cohort_review":report,"execution_receipts":sorted(receipts)}
        result["local_review_sha256"]=digest(result)
        return result
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return {**out,"reason":"INVALID_OR_INCOMPLETE_UNIFIED_COHORT"}
