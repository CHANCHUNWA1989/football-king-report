"""V44: locally replayed, paired prematch model versus market diagnostics.

Market probabilities use proportional normalization of same-snapshot 1X2
prices. This is not independently authenticated market evidence or live EV.
Compare only decisions within the declared test window, not earlier priors
or in-play predictions against older prematch prices. Never promote.
"""
from collections import defaultdict
from random import Random
from .research_unified_cohort_v43 import run as review
from .research_snapshot_replay_v3 import _decode
from .research_live_pipeline_v10 import capture, replay
from .research_live_evidence_v3 import settle
from .research_unified_cutoff_v39 import utc
from .research_multimodel_v1 import multiclass_brier, log_loss
from .research_unified_prematch_replay_v35 import digest

KEYS=("home","draw","away")
METRICS=("brier","log_loss")
MIN_INTERVAL_N=100
MIN_INTERVAL_DAYS=20

def mean(rows):
    return {k:sum(r[k] for r in rows)/len(rows) for k in METRICS}

def compare(rows):
    if not rows:
        return {"n":0,"days":0,"model":None,"market":None,
                "model_minus_market":None,"descriptive_cluster_ci95":None}
    model=mean([r["model"] for r in rows])
    market=mean([r["market"] for r in rows])
    clusters=defaultdict(list)
    for r in rows:
        clusters[r["day"]].append({k:r["model"][k]-r["market"][k] for k in METRICS})
    groups=[clusters[k] for k in sorted(clusters)]
    intervals=None
    if len(rows)>=MIN_INTERVAL_N and len(groups)>=MIN_INTERVAL_DAYS:
        rng=Random(20261127)
        draws=[mean([r for _ in groups for r in rng.choice(groups)]) for _ in range(1000)]
        intervals={k:[sorted(d[k] for d in draws)[25],sorted(d[k] for d in draws)[974]]
                   for k in METRICS}
    return {"n":len(rows),"days":len(groups),"model":model,"market":market,
            "model_minus_market":{k:model[k]-market[k] for k in METRICS},
            "descriptive_cluster_ci95":intervals}

def losses(p,y):
    return {"brier":multiclass_brier(p,y),"log_loss":log_loss(p,y)}

def run(**kwargs):
    out={"schema":"unified-market-benchmark-v44","status":"HOLD",
         "production_recommendations":"DISABLED","structural_review_passed":False,
         "source_authenticity_verified":False,"external_timestamp_verified":False,
         "independent_oos_proven":False,"certified_ev":False,
         "model_promotion_allowed":False,"market_comparison_performed":False,
         "missing_release_evidence":["AUTHENTICATED_SOURCES","EXTERNAL_FORECAST_TIMESTAMPS",
            "INDEPENDENT_PROSPECTIVE_OOS","VALIDATED_CALIBRATION","EXECUTABLE_MARKET_QUOTES",
            "PRODUCTION_DEPLOYMENT_REVIEW"]}
    try:
        base=review(**kwargs)
        if (base.get("structural_review_passed") is not True
                or base.get("status")!="HOLD"
                or base.get("production_recommendations")!="DISABLED"
                or any(base.get(k) is not False for k in (
                    "source_authenticity_verified","external_timestamp_verified",
                    "independent_oos_proven","certified_ev","model_promotion_allowed"))):
            raise ValueError("cohort review rejected")
        cut,end=map(utc,(kwargs["train_cutoff"],kwargs["test_end"]))
        rows=[]; excluded=0; seen=set()
        for execution in kwargs["executions"]:
            for event,case in sorted(execution["live_cases"].items()):
                if event in seen:
                    raise ValueError("duplicate fixture")
                seen.add(event)
                args=case["inputs"]
                p=_decode(args["prematch_raw"])
                decision=utc(p["as_of"])
                if not cut<=decision<end:
                    excluded+=1
                    continue
                receipt=capture(args["live_raw_captures"],args["policy"],event_id=event,
                                as_of=args["as_of"],model_release=args["model_release"],
                                probability_only=True,source_bound=True)
                bundle=replay(receipt,args["live_raw_captures"],args["policy"])
                final=kwargs["finals"][event]
                settled=settle(bundle,final["final_observations"],as_of=final["settled_at"])
                y=settled["outcome"]
                scenario=args["prematch_receipt"]["result"]["scenario"]["one_x_two"]
                model={k:scenario[k]["scenario_probability"] for k in KEYS}
                odds=p["snapshots"][0]["odds"]
                inverse={k:1/odds[k] for k in KEYS}
                market={k:v/sum(inverse.values()) for k,v in inverse.items()}
                rows.append({"event":event,"day":utc(p["kickoff"]).date().isoformat(),
                             "model":losses(model,y),"market":losses(market,y),
                             "settlement_sha256":settled["sha256"]})
        if seen!=set(kwargs["expected_ids"]) or len(rows)+excluded!=len(seen):
            raise ValueError("benchmark coverage mismatch")
        rows.sort(key=lambda r:r["event"])
        metrics=compare(rows)
        result={**out,"structural_review_passed":True,"market_comparison_performed":bool(rows),
                "declared_count":len(seen),"excluded_prematch_outside_test_window":excluded,
                "benchmark_kind":"PREMATCH_PROPORTIONAL_DEVIG_ONLY",
                "interval_policy":{"minimum_fixtures":MIN_INTERVAL_N,"minimum_utc_days":MIN_INTERVAL_DAYS,
                                   "draws":1000,"seed":20261127,"descriptive_only":True},
                "benchmark":metrics,"v43_review_sha256":base["local_review_sha256"],
                "paired_rows_sha256":digest(rows)}
        result["local_review_sha256"]=digest(result)
        return result
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return {**out,"reason":"INVALID_OR_INCOMPLETE_MARKET_BENCHMARK"}
