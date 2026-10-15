"""Conservative two-publisher FT matching diagnostic; not independent attestation."""
import argparse
import json
import unicodedata
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

def name_key(value):
    if not isinstance(value,str):
        return ""
    return " ".join(unicodedata.normalize("NFKC",value).casefold().split())

def reconcile(openliga,openfootball):
    if not isinstance(openliga,list) or not isinstance(openfootball,list):
        raise ValueError("INVALID_ROWS")
    def key(row,provider):
        if not isinstance(row,dict) or row.get("provider")!=provider or row.get("status")!="FT":
            return None
        try:
            score=row["score_ft"]
            if not isinstance(score,list) or len(score)!=2 or any(type(x) is not int or not 0<=x<=30 for x in score):
                return None
            home=name_key(row["home"]);away=name_key(row["away"])
            if not home or not away or home==away:
                return None
            if provider=="OpenLigaDB":
                date=datetime.fromisoformat(row["kickoff_utc"].replace("Z","+00:00"))
                if date.tzinfo is None:
                    return None
                day=date.astimezone(timezone.utc).date().isoformat()
            else:
                day=row["match_date"]
                if datetime.strptime(day,"%Y-%m-%d").date().isoformat()!=day:
                    return None
            return (day,home,away)
        except (KeyError,TypeError,ValueError,AttributeError):
            return None
    left={};right={}
    for rows,provider,dest in ((openliga,"OpenLigaDB",left),(openfootball,"OpenFootball",right)):
        for row in rows:
            k=key(row,provider)
            if k is not None:
                dest.setdefault(k,[]).append(row)
    agreements=[];disagreements=[];ambiguous=0
    for k in sorted(left.keys() & right.keys()):
        if len(left[k])!=1 or len(right[k])!=1:
            ambiguous+=1
            continue
        a,b=left[k][0],right[k][0]
        item={"match_date":k[0],"home":a["home"],"away":a["away"],
              "openliga_score":a["score_ft"],"openfootball_score":b["score_ft"],
              "source_urls":[a.get("source_url"),b.get("source_url")],
              "raw_sha256":[a.get("raw_sha256"),b.get("raw_sha256")]}
        (agreements if a["score_ft"]==b["score_ft"] else disagreements).append(item)
    return {"schema":"football-king-cross-source-ft-diagnostic-v1","status":"RESEARCH_ONLY",
        "matching_policy":"EXACT_NORMALIZED_NAMES_AND_UTC_DATE",
        "date_only_not_kickoff_verified":True,"external_provenance_rechecked":False,
        "independently_verified":False,"production_recommendations":"DISABLED",
        "exact_agreement_count":len(agreements),"disagreement_count":len(disagreements),
        "ambiguous_match_keys":ambiguous,"agreements":agreements,"disagreements":disagreements}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--openliga",required=True);p.add_argument("--openfootball",required=True)
    p.add_argument("--output",required=True);a=p.parse_args()
    def rows(path):
        obj=json.loads(Path(path).read_text(encoding="utf-8"))
        if obj.get("independently_verified") is not False or obj.get("production_recommendations")!="DISABLED":
            raise ValueError("UNSAFE_CANDIDATE_FILE")
        return obj["rows"]
    report=reconcile(rows(a.openliga),rows(a.openfootball))
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("exact_agreement_count","disagreement_count","ambiguous_match_keys")}))
if __name__=="__main__":
    main()
