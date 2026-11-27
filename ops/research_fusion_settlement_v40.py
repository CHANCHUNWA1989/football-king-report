"""Research-only V39 witness + regulation result candidate settlement.

Two local result envelopes do not prove publisher authenticity or independence.
No ledger write, certified OOS, model promotion or betting return.
"""
from datetime import timedelta
from .research_fusion_witness_v39 import verify
from .research_prospective_fusion_v38 import replay, canonical, sha, exact, token
from .research_candidate_gap_v6 import stamp
from .research_live_intake_v4 import decode
from .research_missing_fixture_discovery_v16 import identity
from .research_market_fusion_v37 import mix, CAP, normalized
from .research_multimodel_v1 import multiclass_brier, log_loss

KEYS=("home","draw","away")
MAX_KICKOFF_DRIFT=timedelta(minutes=15)
def settle_candidate(raw,receipt_bytes,bundle_bytes,result_bytes,*,source_sha,workflow_sha,run_id,attempt,as_of):
    out={"schema":"fusion-settlement-candidate-v40","status":"HOLD",
         "production_recommendations":"DISABLED","authenticated_samples":0,
         "actual_kickoff_authenticated":False,"source_authenticity_verified":False,
         "upstream_independence_proven":False,"independent_oos_proven":False,
         "training_admission":False,"model_promotion_allowed":False,"certified_ev":False}
    try:
        now=stamp(as_of)
        receipt=replay(decode(receipt_bytes),raw)
        if receipt["candidate"]["state"]!="RESEARCH_CANDIDATE":
            raise ValueError("abstained forecast")
        if not isinstance(result_bytes,list) or len(result_bytes)!=2:
            raise ValueError("two result envelopes required")
        key=identity(*receipt["fixture"])
        recorded=key[3]
        rows=[]
        for body in result_bytes:
            r=decode(body)
            exact(r,"schema event_id league home away kickoff_utc actual_kickoff_utc finished_utc observed_utc captured_utc publisher upstream provider_fixture_id status scope score")
            if r["schema"]!="fusion-final-result-v40" or r["event_id"]!=receipt["event_id"] or identity(r["league"],r["home"],r["away"],r["kickoff_utc"])!=key:
                raise ValueError("fixture mismatch")
            if r["status"]!="FT" or r["scope"]!="regulation":
                raise ValueError("not regulation final")
            publisher,upstream=(token(r[k]).casefold() for k in ("publisher","upstream"))
            token(r["provider_fixture_id"])
            actual,finished,observed,captured=map(stamp,(r["actual_kickoff_utc"],r["finished_utc"],r["observed_utc"],r["captured_utc"]))
            if abs(actual-recorded)>MAX_KICKOFF_DRIFT or not actual+timedelta(minutes=90)<=finished<=observed<=captured<=now:
                raise ValueError("invalid final chronology")
            s=r["score"]
            if not isinstance(s,list) or len(s)!=2 or any(type(x) is not int or not 0<=x<=30 for x in s):
                raise ValueError("invalid regulation score")
            rows.append((publisher,upstream,actual,finished,s,sha(body)))
        a,b=rows
        if a[0]==b[0] or a[1]==b[1] or a[2]!=b[2] or a[4]!=b[4] or abs(a[3]-b[3])>timedelta(minutes=5):
            raise ValueError("conflicting or duplicate result")
        # Never accept saved verification output: invoke V39 on original bytes.
        witness=verify(raw,receipt_bytes,bundle_bytes,source_sha=source_sha,workflow_sha=workflow_sha,
                       run_id=run_id,attempt=attempt,as_of=as_of)
        if (witness.get("verification_completed") is not True or
            witness.get("observed_before_recorded_kickoff") is not True or
            witness.get("receipt_sha256")!=sha(receipt_bytes) or witness.get("raw_input_sha256")!=sha(raw) or
            witness.get("bundle_sha256")!=sha(bundle_bytes)):
            raise ValueError("witness rejected")
        t=stamp(witness["verified_tlog_utc"])
        if not stamp(receipt["receipt_clock_utc"])<=t<=min(recorded,a[2])-timedelta(minutes=10):
            raise ValueError("witness too late for corroborated kickoff")
        h,g=a[4]
        y="home" if h>g else "draw" if h==g else "away"
        market,model=receipt["market_p"],receipt["model_p"]
        forecasts={"market":market,"expanded":model,"fixed_10pct":mix(model,market,CAP),
                   "adaptive_capped":receipt["candidate"]["p"]}
        scores={}
        for name,p in forecasts.items():
            p=dict(zip(KEYS,normalized(p)))
            scores[name]={"brier":multiclass_brier(p,y),"log_loss":log_loss(p,y)}
        result={**out,"structural_settlement_passed":True,"external_witness_verifier_passed":True,
                "result_corroboration":"DECLARED_DISTINCT_PUBLISHERS_ONLY",
                "fixture":receipt["fixture"],"event_id":receipt["event_id"],"final_score":[h,g],"outcome":y,
                "reported_actual_kickoff":a[2].isoformat(),"verified_tlog_utc":t.isoformat(),
                "receipt_sha256":sha(receipt_bytes),"result_sha256s":sorted([a[5],b[5]]),
                "bundle_sha256":sha(bundle_bytes),"raw_input_sha256":sha(raw),
                "single_case_descriptive_losses":scores,"market_same_cutoff_proven":False}
        result["settlement_sha256"]=sha(canonical(result))
        return result
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError,OSError,RecursionError):
        return {**out,"structural_settlement_passed":False,
                "reason":"INVALID_OR_UNVERIFIED_WITNESS_OR_RESULT"}
