"""One-stop value research gate: no unverified model probability or odds."""
import argparse
import json
from pathlib import Path
from ev_screen import screen_ev

def evaluate(rows):
    if not isinstance(rows,list):
        raise ValueError("INVALID_ROWS")
    results=[]
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("INVALID_ROW")
        identity={k:row.get(k) for k in ("fixture_id","market","selection")}
        if not isinstance(row.get("odds"),(float,int)) or not isinstance(row.get("probability"),(float,int)):
            result={"research_candidate":False,"blockers":["MISSING_ODDS_OR_PROBABILITY"],"production_recommendations":"DISABLED"}
        else:
            result=screen_ev(row["odds"],row["probability"],
                calibrated=row.get("calibrated") is True,
                fresh_odds=row.get("fresh_odds") is True)
        results.append({**identity,**result})
    return {"schema":"football-king-value-research-v1",
        "status":"RESEARCH_ONLY",
        "total":len(results),
        "candidate_count":sum(x["research_candidate"] for x in results),
        "results":results,
        "production_recommendations":"DISABLED"}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    report=evaluate(json.loads(Path(args.input).read_text(encoding="utf-8")))
    dest=Path(args.output)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Research candidates:",report["candidate_count"],"/",report["total"])

if __name__=="__main__":
    main()
