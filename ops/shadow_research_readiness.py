"""Consolidated, fail-closed daily research readiness report."""
import argparse
import json
from pathlib import Path


def summarize(coverage, probe, correlations, daily):
    if any(x.get("production_recommendations") != "DISABLED" for x in (coverage,probe,correlations,daily)):
        raise ValueError("PRODUCTION_NOT_DISABLED")
    if coverage.get("status")!="HOLD" or probe.get("status")!="HOLD":
        raise ValueError("UNSAFE_RESEARCH_INPUT")
    if probe.get("independently_verified") is not False or probe.get("eligible_for_model_scoring") is not False:
        raise ValueError("UNSAFE_PROBE")
    target=1000
    verified=daily.get("valid_fixtures",0)
    if type(verified) is not int or verified<0:
        raise ValueError("INVALID_VERIFIED_COUNT")
    queue=coverage.get("matured_unmatched_fixtures",[])
    if not isinstance(queue,list) or len(queue)!=coverage.get("matured_unmatched_count"):
        raise ValueError("INVALID_QUEUE")
    overlap=set(probe.get("both_sources_name_overlap_fixture_ids",[]))
    items=[]
    for f in queue:
        fid=f["fixture_id"]
        items.append({"fixture_id":fid,"home":f["home"],"away":f["away"],
                      "kickoff_utc":f["kickoff_utc"],"both_webpages_contain_nearby_names":fid in overlap,
                      "verification":"AWAITING_INDEPENDENT_FT","model_scoring_eligible":False})
    return {"schema":"football-king-shadow-readiness-v1","status":"HOLD",
            "production_recommendations":"DISABLED","independently_verified":False,
            "valid_scored_fixtures":verified,"target":target,"remaining":max(0,target-verified),
            "source_agreements_unmatched_or_partial":coverage.get("source_agreements",0),
            "sealed_bundesliga_pairs":coverage.get("eligible_bundesliga_pairs",0),
            "matured_awaiting_ft":len(items),
            "webpage_name_overlap_not_scores":len(overlap),
            "source_stale_14d":coverage.get("source_stale_14d"),
            "blocking_reasons":(["NO_VERIFIED_PREDICTION_RESULT_PAIRS"] if verified==0 else [])
                                + (["MATURED_FIXTURES_AWAIT_FT"] if items else [])
                                + (["STRUCTURED_SOURCE_STALE"] if coverage.get("source_stale_14d") else []),
            "research_queue":items}


def main():
    parser=argparse.ArgumentParser()
    for arg in ("coverage","probe","correlations","daily","output"):
        parser.add_argument("--"+arg,required=True)
    a=parser.parse_args()
    inputs=[json.loads(Path(getattr(a,k)).read_text(encoding="utf-8")) for k in ("coverage","probe","correlations","daily")]
    report=summarize(*inputs)
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("READINESS",report["status"],"verified",report["valid_scored_fixtures"],"matured_awaiting_ft",report["matured_awaiting_ft"],"blockers",report["blocking_reasons"])

if __name__=="__main__":
    main()
