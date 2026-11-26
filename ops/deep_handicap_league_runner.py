"""Run two pinned season indexes; no raw or statistical research output."""
import json
import sys
from deep_handicap_historical_smoke import fetch, INDEX_LIMIT
from deep_handicap_historical_inputs import _decode
from deep_handicap_league_benchmark import evaluate,LEAGUES

def run():
    out={"status":"HOLD","production_recommendations":"DISABLED",
         "true_forward_sample_count":0,"research_metrics_published":False,
         "data_source":"StatsBomb Open Data","completed_cohorts":0,"cohorts":[]}
    for c in LEAGUES:
        entry={"competition_id":c,"compatibility":"FAIL"}
        try:
            r=evaluate(_decode(fetch(f"data/matches/{c}/27.json",INDEX_LIMIT,league_indexes=True),INDEX_LIMIT),c)
            if (r["reason"]=="RETROSPECTIVE_HYPOTHETICAL_MARGIN_ONLY"
                    and r["private_metrics"] is not None
                    and (r["train_count"],r["holdout_count"])==LEAGUES[c]
                    and r["evaluated_count"]==r["holdout_count"]
                    and r["production_recommendations"]=="DISABLED"
                    and type(r["true_forward_sample_count"]) is int and r["true_forward_sample_count"]==0):
                entry.update(compatibility="PASS",train_count=r["train_count"],
                             holdout_count=r["holdout_count"],evaluated_count=r["evaluated_count"])
                out["completed_cohorts"]+=1
        except Exception:
            pass
        out["cohorts"].append(entry)
    print(json.dumps(out),flush=True)
    return 0 if out["completed_cohorts"]==len(LEAGUES) else 1

if __name__=="__main__":
    sys.exit(run())
