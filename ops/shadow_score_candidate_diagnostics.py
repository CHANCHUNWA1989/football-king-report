"""Report score-like tokens near real fixtures, without certifying FT."""
import argparse
import json
from pathlib import Path

def diagnose(probe):
    if probe.get("status")!="HOLD" or probe.get("independently_verified") is not False or probe.get("eligible_for_model_scoring") is not False:
        raise ValueError("UNSAFE_PROBE")
    overlap=set(probe.get("both_sources_name_overlap_fixture_ids",[]))
    sources=probe.get("source_probes",[])
    rows={}
    for source in sources:
        provider=source.get("provider")
        if not provider or provider in rows:
            raise ValueError("DUPLICATE_OR_MISSING_PROVIDER")
        rows[provider]={}
        for item in source.get("fixture_text_checks",[]):
            fid=item["fixture_id"]
            if fid not in overlap:continue
            if fid in rows[provider]:raise ValueError("DUPLICATE_FIXTURE")
            tokens=item.get("score_like_tokens_unverified",[])
            valid=[]
            for token in tokens:
                a,b=token.get("home_goals_candidate"),token.get("away_goals_candidate")
                if type(a) is int and type(b) is int and 0<=a<=15 and 0<=b<=15:
                    valid.append([a,b])
            rows[provider][fid]={"score_like_token_count":len(tokens),
                                 "plausible_score_like_tokens":valid,
                                 "tokens_truncated":bool(item.get("score_like_tokens_truncated"))}
    fixtures=[]
    for fid in sorted(overlap):
        provider_tokens={name:data.get(fid,{"score_like_token_count":0,"plausible_score_like_tokens":[],"tokens_truncated":False}) for name,data in rows.items()}
        fixtures.append({"fixture_id":fid,"provider_diagnostics":provider_tokens,
                         "status":"UNVERIFIED_CONTEXT_ONLY","eligible_for_model_scoring":False})
    return {"schema":"football-king-shadow-score-candidate-diagnostics-v1",
            "status":"HOLD","independently_verified":False,"eligible_for_model_scoring":False,
            "production_recommendations":"DISABLED","fixture_count":len(fixtures),
            "warning":"Score-like tokens may be times, unrelated fixtures or other numbers; no FT binding or verification.",
            "fixtures":fixtures}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--probe",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    data=diagnose(json.loads(Path(a.probe).read_text(encoding="utf-8")))
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("UNVERIFIED SCORE DIAGNOSTICS",data["fixture_count"],"overlapping fixture contexts")
    for f in data["fixtures"]:
        print("CANDIDATES",f["fixture_id"],{k:v["plausible_score_like_tokens"] for k,v in f["provider_diagnostics"].items()})

if __name__=="__main__":main()
