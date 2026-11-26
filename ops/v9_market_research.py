"""V9.2 paired market probability research; no executable odds or EV."""
import argparse,json,hashlib
from collections import Counter
from datetime import timedelta
from pathlib import Path
from ops.v6_forward_bundle import decode
from ops.v5_ucl_source_gate import utc
from ops.v8_multiseason import git_blob
from ops.market_shrinkage import blend,score,validate_probs
PIN="8f926d2c1aa9739f89975bd561c18239cb0cf28c"
WEIGHTS=(0.,.25,.5,.75,1.)
MAX_AGE=timedelta(hours=24)
def load(raw):
    if not 0<len(raw)<=2_000_000 or git_blob(raw)!=PIN:raise ValueError("PINNED_EVIDENCE_MISMATCH")
    doc=decode(raw)
    if doc.get("schema")!="football-king-forward-research-1" or doc.get("production_recommendations")!="DISABLED":raise ValueError("SCOPE")
    rows=doc["samples"]
    if len(rows)!=128 or doc["n"]!=len(rows):raise ValueError("ROW_COUNT")
    return rows,utc(doc["checked_utc"])
def audit(rows,checked):
    counts=Counter(r["key"] for r in rows)
    out=[];rejected=Counter()
    for r in rows:
        try:
            if counts[r["key"]]!=1:raise ValueError("DUPLICATE")
            k=decode(r["key"].encode())
            if not isinstance(k,list) or len(k)!=4 or k[0]!=r["league"] or not all(isinstance(v,str) and v for v in k) or k[1]==k[2]:raise ValueError("IDENTITY")
            ko,f,m=map(utc,(r["kickoff_utc"],r["forecast_utc"],r["market_utc"]))
            if utc(k[3])!=ko:raise ValueError("IDENTITY")
            if not m<=f<ko<=checked:raise ValueError("CLOCK")
            if f-m>MAX_AGE:raise ValueError("RESEARCH_STALE")
            if r["production_recommendations"]!="DISABLED" or r["fixture_result_source_independently_verified"] is not False:raise ValueError("SCOPE")
            validate_probs(r["p"]);validate_probs(r["m"])
            if type(r["y"]) is not int or r["y"] not in (0,1,2):raise ValueError("OUTCOME")
            out.append({**r,"kickoff":ko.isoformat()})
        except (ValueError,TypeError,KeyError,AttributeError) as ex:
            reason=str(ex)
            rejected[reason if reason in {"DUPLICATE","IDENTITY","CLOCK","RESEARCH_STALE","SCOPE","INVALID_PROBABILITIES","OUTCOME"} else "INVALID_ROW"]+=1
    return sorted(out,key=lambda r:(r["kickoff"],r["key"])),dict(rejected)
def choose(dev):
    if len(dev)<50:raise ValueError("INSUFFICIENT_DEVELOPMENT")
    # Conservative tie break toward pure market; score only earlier rows.
    return min(WEIGHTS,key=lambda w:(score(dev,w)["log_loss"],-w))
def evaluate(rows):
    days=sorted({r["kickoff"][:10] for r in rows})
    if len(days)<2:return {"reason":"INSUFFICIENT_DAYS","development_n":0,"assessment_n":0,"chosen_weight":None}
    split=days[max(1,min(len(days)-1,int(.7*len(days))))]
    dev=[r for r in rows if r["kickoff"][:10]<split]
    test=[r for r in rows if r["kickoff"][:10]>=split]
    w=choose(dev) if len(dev)>=50 else None
    comparisons={str(v):score(test,v) for v in WEIGHTS}
    candidate=score(test,w) if w is not None else None
    market=comparisons["1.0"]
    return {"cutoff_utc_day":split,"development_n":len(dev),"assessment_n":len(test),"chosen_weight":w,
        "assessment_market":market,"assessment_candidate":candidate,"assessment_fixed_grid_diagnostics":comparisons,
        "point_scores_both_better_than_market":bool(candidate and candidate["log_loss"]<market["log_loss"] and candidate["brier"]<market["brier"]),
        "assessment_weeks":len({utc(r["kickoff"]).strftime("%G-W%V") for r in test})}
def build(raw):
    source,checked=load(raw);rows,rejected=audit(source,checked)
    chronological=evaluate(rows)
    from ops.v9_market_calibration import evaluate as calibrate
    v14=calibrate(rows,chronological["cutoff_utc_day"]) if "cutoff_utc_day" in chronological else None
    return {"schema":"v9-2-market-paired-research-v1","source_blob":PIN,"source_sha256":hashlib.sha256(raw).hexdigest(),
        "raw_n":len(source),"eligible_research_n":len(rows),"rejected":rejected,
        "all_same_fixture_diagnostic":{str(w):score(rows,w) for w in WEIGHTS},"chronological":chronological,"v14_consensus_calibration":v14,
        "max_research_market_age_seconds":86400,"live_quote_freshness_checked":False,
        "outcomes_independently_verified":False,"assessment_previously_inspected":True,
        "market_is_consensus_not_executable_price":True,"verified_ev":False,"statistical_promotion_gate":False,
        "verified_forward_sample_credit":0,"production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}
def main():
    p=argparse.ArgumentParser();p.add_argument("--input",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    f=Path(a.input)
    if not 0<f.stat().st_size<=2_000_000:raise ValueError("SIZE")
    out=build(f.read_bytes())
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
