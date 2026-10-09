"""Isolated alternate bookmaker-consensus research, never overrides main odds.

Additional BSD comparisons use the ORIGINAL frozen pre-match model only,
and do not claim an independent extra bookmaker or executable odds.
"""
import argparse,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from bsd_guard import validate
from market_pair import pair

def build(shadow, latest, *, now=None):
    now=now or datetime.now(timezone.utc)
    result={
        "schema":"football-king-bsd-optional-market-overlay-v1",
        "created_utc":now.isoformat(),"status":"HOLD",
        "source":"BSD FREE CONSENSUS MARKET",
        "reason":"NO_CONFIGURED_FREE_TOKEN",
        "source_state":"NOT_CONFIGURED",
        "last_source_checked_utc":None,
        "source_age_hours":None,
        "six_league_fixture_count":0,"market_event_count":0,
        "time_valid_shadow_pairs":0,
        "provenance":"BSD_NONSEPARATE_BOOKMAKER_CONSENSUS",
        "compared_to_primary_model":False,
        "automatic_replacement_of_main_market":False,
        "market_is_executable":False,"real_money_recommendations":False,
        "source_licence_verified_for_derived_research":True,
        "production_recommendations":"DISABLED",
        "warning":"BSD免費版只係市場共識、唔係真正可買賠率；配對另行評分，唔自動替換主模型。",
    }
    if not isinstance(latest,dict) or not isinstance(shadow,dict):
        return result
    try:
        captured=validate(latest,now=now)
    except (ValueError,TypeError,KeyError,OverflowError):
        result["reason"]="INVALID_VENDOR_EVIDENCE"
        return result
    result["source_state"]=latest["status"]
    result["last_source_checked_utc"]=captured.isoformat()
    result["source_age_hours"]=round((now-captured).total_seconds()/3600,1)
    result["six_league_fixture_count"]=latest["fixture_count"]
    result["market_event_count"]=latest["market_count"]
    if latest["status"]!="RESEARCH_ONLY":
        result["reason"]="NO_FREE_1X2_CONSENSUS_AVAILABLE"
        return result
    if (not -timedelta(minutes=5)<=now-captured<=timedelta(hours=12)
            or shadow.get("status")!="SHADOW_ONLY"
            or shadow.get("production_recommendations")!="DISABLED"):
        result["reason"]="OUT_OF_TIME_OR_MODEL_HOLD"
        return result
    market={"status":"RESEARCH_ONLY",
            "as_of_utc":latest["captured_utc"],
            "events":[{key:v for key,v in r.items()
                if key not in ("market_source","raw_prices_published","not_executable_odds")}
                for r in latest["events"]],
            "production_recommendations":"DISABLED"}
    evidence=pair(shadow,market)
    result["time_valid_shadow_pairs"]=evidence["matched_count"]
    result["compared_to_primary_model"]=True
    result["status"]="RESEARCH_ONLY" if evidence["matched_count"] else "HOLD"
    result["reason"]=("SEPARATE_ALTERNATIVE_SHADOW_MARKET_COMPARISON"
                      if evidence["matched_count"] else "NO_PRE_MATCH_IDENTITY_PAIRS")
    return result

def publish(site,source_file="sources/bsd_market_latest.json",status_file="sources/bsd_status_latest.json"):
    site=Path(site)
    source=None
    for location in (source_file,status_file):
        path=Path(location)
        if path.is_file():
            try:
                obj=json.loads(path.read_text(encoding="utf-8"))
                if obj.get("status")=="RESEARCH_ONLY":
                    source=obj
                    break
                if source is None:source=obj
            except (ValueError,UnicodeError,OSError,AttributeError):continue
    shadow=json.loads((site/"shadow.json").read_text(encoding="utf-8"))
    result=build(shadow,source)
    (site/"bsd_backup.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":result["status"],"source_state":result["source_state"],
        "time_valid_shadow_pairs":result["time_valid_shadow_pairs"],
        "production_recommendations":"DISABLED"},ensure_ascii=False))
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--site",default="app/site")
    p.add_argument("--input",default="sources/bsd_market_latest.json")
    p.add_argument("--status",default="sources/bsd_status_latest.json")
    v=p.parse_args()
    publish(v.site,v.input,v.status)
