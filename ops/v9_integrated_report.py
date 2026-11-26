"""V9 unified evidence index. Missing evidence fails closed."""
import argparse,hashlib,json
from pathlib import Path
from ops.v6_forward_bundle import decode
from ops.v19_evidence_index import EXTRA_FILES,index
FILES={"domestic":"v8-release.json","ucl_archive":"v8-ucl-gap-fill.json","ucl_alias":"v8-ucl-alias.json","ucl_calibration":"v8-ucl-calibration.json","ucl_confidence":"v8-ucl-confidence.json","ucl_adaptive":"v9-ucl-adaptive.json","ucl_current":"v8-ucl-current-intake.json"}
def build(root):
    reports={};hashes={}
    for k,name in {**FILES,**EXTRA_FILES}.items():
        p=Path(root)/name
        if not 0<p.stat().st_size<=3_000_000:raise ValueError("SIZE")
        raw=p.read_bytes();r=decode(raw)
        if r.get("production_recommendations")!="DISABLED" or r.get("status")!="HOLD":raise ValueError("UNSAFE_ARTIFACT")
        if r.get("verified_forward_sample_credit",0)!=0:raise ValueError("UNEXPECTED_CREDIT")
        reports[k]=r;hashes[name]=hashlib.sha256(raw).hexdigest()
    d=reports["domestic"];u=reports["ucl_archive"];a=reports["ucl_adaptive"];c=reports["ucl_confidence"];s=reports["ucl_current"]
    if u["historical_phase_matches"]!=1536 or a["assessment_n"]!=144 or c["assessment_n"]!=144 or s["current_fixture_forecasts"]!=0:raise ValueError("SCOPE")
    extended=index(reports)
    return {"version":"19.0-research","v19_evidence_index":extended,"status":"HOLD","production_recommendations":"DISABLED","automatic_promotion":False,
        "historical_counts":{"domestic":d["history_finished"],"ucl":u["historical_phase_matches"]},
        "domestic_same_fixture":d["same_fixture_full_ensemble_comparison"],
        "ucl_same_fixture":a["assessment"],"ucl_confidence_rule":c["chosen_rule"],"ucl_confidence_assessment":c["assessment_selected"],
        "ucl_current_source_diagnostics":s["providers"],"native_research_forecasts":d["native_forecasts"],"qualified_ucl_forecasts":0,
        "verified_forward_sample_credit":0,"quality":d["quality"],"artifact_sha256":hashes,
        "targets":{"historical_30000":extended["historical_archive"]["raw_archive_target_30000"],"independent_assessment_5000":False,"validated_accuracy_60":False,"validated_high_confidence_70":False,"authenticated_forward_300":False},
        "note":"Same-run local hashes only, not external authentication. V9 does not deploy or select a production model."}
def main():
    p=argparse.ArgumentParser();p.add_argument("--input-dir",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    out=build(a.input_dir)
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
