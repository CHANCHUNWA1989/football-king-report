"""Independent schedule agreement on a community matchday snapshot.

Only use a separately fetched provider's match observations from <=36h
ago. Never infer missing names/dates, never train/refit a model, and never
treat two agreeing publishers as proof of official accuracy.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from source_publish_guard import verify as validate_other
from team_identity import team_id
from live_germany import SHORTCUTS, iso

FRESH_HOURS = 36
TOLERANCE_MINUTES = 45


def crosscheck(german, other, now=None):
    now = now or datetime.now(timezone.utc)
    out = dict(german)
    out["independent_secondary_provider"] = "TheSportsDB"
    out["schedule_crosscheck_completed"] = False
    out["schedule_crosscheck_time_utc"] = None
    out["two_source_kickoff_agreements"] = 0
    out["unverified_single_source_fixtures"] = 0
    out["kickoff_disagreements_needing_review"] = 0
    out["independent_result_evidence_not_official"] = True
    out["formal_prediction_validation_unaffected"] = True
    if not isinstance(other, dict):
        others = {}
    else:
        try:
            sampled = validate_other(other)
            if not -300 <= (now - sampled).total_seconds() <= FRESH_HOURS*3600:
                raise ValueError("SECONDARY_SOURCE_STALE")
            observations = other.get("sampled_fixtures") or []
            others = {}
            for item in observations:
                if (not isinstance(item, dict) or item.get("provider") != "thesportsdb"
                        or item.get("league") not in SHORTCUTS):
                    continue
                league=item["league"]
                h,a=team_id(league,item.get("home")),team_id(league,item.get("away"))
                if not h or not a or h==a:
                    continue
                try:
                    at=iso(item["kickoff_utc"])
                except (KeyError,TypeError,ValueError,OverflowError):
                    continue
                others.setdefault((league,h,a),[]).append((at,item))
            out["schedule_crosscheck_completed"] = True
            out["schedule_crosscheck_time_utc"] = sampled.isoformat()
        except (ValueError,TypeError,KeyError,OverflowError):
            others = {}
    matched=solo=conflict=0
    result=[]
    for row in german.get("matches",[]):
        item=dict(row)
        item["crosscheck_state"]="SINGLE_COMMUNITY_SOURCE"
        item["crosscheck_provider"]=None
        league=item["league"]
        key=(league,team_id(league,item["home"]),team_id(league,item["away"]))
        candidates=others.get(key,[]) if all(key) else []
        # A single matching opponent fixture per 7-day range avoids a
        # postponed match being paired with a future rematch.
        try:
            ko=iso(item["kickoff_utc"])
            nearby=[(dt,r) for dt,r in candidates
                    if abs((dt-ko).total_seconds()) <= 7*86400]
        except (ValueError,KeyError,TypeError):
            nearby=[]
        if len(nearby)==1:
            dt,ob=nearby[0]
            diff=abs((dt-ko).total_seconds())/60
            if diff<=TOLERANCE_MINUTES:
                item["crosscheck_state"]="TWO_PUBLISHER_KICKOFF_AGREEMENT"
                item["crosscheck_provider"]="TheSportsDB"
                matched+=1
                if (item["score_ft"] is not None and ob.get("status")=="FINISHED"
                        and ob.get("score_ft") is not None):
                    if item["score_ft"]!=ob["score_ft"]:
                        item["crosscheck_state"]="FINISHED_SCORE_CONFLICT_REVIEW"
                        conflict+=1
                        matched-=1
            else:
                item["crosscheck_state"]="KICKOFF_CONFLICT_REVIEW"
                item["crosscheck_provider"]="TheSportsDB"
                conflict+=1
        else:
            solo+=1
        result.append(item)
    out["matches"]=result
    out["two_source_kickoff_agreements"]=matched
    out["unverified_single_source_fixtures"]=solo
    out["kickoff_disagreements_needing_review"]=conflict
    return out


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--live",required=True)
    ap.add_argument("--secondary",default="sources/latest.json")
    opts=ap.parse_args()
    p=Path(opts.live)
    live=json.loads(p.read_text(encoding="utf-8"))
    q=Path(opts.secondary)
    if q.is_file():
        try:other=json.loads(q.read_text(encoding="utf-8"))
        except (ValueError,UnicodeError,OSError):other=None
    else:
        other=None
    report=crosscheck(live,other)
    p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"crosscheck_completed":report["schedule_crosscheck_completed"],
                      "two_source_agreements":report["two_source_kickoff_agreements"],
                      "solo":report["unverified_single_source_fixtures"],
                      "conflicts":report["kickoff_disagreements_needing_review"],
                      "production_recommendations":"DISABLED"},ensure_ascii=False))


if __name__=="__main__":
    main()
