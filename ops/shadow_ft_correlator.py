"""Conservative two-publisher Bundesliga full-time candidate correlation.

No fabricated timestamps, no fuzzy team guesses, no automatic certification.
"""
import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from team_identity import team_id

def correlate(bundle):
    result={"schema":"football-king-shadow-bundesliga-ft-correlations-v1",
            "status":"HOLD","independently_verified":False,
            "production_recommendations":"DISABLED","agreements":[],
            "conflicts":[],"ambiguous":0,"unmatched":0,"unmatched_second":0}
    sources=bundle.get("sources",[]) if isinstance(bundle,dict) else []
    if len(sources)!=2 or {x.get("provider") for x in sources}!={"OpenLigaDB","OpenFootball"}:
        return result
    def normalize(source):
        out={}
        for row in source["records"]:
            try:
                h=team_id("bundesliga",row["home"])
                a=team_id("bundesliga",row["away"])
                score=row["score_ft"]
                if not h or not a or h==a or not isinstance(score,list) or len(score)!=2 or any(type(x) is not int or x<0 or x>30 for x in score):
                    continue
                if "kickoff_utc" in row:
                    day=datetime.fromisoformat(row["kickoff_utc"].replace("Z","+00:00")).date()
                else:
                    day=date.fromisoformat(row["date"])
                key=(h,a,day)
                out.setdefault(key,[]).append(tuple(score))
            except (KeyError,ValueError,TypeError,AttributeError):
                continue
        return out
    first=normalize(next(x for x in sources if x["provider"]=="OpenLigaDB"))
    second=normalize(next(x for x in sources if x["provider"]=="OpenFootball"))
    used=set()
    for (h,a,day),scores in first.items():
        possible=[(k,v) for k,v in second.items() if k[0]==h and k[1]==a and abs((k[2]-day).days)<=1]
        reverse=sum(1 for k in first if k[0]==h and k[1]==a and abs((k[2]-possible[0][0][2]).days)<=1) if len(possible)==1 else 0
        if not possible:\n            result["unmatched"]+=1\n            continue\n        if len(scores)!=1 or len(possible)!=1 or reverse!=1 or len(possible[0][1])!=1 or possible[0][0] in used:
            result["ambiguous"]+=1
            continue
        other,other_scores=possible[0]
        used.add(other)
        record={"home_id":h,"away_id":a,"date_first":day.isoformat(),
                "date_second":other[2].isoformat(),
                "score_first":list(scores[0]),"score_second":list(other_scores[0])}
        if scores[0]==other_scores[0]:
            result["agreements"].append(record)
        else:
            result["conflicts"].append(record)
    result["unmatched_second"]=sum(1 for k in second if k not in used)\n    result["status"]="CONFLICT" if result["conflicts"] else "PARTIAL_CHECK" if result["agreements"] else "HOLD"
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    Path(a.output).write_text(json.dumps(correlate(json.loads(Path(a.input).read_text())),ensure_ascii=False,indent=2)+"\n")
if __name__=="__main__":main()
