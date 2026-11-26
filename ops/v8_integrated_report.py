"""V8 integration report: actual artifact metrics and explicit unavailable features."""
import argparse,json
from pathlib import Path
from ops.v6_forward_bundle import decode
def build(root):
    names={"competition":"v8-same-fixture.json","history":"v8-history.json","ensemble":"ensemble.json","calibration":"league-calibration.json","recent":"recent-strength.json","forward":"forward-bundle.json","comparison":"forward-comparison.json","archive":"local-archive-audit.json","accuracy":"accuracy-target.json"}
    reports={}
    for k,name in names.items():
        p=Path(root)/name
        if not 0<p.stat().st_size<=3_000_000:raise ValueError("INPUT_SIZE")
        r=decode(p.read_bytes())
        if r.get("production_recommendations")!="DISABLED":raise ValueError("UNSAFE_ARTIFACT")
        reports[k]=r
    h=reports["history"];f=reports["forward"];c=reports["comparison"];a=reports["accuracy"]
    return {"version":"8.1-research","status":"HOLD","production_recommendations":"DISABLED",
        "history_finished":h["historical_finished"],"historical_rolling_metrics":h["rolling_all"],
        "historical_latest_season":h["latest_season_assessment"],"historical_fixed_threshold":h["latest_season_fixed_threshold_50"],
        "same_fixture_full_ensemble_comparison":reports["competition"]["pooled"],"v6_ensemble_reference":a["full_assessment"],"native_forecasts":f["predictions_count"],"native_coverage":f["coverage"],
        "sealed_comparison_count":len(c["rows"]),"verified_forward_sample_credit":0,
        "quality":{"verified_xg":False,"official_lineups_and_injuries":False,"executable_market_odds":False,
            "two_independent_sources":False,"independent_code_review":False,"production_deployed":False},
        "targets":{"history_10000":h["historical_finished"]>=10000,"latest_season_2000":h["latest_season_assessment"]["n"]>=2000,
            "validated_accuracy_60":False,"authenticated_forward_300":False},
        "note":"Historical research is not certified prospective evidence or model promotion."}
def main():
    p=argparse.ArgumentParser();p.add_argument("--input-dir",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    result=build(a.input_dir)
    with Path(a.output).open("x") as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(result,allow_nan=False))
if __name__=="__main__":main()
