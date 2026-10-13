"""Fail-closed ambiguity triage; never turns HTML context into verified FT."""
import argparse
import json
from pathlib import Path

def triage(report):
    if report.get("status")!="HOLD" or report.get("independently_verified") is not False or report.get("eligible_for_model_scoring") is not False:
        raise ValueError("UNSAFE_INPUT")
    fixtures=[]
    for row in report.get("fixtures",[]):
        providers=row.get("provider_diagnostics",{})
        if len(providers)<2:continue
        per={}
        for provider,details in providers.items():
            raw=details.get("plausible_score_like_tokens",[])
            values=set()
            for item in raw:
                if not isinstance(item,list) or len(item)!=2 or any(type(x) is not int or not 0<=x<=15 for x in item):
                    raise ValueError("INVALID_CANDIDATE")
                values.add(tuple(item))
            per[provider]={"distinct_candidate_scores":[list(x) for x in sorted(values)],
                           "distinct_count":len(values),
                           "truncated":details.get("tokens_truncated",False)}
        sets=[{tuple(v) for v in x["distinct_candidate_scores"]} for x in per.values()]
        common=set.intersection(*sets) if sets else set()
        # Even identical unique tokens do not establish fixture association or FT status.
        label=("NO_SHARED_CANDIDATE" if not common else
               "MULTIPLE_POSSIBLE_SCORES" if len(common)>1 or any(x["distinct_count"]>1 or x["truncated"] for x in per.values()) else
               "ONE_SHARED_TOKEN_NOT_FT")
        fixtures.append({"fixture_id":row["fixture_id"],"ambiguity":label,
                         "shared_tokens_unverified":[list(x) for x in sorted(common)],
                         "sources":per,"independently_verified":False,
                         "eligible_for_model_scoring":False})
    return {"schema":"football-king-shadow-ambiguity-triage-v1",
            "status":"HOLD","independently_verified":False,"eligible_for_model_scoring":False,
            "production_recommendations":"DISABLED","fixture_count":len(fixtures),
            "fixtures":fixtures}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--diagnostics",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    data=triage(json.loads(Path(a.diagnostics).read_text(encoding="utf-8")))
    path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for f in data["fixtures"]:
        print("AMBIGUITY",f["fixture_id"],f["ambiguity"],"shared_unverified",f["shared_tokens_unverified"])
    print("FT CERTIFICATION BLOCKED",data["fixture_count"],"contexts")

if __name__=="__main__":main()
