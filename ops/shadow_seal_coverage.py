"""Audit whether independently agreed FT fixtures have genuine sealed pre-match pairs.

This is a coverage diagnostic, NOT an FT verification or a model score.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from team_identity import team_id
from shadow_archive_bridge import export_archives

def coverage(archives, correlations):
    pairs = correlations.get("agreements", []) if isinstance(correlations, dict) else []
    result = {"schema":"football-king-shadow-seal-coverage-v1","status":"HOLD",
              "production_recommendations":"DISABLED","independently_verified":False,
              "source_agreements":len(pairs),"sealed_archives":len(archives),
              "eligible_sealed_pairs":0,"matched_agreements":0,
              "missing_sealed_pairs":0,"ambiguous_sealed_pairs":0,
              "matched_fixture_ids":[],"archive_leagues":{},"archive_date_range":None,"agreement_date_range":None,"eligible_bundesliga_pairs":0,"upcoming_sealed_bundesliga":0,"completed_unmatched_sealed_bundesliga":0,"source_latest_agreement_date":None,"source_lag_days":None,"source_stale_14d":None,"archive_after_latest_source":False,"next_sealed_bundesliga_date":None,"last_sealed_bundesliga_date":None,"as_of_utc":None,"sealed_bundesliga_kickoff_passed_2h":0,"sealed_bundesliga_not_yet_settleable":0}
    now=datetime.now(timezone.utc)
    result["as_of_utc"]=now.isoformat()
    archive_days=[]
    agreement_days=[]
    valid={}
    for row in archives:
        if isinstance(row,dict):
            league=str(row.get("league","UNKNOWN"))
            result["archive_leagues"][league]=result["archive_leagues"].get(league,0)+1
        try:
            kickoff=datetime.fromisoformat(row["kickoff_utc"].replace("Z","+00:00"))
            sealed=datetime.fromisoformat(row["sealed_at_utc"].replace("Z","+00:00"))
            market=datetime.fromisoformat(row["market_snapshot_utc"].replace("Z","+00:00"))
            if any(x.tzinfo is None for x in (kickoff,sealed,market)):
                continue
            if sealed>=kickoff or market>=kickoff:
                continue
            archive_days.append(kickoff.astimezone(timezone.utc).date().isoformat())
            if str(row.get("league","")).lower() not in ("bundesliga","bl1","de.1"):
                continue
            h=team_id("bundesliga",row["home"])
            a=team_id("bundesliga",row["away"])
            if not h or not a or h==a or not isinstance(row.get("fixture_id"),str):
                continue
            key=(h,a,kickoff.astimezone(timezone.utc).date())
            valid.setdefault(key,[]).append(row["fixture_id"])
            result["eligible_sealed_pairs"]+=1
            result["eligible_bundesliga_pairs"]+=1
            if (now-kickoff.astimezone(timezone.utc)).total_seconds()>=7200:
                result["sealed_bundesliga_kickoff_passed_2h"]+=1
            else:
                result["sealed_bundesliga_not_yet_settleable"]+=1
        except (KeyError,TypeError,ValueError,AttributeError):
            continue
    latest_agreement=max((p.get("date_first","") for p in pairs if isinstance(p,dict)),default="")
    result["source_latest_agreement_date"]=latest_agreement or None
    if latest_agreement:
        from datetime import date
        lag=(date.today()-date.fromisoformat(latest_agreement)).days
        result["source_lag_days"]=lag
        result["source_stale_14d"]=lag>14
    for (h,a,day),ids in valid.items():
        if latest_agreement and day.isoformat()>latest_agreement:
            result["upcoming_sealed_bundesliga"]+=len(ids)
        else:
            result["completed_unmatched_sealed_bundesliga"]+=len(ids)
    if valid:
        days=sorted(k[2].isoformat() for k in valid)
        result["next_sealed_bundesliga_date"]=days[0]
        result["last_sealed_bundesliga_date"]=days[-1]
    used=set()
    for p in pairs:
        try:
            h,a=p["home_id"],p["away_id"]
            day=datetime.fromisoformat(p["date_first"]).date()
            agreement_days.append(day.isoformat())
            matches=[fid for (hh,aa,d),ids in valid.items() if hh==h and aa==a and abs((d-day).days)<=1 for fid in ids]
            if len(matches)==1 and matches[0] not in used:
                used.add(matches[0])
                result["matched_agreements"]+=1
                result["matched_fixture_ids"].append(matches[0])
            elif matches:
                result["ambiguous_sealed_pairs"]+=1
            else:
                result["missing_sealed_pairs"]+=1
        except (KeyError,TypeError,ValueError):
            result["ambiguous_sealed_pairs"]+=1
    if archive_days:
        result["archive_date_range"]=[min(archive_days),max(archive_days)]
        result["archive_after_latest_source"]=bool(latest_agreement and min(archive_days)>latest_agreement)
    if agreement_days:
        result["agreement_date_range"]=[min(agreement_days),max(agreement_days)]
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--archives",default="research_pairs")
    parser.add_argument("--correlations",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    archives=export_archives(args.archives)
    pairs=json.loads(Path(args.correlations).read_text(encoding="utf-8"))
    out=Path(args.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(coverage(archives,pairs),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__":
    main()
