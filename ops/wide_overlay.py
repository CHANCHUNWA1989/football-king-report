"""Safe static-phone summary of optional worldwide and lower-league free feeds.

Current vs archived coverage is always explicit; archived matches are never
backdated into today's forecasts and data do not include executable odds.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from wide_source_guard import verify
from wide_sources import NOW_LEAGUES, HISTORY_LEAGUES, GERMAN_LEAGUES

LEAGUES = NOW_LEAGUES + HISTORY_LEAGUES + GERMAN_LEAGUES


def build(record=None, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    result = {
        "schema": "football-king-global-free-league-site-v1",
        "generated_utc": now.isoformat(),
        "status": "HOLD", "reason": "AWAITING_FIRST_NO_KEY_DOWNLOAD",
        "source_as_of_utc": None,
        "provider_names": ["openfootball_json", "openligadb"],
        "source_count": 2, "league_file_total": len(LEAGUES),
        "successful_league_files": 0,
        "current_season_file_successes": 0,
        "historical_only_file_successes": 0,
        "precise_german_utc_kickoffs_observed": 0,
        "provider_market_odds_available": False,
        "training_evidence_validated": False,
        "historic_data_can_be_presented_as_live": False,
        "provider_names_include_all_football_data_sources": False,
        "backup_policy": "PRECISE_OPENLIGA_UTC_SCHEDULE_ONLY",
        "backup_scheduled_fixtures": [],
        "production_recommendations": "DISABLED",
        "league_cards": [
            {"id":league,"name":name,"provider":source,
             "season_scope":"CURRENT_SEASON_FILE" if
             (source=="openfootball_json" and i<len(NOW_LEAGUES)) else
             ("ARCHIVED_SEASON_ONLY" if source=="openfootball_json" else
              "OPENLIGA_2026_SEASON_UNCONFIRMED"),
             "access_status":"NOT_YET_COLLECTED","records":0}
            for i,(league,name,key,source) in enumerate(
                [(a,b,c,"openfootball_json") for a,b,c in NOW_LEAGUES+HISTORY_LEAGUES] +
                [(a,b,c,"openligadb") for a,b,c in GERMAN_LEAGUES])
        ],
    }
    if not isinstance(record,dict):
        return result
    try:
        origin=verify(record,clock=now)
        age=(now-origin).total_seconds()/3600
        if not -0.1 <= age <= 36:
            result["reason"]="GLOBAL_SOURCE_EXPIRED_OR_CLOCK_INVALID"
            return result
    except (ValueError,TypeError,KeyError,OverflowError):
        result["reason"]="GLOBAL_SOURCE_DATA_FAILED_SAFETY_CHECK"
        return result
    # This is an actionable READ-ONLY schedule fallback for German smaller
    # leagues when a primary fixture feed fails. Never feed it to the model
    # or convert these dates into bets without separate evidence.
    candidates=[]
    seen=set()
    for entry in record.get("league_coverage", []):
        if (not isinstance(entry,dict) or entry.get("provider")!="openligadb"
                or entry.get("access_status")!="FETCHED"):
            continue
        for game in entry.get("sample", [])[:3]:
            if not isinstance(game,dict) or game.get("status")!="SCHEDULED":
                continue
            try:
                kickoff=datetime.fromisoformat(game["kickoff_utc"].replace("Z","+00:00"))
                if kickoff.tzinfo is None or not (
                        now+timedelta(minutes=60)
                        <= kickoff.astimezone(timezone.utc)
                        <= now+__import__("datetime").timedelta(days=14)):
                    continue
                key=(entry["league"],str(game.get("provider_event_id","")))
                if key in seen or not key[1]:
                    continue
                seen.add(key)
                candidates.append({
                    "league":entry["league"],
                    "home":str(game["home"])[:100],"away":str(game["away"])[:100],
                    "kickoff_utc":kickoff.astimezone(timezone.utc).isoformat(),
                    "source":"openligadb",
                    "backup_for_schedule_only":True,
                    "market_confirmed":False,
                    "betting_recommendation":False,
                    "production_recommendations":"DISABLED",
                })
            except (TypeError,ValueError,KeyError,OverflowError,AttributeError):
                continue
    candidates.sort(key=lambda e:(e["kickoff_utc"],e["league"]))
    result["backup_scheduled_fixtures"]=candidates[:9]
    result.update({
        "status":"RESEARCH_ONLY", "reason":"NO_KEY_COVERAGE_NOT_ODDS",
        "source_as_of_utc":origin.isoformat(),
        "successful_league_files":record["successful_league_files"],
        "current_season_file_successes":record["current_season_file_successes"],
        "historical_only_file_successes":record["historical_only_file_successes"],
        "precise_german_utc_kickoffs_observed":sum(
            item.get("precise_utc_kickoffs_confirmed",0)
            for item in record["league_coverage"]
            if item["provider"]=="openligadb" and item["access_status"]=="FETCHED"),
        "league_cards":[{
            "id":item["league"],"name":item["name_zh"],
            "provider":item["provider"],
            "season_scope":item["season_scope"],
            "access_status":item["access_status"],
            "records":item["records"],
            "reported_ft_scores_unverified":item["reported_ft_scores_unverified"],
            "precise_utc_kickoffs_confirmed":item.get("precise_utc_kickoffs_confirmed",0),
            "historical_only":item["season_scope"]=="ARCHIVED_SEASON_ONLY",
            "free_source_status_only":True
        } for item in record["league_coverage"]],
    })
    return result


def publish(site, data_file="sources/wide_latest.json"):
    site=Path(site)
    source=None
    candidate=Path(data_file)
    if candidate.is_file():
        try:
            source=json.loads(candidate.read_text(encoding="utf-8"))
        except (ValueError,UnicodeError,OSError):
            source=None
    payload=build(source)
    (site/"wide_leagues.json").write_text(
        json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":payload["status"],"source_count":payload["source_count"],
        "catalogued_league_files":payload["league_file_total"],
        "fetched":payload["successful_league_files"],
        "current":payload["current_season_file_successes"],
        "archived":payload["historical_only_file_successes"],
        "production_recommendations":"DISABLED"
    },ensure_ascii=False))
    return payload


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--site",default="app/site")
    p.add_argument("--input",default="sources/wide_latest.json")
    args=p.parse_args()
    publish(args.site,args.input)
