"""Simple pre-match over/under 2.5 research, not betting advice."""
import argparse
import json
import math
from pathlib import Path
from ev_screen import screen_ev

def poisson_over25(expected_goals):
    if type(expected_goals) not in (int,float) or not math.isfinite(expected_goals) or not 0<=expected_goals<=12:
        raise ValueError("INVALID_EXPECTED_GOALS")
    return 1-math.exp(-expected_goals)*(1+expected_goals+expected_goals**2/2)

def evaluate(rows):
    if not isinstance(rows,list):
        raise ValueError("INVALID_ROWS")
    results=[]
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("INVALID_ROW")
        out={"fixture_id":row.get("fixture_id"),"market":"TOTAL_GOALS_2.5",
             "status":"HOLD","production_recommendations":"DISABLED"}
        lam=row.get("expected_goals")
        if lam is None:
            out["blockers"]=["MISSING_EXPECTED_GOALS"]
        else:
            try:
                p=poisson_over25(lam)
            except ValueError:
                out["blockers"]=["INVALID_EXPECTED_GOALS"]
                results.append(out)
                continue
            out["probability_over"]=round(p,6)
            out["probability_under"]=round(1-p,6)
            odds=row.get("over_odds")
            under=row.get("under_odds")
            if type(odds) not in (int,float) or type(under) not in (int,float):
                out["blockers"]=["MISSING_BOTH_SIDES_ODDS"]
            else:
                try:
                    a=screen_ev(odds,p,calibrated=row.get("calibrated") is True,
                                fresh_odds=row.get("fresh_odds") is True)
                    z=screen_ev(under,1-p,calibrated=row.get("calibrated") is True,
                                fresh_odds=row.get("fresh_odds") is True)
                except ValueError:
                    out["blockers"]=["INVALID_ODDS_INPUT"]
                    results.append(out)
                    continue
                # Normalize both implied probabilities to remove the simple overround.
                market_over=(1/odds)/((1/odds)+(1/under))
                divergence=abs(p-market_over)
                out["market_probability_over_no_vig"]=round(market_over,6)
                out["model_market_divergence"]=round(divergence,6)
                if divergence>0.15:
                    out["status"]="HOLD"
                    out["blockers"]=["MODEL_MARKET_DIVERGENCE_UNVERIFIED"]
                    out["over_ev"]=a["ev"]
                    out["under_ev"]=z["ev"]
                    results.append(out)
                    continue
                out["over_ev"]=a["ev"]
                out["under_ev"]=z["ev"]
                if a["research_candidate"] or z["research_candidate"]:
                    side="OVER_2.5" if a["research_candidate"] and (not z["research_candidate"] or a["ev"]>=z["ev"]) else "UNDER_2.5"
                    out["status"]="RESEARCH_CANDIDATE"
                    out["side"]=side
                else:
                    out["blockers"]=sorted(set(a["blockers"]+z["blockers"]))
        results.append(out)
    return {"schema":"football-king-over-under-25-v1","status":"RESEARCH_ONLY",
            "market":"TOTAL_GOALS_2.5","candidate_count":sum(x["status"]=="RESEARCH_CANDIDATE" for x in results),
            "production_recommendations":"DISABLED","results":results}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    result=evaluate(json.loads(Path(a.input).read_text(encoding="utf-8")))
    dest=Path(a.output)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__":
    main()
