"""Audit independent FREE 90-minute final-score agreement without rewriting evidence.

Only observations in a verified source snapshot may corroborate a previously
sealed forward sample. No new predictions or releases are created here.
"""
import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from source_publish_guard import verify
from team_identity import team_id

PROVIDERS=("thesportsdb","api_football","football_data_org")
LEAGUES=("epl","championship","bundesliga","laliga","seriea","ligue1")


def utc(text):
    t=datetime.fromisoformat(str(text).replace("Z","+00:00"))
    if t.tzinfo is None:
        raise ValueError("NAIVE_UTC")
    return t.astimezone(timezone.utc)


def compare(evidence, sources, now=None):
    now=now or datetime.now(timezone.utc)
    result={"schema":"football-king-independent-final-score-audit-v1",
            "status":"HOLD","settled_evidence_count":0,
            "single_source_agreements":0,"two_provider_agreements":0,
            "conflicting_observations":0,"unmatched_samples":0,
            "provider_counts":{p:0 for p in PROVIDERS},
            "provenance":"FREE_SOURCE_ARCHIVED_AFTER_OUTCOME_NOT_POINT_IN_TIME_MARKET",
            "all_six_leagues_verified":False,"independently_validated_prediction_value":False,
            "profitability_verified":False,"can_unlock_betting":False,
            "production_recommendations":"DISABLED"}
    if (not isinstance(evidence,dict) or evidence.get("production_recommendations")!="DISABLED"
            or not isinstance(evidence.get("samples"),list)
            or evidence.get("n")!=len(evidence["samples"])):
        return result
    result["settled_evidence_count"]=len(evidence["samples"])
    if not isinstance(sources,dict):
        return result
    try:
        stamp=verify(sources)
        if not -300 <= (now-stamp).total_seconds() <= 48*3600:
            return result
    except (TypeError,KeyError,ValueError,OverflowError):
        return result
    idx=defaultdict(list)
    for item in sources["sampled_fixtures"]:
        if (item.get("provider") not in PROVIDERS or item.get("status")!="FINISHED"
                or not isinstance(item.get("score_ft"),list)):
            continue
        league=item.get("league")
        if league not in LEAGUES:continue
        h=team_id(league,item.get("home")); a=team_id(league,item.get("away"))
        if not h or not a or h==a:continue
        score=item["score_ft"]
        if len(score)!=2 or any(type(s) is not int or not 0<=s<=30 for s in score):
            continue
        outcome=0 if score[0]>score[1] else 1 if score[0]==score[1] else 2
        try:
            kickoff = utc(item["kickoff_utc"])
        except (KeyError, TypeError, ValueError, OverflowError):
            # One malformed free-provider fixture must not abort the whole audit.
            continue
        idx[(league,h,a)].append((item["provider"],kickoff,outcome))
    if not idx:
        result["status"]="PARTIAL_CHECK"
        result["unmatched_samples"]=len(evidence["samples"])
        return result
    for sample in evidence["samples"]:
        try:
            key=json.loads(sample["key"])
            league=sample["league"]
            kickoff=utc(sample["kickoff_utc"])
            if len(key)!=4 or key[0]!=league:
                raise ValueError("INVALID_ARCHIVED_IDENTITY")
            fixture=(league,team_id(league,key[1]),team_id(league,key[2]))
            y=sample["y"]
            if type(y) is not int or y not in (0,1,2):
                raise ValueError("INVALID_ARCHIVED_OUTCOME")
        except (ValueError,TypeError,KeyError,IndexError):
            result["unmatched_samples"]+=1
            continue
        matched=[(provider,outcome) for provider,date,outcome in idx.get(fixture,[])
                 if abs((date-kickoff).total_seconds())<=45*60]
        if not matched:
            result["unmatched_samples"]+=1
            continue
        votes=defaultdict(set)
        for provider,outcome in matched:
            votes[provider].add(outcome)
        if any(len(outcomes)>1 for outcomes in votes.values()):
            result["conflicting_observations"]+=1
            continue
        for p,vs in votes.items():
            result["provider_counts"][p]+=1
        if any(next(iter(v))!=y for v in votes.values()):
            result["conflicting_observations"]+=1
        elif len(votes)>=2:
            result["two_provider_agreements"]+=1
        else:
            result["single_source_agreements"]+=1
    result["status"]="PARTIAL_CHECK"
    return result


def publish(site, evidence_path, sources_path):
    site=Path(site)
    evidence=json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    src=json.loads(Path(sources_path).read_text(encoding="utf-8")) if Path(sources_path).is_file() else None
    result=compare(evidence,src)
    (site/"independent_results.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in (
        "status","settled_evidence_count","single_source_agreements",
        "two_provider_agreements","conflicting_observations","production_recommendations")}))
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--site",default="app/site")
    p.add_argument("--evidence",required=True)
    p.add_argument("--sources",default="sources/latest.json")
    a=p.parse_args()
    publish(a.site,a.evidence,a.sources)
