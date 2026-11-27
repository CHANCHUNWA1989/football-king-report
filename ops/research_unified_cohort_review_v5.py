"""Matched prematch/live/final research review; no source authentication or promotion.

Use the same replayed fixture across all models. Existing calibration fits only
on earlier results; this wrapper does not fit red-card or xG parameters.
"""
from .research_prematch_live_bridge_v4 import link, safety
from .research_snapshot_replay_v3 import _decode
from .research_live_pipeline_v10 import capture, replay
from .research_live_evidence_v3 import settle
from .research_live_calibration_v8 import calibrate
from .research_unified_live_v2 import utc, digest
from .research_multimodel_v1 import multiclass_brier, log_loss

KEYS=("home","draw","away")
MAX_CASES=1000

def _metrics(rows):
    if not rows:
        return {"n":0,"models":None}
    out={}
    for label in ("prematch","clock_baseline","dynamic"):
        out[label]={"brier":sum(multiclass_brier(r[label],r["outcome"]) for r in rows)/len(rows),
                    "log_loss":sum(log_loss(r[label],r["outcome"]) for r in rows)/len(rows)}
    return {"n":len(rows),"models":out,
            "dynamic_minus_clock":{k:out["dynamic"][k]-out["clock_baseline"][k] for k in ("brier","log_loss")}}

def review(cases,*,model_release,train_start,train_cutoff,test_end,as_of):
    """One fixed 20–30 minute forecast per fixture, same results for all models.
    All locally supplied clocks/labels remain untrusted. Invalid cohort fails closed.
    No partial metrics, market returns, or performance certification.
    """
    out={**safety(),"schema":"unified-cohort-review-v5","cohort_completeness_proven":False,
         "weights_fitted":False,"test_used_for_weight_selection":False}
    try:
        start,cut,end,now=map(utc,(train_start,train_cutoff,test_end,as_of))
        if not start<cut<end<=now or not isinstance(cases,list) or not 1<=len(cases)<=MAX_CASES:
            raise ValueError("invalid cohort")
        pairs=[]; testing=[]; seen=set(); receipts=[]
        for case in cases:
            if set(case)!={"link_inputs","final_observations","settled_at"}:
                raise ValueError("unexpected case fields")
            args=case["link_inputs"]
            if args["model_release"]!=model_release:
                raise ValueError("mixed release")
            linked=link(**args)
            if not linked.get("structural_link_passed"):
                raise ValueError("bridge rejected")
            event=linked["fixture_id"]
            t=utc(args["as_of"])
            settled=utc(case["settled_at"])
            if event in seen or not start<=t<end or not t<settled<=now or not 20<=linked["minute"]<30:
                raise ValueError("duplicate fixture or invalid cohort clock/band")
            seen.add(event)
            live=capture(args["live_raw_captures"],args["policy"],event_id=event,
                         as_of=args["as_of"],model_release=model_release,probability_only=True,source_bound=True)
            if live["sha256"]!=linked["live_receipt_sha256"]:
                raise ValueError("live receipt changed")
            bundle=replay(live,args["live_raw_captures"],args["policy"])
            result=settle(bundle,case["final_observations"],as_of=case["settled_at"])
            pairs.append((bundle,result))
            receipts.append((linked["link_sha256"],result["sha256"]))
            if t>=cut:
                pre=args["prematch_receipt"]["result"]["scenario"]["one_x_two"]
                testing.append({"prematch":{k:pre[k]["scenario_probability"] for k in KEYS},
                                "clock_baseline":{k:linked["baseline"][k] for k in KEYS},
                                "dynamic":{k:linked["dynamic"][k] for k in KEYS},
                                "outcome":result["outcome"],"red":sum(linked["red_cards"])>0,
                                "trailing":linked["trailing_side"]})
        cal=calibrate(pairs,model_release=model_release,train_start=train_start,
                      train_cutoff=train_cutoff,test_end=test_end,as_of=as_of)
        if cal["test_n"]!=len(testing):
            raise ValueError("test cohort mismatch")
        # Do not expose training fixture IDs in a summary.
        if "frozen_policy" in cal:
            cal["frozen_policy"]={k:v for k,v in cal["frozen_policy"].items() if k!="training_event_ids"}
            cal["frozen_policy"]["training_event_ids_redacted"]=True
        trailing=[r for r in testing if r["trailing"]]
        comeback=None
        if trailing:
            comeback={"n":len(trailing),
                      "brier":sum((r["dynamic"][r["trailing"]]-float(r["outcome"]==r["trailing"]))**2
                                  for r in trailing)/len(trailing)}
        return {**out,"structural_review_passed":True,"candidate_pairs":len(pairs),
                "train_n":cal["train_n"],"test_n":cal["test_n"],
                "weights_fitted":cal["weights_fitted"],"calibration_research":cal,
                "test_diagnostics":{"all":_metrics(testing),"red_card":_metrics([r for r in testing if r["red"]]),
                                    "no_red_card":_metrics([r for r in testing if not r["red"]]),
                                    "comeback":comeback},
                "cohort_sha256":digest({"receipts":sorted(receipts),"release":model_release,
                                        "train_start":start.isoformat(),"train_cutoff":cut.isoformat(),
                                        "test_end":end.isoformat(),"as_of":now.isoformat()}),
                "descriptive_only":True,"market_comparison_performed":False}
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return {**out,"structural_review_passed":False,"candidate_pairs":0,
                "reason":"INVALID_OR_INCOMPLETE_LINKED_COHORT"}
