"""Mobile-friendly forward research status: ALL six leagues, no invented edges.

Scores, calibration, uncertainty and A/B summaries only use previously sealed
pre-match observations after real outcomes are finalized. Samples from an
unverified public score feed remain labeled as such.
"""
import argparse
import json
import math
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

LEAGUES=("epl","championship","bundesliga","laliga","seriea","ligue1")
NAMES={"epl":"英超","championship":"英冠","bundesliga":"德甲",
       "laliga":"西甲","seriea":"意甲","ligue1":"法甲"}


def score(probs,y):
    if (not isinstance(probs,list) or len(probs)!=3 or y not in (0,1,2)
            or not all(type(x) in (int,float) and math.isfinite(x) and 0<=x<=1 for x in probs)
            or abs(sum(probs)-1)>.002):
        raise ValueError("INVALID_SCORE_INPUT")
    return -math.log(max(probs[y],1e-15)),sum((v-int(i==y))**2 for i,v in enumerate(probs))


def calibration(samples):
    bins=[[{"n":0,"sum_p":0.0,"hits":0} for _ in range(5)] for outcome in range(3)]
    for row in samples:
        for i,p in enumerate(row["p"]):
            idx=min(4,int(p*5))
            bins[i][idx]["n"]+=1
            bins[i][idx]["sum_p"]+=p
            bins[i][idx]["hits"]+=int(row["y"]==i)
    return [{
        "outcome":label,
        "bins":[{"probability_band":f"{j*20}–{(j+1)*20}%",
                 "n":d["n"],"forecast_mean":round(d["sum_p"]/d["n"],4) if d["n"] else None,
                 "observed_frequency":round(d["hits"]/d["n"],4) if d["n"] else None}
                for j,d in enumerate(outcome_bins)]
        } for label,outcome_bins in zip(("home","draw","away"),bins)]


def metrics(rows):
    if not rows:
        return None
    totals={"model_log_loss":0.0,"market_log_loss":0.0,"model_brier":0.0,"market_brier":0.0}
    ab_losses=[]
    weekly=defaultdict(list)
    for r in rows:
        ll,bs=score(r["p"],r["y"])
        bm,ms=score(r["m"],r["y"])
        totals["model_log_loss"]+=ll
        totals["model_brier"]+=bs
        totals["market_log_loss"]+=bm
        totals["market_brier"]+=ms
        weekly[r["kickoff_utc"][:10]].append(bm-ll)
        if "ab" in r:
            alt=score(r["ab"],r["y"])
            ab_losses.append((alt[0],ll,alt[1],bs))
    n=len(rows)
    result={k:round(v/n,6) for k,v in totals.items()}
    result["market_minus_model_log_loss"]=round(
        (totals["market_log_loss"]-totals["model_log_loss"])/n,6)
    result["settled_games"]=n
    result["unique_kickoff_dates"]=len(weekly)
    result["ab_research"]={
        "same_case_count":len(ab_losses),
        "candidate_log_loss":round(sum(v[0] for v in ab_losses)/len(ab_losses),6) if ab_losses else None,
        "baseline_log_loss":round(sum(v[1] for v in ab_losses)/len(ab_losses),6) if ab_losses else None,
        "candidate_brier":round(sum(v[2] for v in ab_losses)/len(ab_losses),6) if ab_losses else None,
        "baseline_brier":round(sum(v[3] for v in ab_losses)/len(ab_losses),6) if ab_losses else None,
        "promoted":False,
    }
    result["descriptive_only"]=True
    return result


def build(site, settled_doc):
    site=Path(site)
    def load(name):
        path=site/name
        return json.loads(path.read_text(encoding="utf-8"))
    status=load("status.json")
    market=load("market_status.json")
    validation=load("validation.json")
    source=load("crosscheck.json")
    coverage=load("league_coverage.json")
    ab=load("ab_status.json")
    shadow=load("shadow.json")
    if (settled_doc.get("production_recommendations")!="DISABLED"
            or status.get("production_recommendations")!="DISABLED"
            or market.get("production_recommendations")!="DISABLED"
            or validation.get("status")!="HOLD"
            or coverage.get("production_recommendations")!="DISABLED"
            or ab.get("promotion_allowed") is not False):
        raise ValueError("UNSAFE_RESEARCH_CENTER_SOURCE")
    samples=settled_doc.get("samples",[])
    if not isinstance(samples,list) or settled_doc.get("n")!=len(samples):
        raise ValueError("INVALID_SETTLED_SAMPLE_COUNT")
    groups=defaultdict(list)
    for row in samples:
        if not isinstance(row,dict) or row.get("league") not in LEAGUES or row.get("y") not in (0,1,2):
            raise ValueError("INVALID_SETTLED_SAMPLE")
        score(row["p"],row["y"])
        score(row["m"],row["y"])
        if "ab" in row:
            score(row["ab"],row["y"])
        groups[row["league"]].append(row)
    public={l["league"]:l for l in coverage.get("league_coverage",[]) if isinstance(l,dict)}
    pair_counts=defaultdict(int)
    for item in load("market_comparison.json").get("comparisons",[]):
        if isinstance(item,dict) and item.get("league") in LEAGUES:
            pair_counts[item["league"]]+=1
    league_cards=[]
    for league in LEAGUES:
        c=public.get(league,{})
        data=groups[league]
        league_cards.append({
            "id":league,"name":NAMES[league],
            "public_window_fixtures":c.get("public_fixtures",0),
            "precise_scheduled_kickoffs":c.get("precise_scheduled_kickoffs",0),
            "market_fixtures":c.get("market_fixture_metadata",0),
            "two_source_kickoff_agreements":c.get("two_source_kickoff_agreements",0),
            "unconfirmed_kickoff_alerts":c.get("time_disagreements_needing_review",0),
            "strict_pre_match_pairs_current_run":pair_counts[league],
            "settled_held_out_samples":len(data),
            "comparison":metrics(data),
            "results_independently_verified":False,
        })
    return {
        "schema":"football-king-research-center-1",
        "generated_utc":status.get("checked_utc"),
        "status":"RESEARCH_ONLY" if status.get("status")=="RESEARCH_ONLY" else "HOLD",
        "market_status":market.get("source_state"),
        "market_age_utc":market.get("market_as_of_utc"),
        "free_quota":market.get("quota"),
        "total_market_fixtures":market.get("market_events",0),
        "total_shadow_candidates":shadow.get("predictions_count",0),
        "total_strict_market_pairs":market.get("matched_count",0),
        "total_completed_comparable_samples":len(samples),
        "total_independently_confirmed_kickoffs":coverage.get("total_confirmed_kickoffs",0),
        "six_league_result_verification_complete":False,
        "bundesliga_independent_completed_result_comparisons":source.get("score_comparisons",0),
        "validation_status":"HOLD",
        "shadow_ab_status":ab.get("status","HOLD"),
        "league_cards":league_cards,
        "aggregate_metrics":metrics(samples),
        "calibration":calibration(samples) if samples else None,
        "calibration_reliable":False,
        "ab_candidate_promoted":False,
        "guaranteed_positive_roi":False,
        "market_odds_are_executable":False,
        "production_recommendations":"DISABLED",
        "notice":"Only timestamped historical research; performance estimates are descriptive until independently validated.",
    }


def publish(site, evidence):
    p=Path(evidence)
    if p.exists():
        settled=json.loads(p.read_text(encoding="utf-8"))
    else:
        settled={"samples":[],"n":0,"production_recommendations":"DISABLED"}
    report=build(site,settled)
    (Path(site)/"research_center.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return {"status":report["status"],
            "settled":report["total_completed_comparable_samples"],
            "market":report["total_market_fixtures"],
            "strict_pairs":report["total_strict_market_pairs"],
            "production_recommendations":"DISABLED"}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--site",default="app/site")
    p.add_argument("--evidence",default="settled-next.json")
    args=p.parse_args()
    print(json.dumps(publish(args.site,args.evidence),ensure_ascii=False))
