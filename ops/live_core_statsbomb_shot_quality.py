"""Private StatsBomb pre-shot xG descriptive reliability; not a betting model.

No network, no raw/derived data in Git or CI. Check research-use rights,
StatsBomb attribution and logo requirements before distributing results.
"""
import json
import math
from collections import Counter
from pathlib import Path
from live_core_statsbomb_cohort import load_plan, load
from live_core_statsbomb_event_replay import decode, replay, MAX

OUTCOMES=frozenset(("Goal","Saved","Saved to Post","Saved Off Target","Blocked","Off T","Post","Wayward"))
TYPES=frozenset(("Open Play","Free Kick","Penalty","Corner","Kick Off"))

def shot_rows(raw,pin,home,away):
    events=decode(raw,pin)
    replay(events,home,away)  # existing strict event order/identity/period/xG guard
    rows=[]
    for event in events:
        if event["period"] not in (1,2) or event["type"]["name"]!="Shot":
            continue
        s=event["shot"]
        outcome=s["outcome"]["name"]
        kind=s["type"]["name"]
        if outcome not in OUTCOMES or kind not in TYPES:
            raise ValueError("UNKNOWN_SHOT_CATEGORY")
        p=s["statsbomb_xg"]
        rows.append((p,int(outcome=="Goal"),kind=="Penalty"))
    return rows

def reliability(rows):
    bins=[]
    for i in range(5):
        group=[(p,y) for p,y in rows if min(4,int(p*5))==i]
        n=len(group)
        bins.append({"lower":i/5,"upper":(i+1)/5,"n":n,
                     "mean_xg":math.fsum(p for p,_ in group)/n if n else None,
                     "goal_frequency":sum(y for _,y in group)/n if n else None})
    n=len(rows)
    return {"shots":n,"goals_from_shots":sum(y for _,y in rows),
            "mean_xg":math.fsum(p for p,_ in rows)/n if n else None,
            "brier":math.fsum((p-y)**2 for p,y in rows)/n if n else None,
            "log_loss":math.fsum(-math.log(max(1e-15,p if y else 1-p)) for p,y in rows)/n if n else None,
            "bins":bins,"small_shot_sample":n<100,
            "ece":math.fsum(b["n"]*abs(b["mean_xg"]-b["goal_frequency"]) for b in bins if b["n"])/n if n else None}

def summarize(rows):
    return {"all_shots":reliability([(p,y) for p,y,_ in rows]),
            "nonpenalty":reliability([(p,y) for p,y,pen in rows if not pen]),
            "penalty":reliability([(p,y) for p,y,pen in rows if pen])}

def run(root):
    root,plan,pins=load_plan(root)
    groups={"group_stage":[],"knockout_stage":[]}
    accepted=Counter()
    rejected=Counter()
    for day,mid,h,a in plan:
        stage="group_stage" if day<"2022-12-03" else "knockout_stage"
        try:
            rows=shot_rows(load(root,f"{mid}.json",MAX),pins[str(mid)],h,a)
            groups[stage].extend(rows)
            accepted[stage]+=1
        except (ValueError,KeyError,TypeError,AttributeError,OverflowError,OSError,RecursionError):
            rejected[stage]+=1
    return {"source":"StatsBomb","source_url":"https://github.com/hudl/open-data",
            "private_research_only":True,"scheduled":len(plan),
            "accepted":sum(accepted.values()),"rejected":sum(rejected.values()),
            "complete_cohort":sum(accepted.values())==len(plan),
            "stages":{k:{"accepted_matches":accepted[k],"rejected_matches":rejected[k],
                         **summarize(v)} for k,v in groups.items()},
            "own_goals_not_shot_outcomes":True,"extra_time_and_shootout_excluded":True,
            "shot_observations_not_independent":True,"selection_bias_not_ruled_out":True,
            "psxg_available":False,"psxg_inferred_from_xg":False,
            "independent_prospective_validation":False,"verified_forward_sample_credit":0,
            "model_calibrated":False,"positive_ev_verified":False,
            "production_recommendations":"DISABLED","status":"HOLD"}

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_directory",type=Path)
    p.add_argument("--private-output",type=Path,required=True)
    a=p.parse_args()
    root=a.private_directory.resolve(strict=True)
    output=a.private_output
    if output.is_symlink() or output.parent.resolve(strict=True)!=root:
        raise ValueError("OUTPUT_MUST_BE_IN_PRIVATE_DIRECTORY")
    result=run(root)
    # Exclusive creation; never overwrite an existing private file.
    with output.open("x",encoding="utf-8") as f:
        json.dump(result,f,sort_keys=True,allow_nan=False)
