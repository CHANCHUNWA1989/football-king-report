"""Per-fixture source availability matrix from real parsed records (never FT verification)."""
import argparse
import json
from datetime import date,datetime
from pathlib import Path
from team_identity import team_id

def matrix(coverage, bundle):
    if coverage.get("status")!="HOLD" or bundle.get("status")!="HOLD" or bundle.get("independently_verified") is not False:
        raise ValueError("UNSAFE_INPUT")
    providers={}
    for source in bundle.get("sources",[]):
        name=source.get("provider")
        if name in providers or name not in ("OpenLigaDB","OpenFootball"):
            raise ValueError("INVALID_PROVIDER")
        normalized=[]
        for row in source.get("records",[]):
            try:
                home=team_id("bundesliga",row["home"]);away=team_id("bundesliga",row["away"])
                day=date.fromisoformat(row.get("date") or row["kickoff_utc"][:10])
                score=row["score_ft"]
                if home and away and home!=away and isinstance(score,list) and len(score)==2 and all(type(x) is int and 0<=x<=30 for x in score):
                    normalized.append((home,away,day))
            except (KeyError,ValueError,TypeError,AttributeError):
                continue
        providers[name]=normalized
    rows=[]
    for fixture in coverage.get("matured_unmatched_fixtures",[]):
        home=team_id("bundesliga",fixture["home"]);away=team_id("bundesliga",fixture["away"])
        day=datetime.fromisoformat(fixture["kickoff_utc"].replace("Z","+00:00")).date()
        counts={provider:sum(h==home and a==away and abs((d-day).days)<=1 for h,a,d in records) for provider,records in providers.items()}
        label="BOTH_PRESENT_NEEDS_PROVENANCE_REVIEW" if len(providers)==2 and all(n==1 for n in counts.values()) else "MISSING_SOURCE_RECORDS" if any(n==0 for n in counts.values()) or len(providers)<2 else "AMBIGUOUS_SOURCE_RECORDS"
        rows.append({"fixture_id":fixture["fixture_id"],"home":fixture["home"],"away":fixture["away"],"kickoff_utc":fixture["kickoff_utc"],
                     "source_candidate_counts":counts,"reason":label,"independently_verified":False,"eligible_for_model_scoring":False})
    return {"schema":"football-king-shadow-source-gap-matrix-v1","status":"HOLD","independently_verified":False,"eligible_for_model_scoring":False,
            "production_recommendations":"DISABLED","providers":sorted(providers),"fixtures":rows,
            "matured_fixture_count":len(rows),"missing_source_fixture_count":sum(x["reason"]=="MISSING_SOURCE_RECORDS" for x in rows)}

def main():
    p=argparse.ArgumentParser()
    for arg in ("coverage","parsed","output"):p.add_argument("--"+arg,required=True)
    a=p.parse_args()
    result=matrix(json.loads(Path(a.coverage).read_text()),json.loads(Path(a.parsed).read_text()))
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("SOURCE GAP MATRIX",result["matured_fixture_count"],"matured",result["missing_source_fixture_count"],"missing structured FT")
    for row in result["fixtures"]:print("SOURCE GAP",row["home"],"vs",row["away"],row["source_candidate_counts"],row["reason"])

if __name__=="__main__":main()
