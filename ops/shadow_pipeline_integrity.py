"""End-to-end fail-closed integrity gate for the daily research bundle."""
import argparse
import json
from pathlib import Path

def check(archives,coverage,gaps,probe,ambiguity,daily,readiness):
    errors=[]
    def require(ok,label):
        if not ok:errors.append(label)
    for name,part in (("coverage",coverage),("gaps",gaps),("probe",probe),("ambiguity",ambiguity),("readiness",readiness)):
        require(part.get("status")=="HOLD",name+"_NOT_HOLD")
        require(part.get("production_recommendations")=="DISABLED",name+"_PRODUCTION_ENABLED")
        require(part.get("independently_verified") is False,name+"_UNSAFE_VERIFICATION")
    require(daily.get("production_recommendations")=="DISABLED","DAILY_PRODUCTION_ENABLED")
    require(daily.get("status")=="SHADOW_ONLY","DAILY_NOT_SHADOW")
    require(isinstance(archives,list),"INVALID_ARCHIVES")
    archive_ids=[r.get("fixture_id") for r in archives if isinstance(r,dict)] if isinstance(archives,list) else []
    require(len(archive_ids)==len(set(archive_ids)),"DUPLICATE_ARCHIVE_IDS")
    require(all(isinstance(x,str) and x for x in archive_ids),"INVALID_ARCHIVE_IDS")
    queue=coverage.get("matured_unmatched_fixture_ids",[])
    gap_ids=[x.get("fixture_id") for x in gaps.get("fixtures",[])]
    require(isinstance(queue,list) and set(queue)==set(gap_ids) and len(queue)==len(gap_ids),"QUEUE_GAP_MISMATCH")
    require(set(queue).issubset(set(archive_ids)),"UNSEALED_QUEUE_FIXTURE")
    require(readiness.get("matured_awaiting_ft")==len(queue),"READINESS_QUEUE_MISMATCH")
    require(readiness.get("valid_scored_fixtures")==daily.get("valid_fixtures"),"READINESS_SCORE_MISMATCH")
    models=daily.get("models",{})
    require(all(models.get(k,{}).get("sample_size")==daily.get("valid_fixtures") for k in ("original","market","market_50","market_75")),"FOUR_MODEL_SAMPLE_MISMATCH")
    require(ambiguity.get("fixture_count")==len(ambiguity.get("fixtures",[])),"AMBIGUITY_COUNT_MISMATCH")
    require(all(x.get("eligible_for_model_scoring") is False for x in ambiguity.get("fixtures",[])),"AMBIGUITY_LEAK")
    require(all(x.get("eligible_for_model_scoring") is False for x in gaps.get("fixtures",[])),"GAP_LEAK")
    return {"schema":"football-king-shadow-pipeline-integrity-v1","status":"PASS" if not errors else "FAIL",
            "production_recommendations":"DISABLED","verified_fixtures":daily.get("valid_fixtures"),
            "sealed_archive_count":len(archive_ids),"matured_queue_count":len(queue),
            "errors":errors}

def main():
    p=argparse.ArgumentParser()
    for key in ("archives","coverage","gaps","probe","ambiguity","daily","readiness","output"):
        p.add_argument("--"+key,required=True)
    a=p.parse_args()
    parts=[json.loads(Path(getattr(a,k)).read_text(encoding="utf-8")) for k in ("archives","coverage","gaps","probe","ambiguity","daily","readiness")]
    result=check(*parts)
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("PIPELINE INTEGRITY",result)
    if result["status"]!="PASS":raise SystemExit(1)

if __name__=="__main__":main()
