"""V56 private research report: recompute, bind and abstain. No live claims."""
from datetime import datetime
from itertools import product
from pathlib import Path
import hashlib
import math
from .research_unified_prematch_replay_v35 import verify, digest, canonical
from .research_market_provenance_v1 import Quote
from .research_evidence_bound_pricing_v1 import evidence_bound_pricing

def report(record, *, root="."):
    """Exact finite stress grid, not fitted uncertainty or verified EV."""
    out={"schema":"strict-analysis-receipt-v56","status":"HOLD",
         "production_recommendations":"DISABLED","private_only":True,
         "public_output_allowed":False,"verified_executable_ev":False,
         "source_identity_authenticated":False,"external_timestamp_verified":False,
         "training_admission":False,"qualified_for_production":False,
         "calibrated":False,"research_completed":False}
    try:
        if not verify(record,root=root)["replay_verified"]:
            raise ValueError("V35 replay failed")
        parse=datetime.fromisoformat
        quotes=[Quote(**dict(q,observed_at=parse(q["observed_at"]),
                            kickoff_at=parse(q["kickoff_at"]))) for q in record["quotes"]]
        delta=record["delta"]
        rows=[]
        for f in record["forecasts"]:
            for dh,da,rho in product((-delta,0,delta),(-delta,0,delta),(None,-0.1)):
                h,a=f["home"]+dh,f["away"]+da
                p=evidence_bound_pricing(event_id=record["event_id"],
                    home_xg=h,away_xg=a,quotes=quotes,now=parse(record["frozen_at"]),
                    handicap_line=record["handicap_line"],totals_line=record["totals_line"],
                    dc_rho=rho)
                if p["quote_manifest_sha256"]!=record["audit"]["quote_manifest_sha256"]:
                    raise ValueError("quote manifest drift")
                rows.append({"model":f["model"],"upstream":f["upstream"],
                             "home_rate":h,"away_rate":a,"rho":rho,
                             "one_x_two":p["one_x_two"],
                             "scenario_returns":{k:v["expected_net_return"] for k,v in p["markets"].items()}})
        if len(rows)!=18*len(record["forecasts"]):
            raise ValueError("scenario count mismatch")
        def bounds(field):
            keys=sorted(rows[0][field])
            if any(sorted(r[field])!=keys for r in rows):
                raise ValueError("scenario keys mismatch")
            result={}
            for k in keys:
                values=[r[field][k] for r in rows]
                if not all(math.isfinite(v) for v in values):
                    raise ValueError("nonfinite scenario")
                result[k]={"min":min(values),"max":max(values)}
            return result
        source=Path(root).resolve()/"ops/research_strict_analysis_receipt_v56.py"
        if source.resolve()!=Path(__file__).resolve():
            raise ValueError("executing report source differs from root")
        out.update({"research_completed":True,"input_sha256":record["sha256"],
                    "event_id":record["event_id"],"frozen_at":record["frozen_at"],
                    "quote_manifest_sha256":record["audit"]["quote_manifest_sha256"],
                    "report_source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
                    "scenario_count":len(rows),"scenarios":rows,
                    "probability_bounds":bounds("one_x_two"),
                    "scenario_return_bounds":bounds("scenario_returns"),
                    "missing_evidence":["independent_source_authentication",
                    "external_timestamp_witness","fitted_calibration",
                    "independent_out_of_sample_advantage","live_executable_price"]})
        out["sha256"]=digest(out)
        return out
    except (ValueError,TypeError,KeyError,AttributeError,OSError,OverflowError,IndexError):
        return {"schema":"strict-analysis-receipt-v56","status":"HOLD",
                "production_recommendations":"DISABLED","private_only":True,
                "public_output_allowed":False,"verified_executable_ev":False,
                "source_identity_authenticated":False,"external_timestamp_verified":False,
                "training_admission":False,"qualified_for_production":False,
                "calibrated":False,"research_completed":False,
                "reason":"REPLAY_OR_SCENARIO_REJECTED"}

def recheck(receipt,record,*,root="."):
    """Canonical recomputation, not a signature or source authentication."""
    try:
        expected=report(record,root=root)
        return expected["research_completed"] is True and canonical(receipt)==canonical(expected)
    except (ValueError,TypeError,KeyError,OverflowError):
        return False
