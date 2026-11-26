"""V10 evidence rollup, hash receipts are local integrity only."""
import argparse,json,hashlib
from pathlib import Path
from ops.v6_forward_bundle import decode
FILES={"history":"v9-history-expansion.json","league":"v9-league-weights.json","ml":"v9-expanded-ml.json",
       "schedule":"v9-schedule-venue.json","market":"v9-market-research.json","ucl":"v9-ucl-adaptive.json",
       "confidence":"v8-ucl-confidence.json","fusion":"v10-fusion.json","release":"v9-release.json"}
def build(root):
    r={};hashes={}
    for k,name in FILES.items():
        f=Path(root)/name
        if not 0<f.stat().st_size<=3_000_000:raise ValueError("SIZE")
        raw=f.read_bytes();q=decode(raw)
        if q.get("status")!="HOLD" or q.get("production_recommendations")!="DISABLED" or q.get("verified_forward_sample_credit")!=0:raise ValueError("UNSAFE_ARTIFACT")
        r[k]=q;hashes[name]=hashlib.sha256(raw).hexdigest()
    h=r["history"];f=r["fusion"];m=r["ml"]
    if f["assessment_n"]!=m["all_finished_assessment"] or f["pooled"]["ml_available"]!=m["common_assessment_n"]:raise ValueError("COHORT")
    return {"version":"10.0-research","history_finished":h["combined_historical_finished"],"history_target_30000":h["combined_history_target_30000"],
        "domestic":f["pooled"],"league_weights":f["league_ml_weights"],"ucl":r["ucl"]["assessment"],
        "market_research":r["market"]["chronological"],"confidence_rule":r["confidence"]["chosen_rule"],
        "quality":r["release"]["quality"],"artifact_sha256":hashes,"verified_forward_sample_credit":0,
        "production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}
def main():
    p=argparse.ArgumentParser();p.add_argument("--input-dir",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    out=build(a.input_dir)
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
