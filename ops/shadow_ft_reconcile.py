"""Conservative two-publisher Bundesliga FT candidate reconciliation.

Agreement is corroboration only: no independent kickoff or forecast seal proof.
"""
import argparse
import json
from datetime import date,datetime,timezone
from pathlib import Path
from source_crosscheck import normalized_team

def reconcile(document):
    sources=document.get("sources",[])
    if document.get("status")!="HOLD" or len(sources)!=2:
        return {"status":"HOLD","reason":"MISSING_SOURCES","candidates":[],"conflicts":[]}
    by={s.get("provider"):s.get("records",[]) for s in sources}
    if set(by)!={"OpenLigaDB","OpenFootball"}:
        return {"status":"HOLD","reason":"WRONG_SOURCES","candidates":[],"conflicts":[]}
    a,b=by["OpenLigaDB"],by["OpenFootball"]
    candidates,conflicts=[],[]
    used=set()
    for left in a:
        try:
            when=datetime.fromisoformat(left["kickoff_utc"].replace("Z","+00:00"))
            if when.tzinfo is None:continue
            home,away=normalized_team(left["home"]),normalized_team(left["away"])
            if not home or not away or home==away:continue
            possible=[]
            for j,right in enumerate(b):
                if (normalized_team(right.get("home"))==home
                        and normalized_team(right.get("away"))==away
                        and abs((date.fromisoformat(right["date"])-when.date()).days)<=1):
                    possible.append((j,right))
            if len(possible)!=1:continue
            j,right=possible[0]
            reverse=sum(1 for item in a if
                normalized_team(item.get("home"))==home
                and normalized_team(item.get("away"))==away
                and abs((datetime.fromisoformat(item["kickoff_utc"].replace("Z","+00:00")).date()-date.fromisoformat(right["date"])).days)<=1)
            if reverse!=1 or j in used:continue
            used.add(j)
            score_a,score_b=left["score_ft"],right["score_ft"]
            if (not all(isinstance(s,list) and len(s)==2 and all(type(n) is int and 0<=n<=30 for n in s)
                        for s in (score_a,score_b))):continue
            record={"league":"bundesliga","home":left["home"],"away":left["away"],
                    "kickoff_utc":left["kickoff_utc"],"score_a":score_a,"score_b":score_b}
            if score_a==score_b:candidates.append(record)
            else:conflicts.append(record)
        except (KeyError,TypeError,ValueError,AttributeError):continue
    return {"status":"HOLD","reason":"CANDIDATE_CORROBORATION_ONLY",
            "candidates":candidates,"conflicts":conflicts,
            "independently_verified":False,"production_recommendations":"DISABLED"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    result=reconcile(json.loads(Path(a.input).read_text()))
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
if __name__=="__main__":main()
