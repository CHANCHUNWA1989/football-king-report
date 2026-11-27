"""V57 numerical cross-check, not independent model or real-world validation."""
import bisect
import hashlib
import math
import random
from pathlib import Path
from .research_multimodel_v1 import score_matrix,dixon_coles
from .research_strict_analysis_receipt_v56 import recheck
from .research_unified_prematch_replay_v35 import digest,canonical

DRAWS=4096
ALPHA=.001
METRICS=("home","draw","away","over_2_5","both_score")

def flags(i,j):
    return (i>j,i==j,i<j,i+j>=3,i>0 and j>0)

def crosscheck(receipt,record,*,root="."):
    """Compare sampling with exact matrix aggregation; no promotion."""
    out={"schema":"numerical-crosscheck-v57","status":"HOLD",
         "production_recommendations":"DISABLED","private_only":True,
         "qualified_for_production":False,"verified_executable_ev":False,
         "independent_model_validation":False,"calibrated":False,
         "training_admission":False,"public_output_allowed":False,
         "numerical_check_passed":False}
    try:
        if not recheck(receipt,record,root=root):
            raise ValueError("receipt mismatch")
        rows=receipt["scenarios"]
        if not 36<=len(rows)<=144:
            raise ValueError("invalid scenario count")
        epsilon=math.sqrt(math.log(2*len(rows)*len(METRICS)/ALPHA)/(2*DRAWS))
        diagnostics=[]
        for index,row in enumerate(rows):
            h,a,rho=row["home_rate"],row["away_rate"],row["rho"]
            m=score_matrix(h,a) if rho is None else dixon_coles(h,a,rho)
            cumulative=[]; cells=[]; exact=[0.]*len(METRICS); mass=0.
            for i,line in enumerate(m):
                for j,p in enumerate(line):
                    if not math.isfinite(p) or p<0:
                        raise ValueError("invalid mass")
                    f=flags(i,j)
                    for k,v in enumerate(f):
                        exact[k]+=p*v
                    mass+=p
                    cells.append(f)
                    cumulative.append(mass)
            if abs(mass-1)>1e-8:
                raise ValueError("normalization")
            if any(abs(exact[k]-row["one_x_two"][key])>1e-8
                   for k,key in enumerate(METRICS[:3])):
                raise ValueError("analytic result mismatch")
            seed=int(hashlib.sha256((receipt["sha256"]+":"+str(index)).encode()).hexdigest(),16)
            rng=random.Random(seed)
            counts=[0]*len(METRICS)
            for _ in range(DRAWS):
                pos=min(bisect.bisect_right(cumulative,rng.random()*mass),len(cells)-1)
                for k,v in enumerate(cells[pos]):
                    counts[k]+=v
            sampled=[v/DRAWS for v in counts]
            error=max(abs(a-b) for a,b in zip(exact,sampled))
            diagnostics.append({"index":index,"exact":dict(zip(METRICS,exact)),
                "sampled":dict(zip(METRICS,sampled)),"max_error":error})
        source=Path(root).resolve()/"ops/research_numerical_crosscheck_v57.py"
        if source.resolve()!=Path(__file__).resolve():
            raise ValueError("source root mismatch")
        out.update({"receipt_sha256":receipt["sha256"],
            "source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
            "draws_per_scenario":DRAWS,"scenario_count":len(rows),
            "total_draws":DRAWS*len(rows),"familywise_alpha_reference":ALPHA,
            "sampling_tolerance":epsilon,"diagnostics":diagnostics,
            "numerical_check_passed":all(r["max_error"]<=epsilon for r in diagnostics)})
        out["sha256"]=digest(out)
    except (ValueError,TypeError,KeyError,AttributeError,OSError,OverflowError,IndexError):
        out["reason"]="INPUT_OR_NUMERICAL_CHECK_REJECTED"
    return out

def verify_crosscheck(result,receipt,record,*,root="."):
    try:
        expected=crosscheck(receipt,record,root=root)
        return expected["numerical_check_passed"] is True and canonical(result)==canonical(expected)
    except (ValueError,TypeError,KeyError,OverflowError):
        return False
