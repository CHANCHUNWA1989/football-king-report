"""Read-only weather background for eligible German fixtures on iPhone.

Only matches a curatively mapped HOME CLUB with a city centre proxy, not a
verified match venue. No match recommendations, EV, probability adjustment,
player risk or bankroll calculation is derived from MET Norway forecasts.
"""
import argparse
import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
from met_weather_guard import validate
from met_weather import CITY_POINTS,LICENSE,ATTRIBUTION
from team_identity import team_id

SCHEMA="football-king-research-weather-overlay-v1"


def utc(value):
    x=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if x.tzinfo is None:
        raise ValueError("WEATHER_NO_TIMEZONE")
    return x.astimezone(timezone.utc)


def build(shadow,source,*,now=None):
    now=now or datetime.now(timezone.utc)
    output={
        "schema":SCHEMA,"status":"HOLD",
        "generated_utc":now.isoformat(),
        "reason":"OPTIONAL_WEATHER_SOURCE_UNAVAILABLE",
        "data_source":"MET Norway Locationforecast 2.0",
        "data_license":LICENSE,"attribution":ATTRIBUTION,
        "source_is_city_centre_not_venue":True,
        "match_venue_confirmed":False,
        "included_as_predictive_model_feature":False,
        "weather_impact_on_win_probability_validated":False,
        "market_odds_source":False,
        "production_recommendations":"DISABLED",
        "forecasts":[],
        "available_cities":0,
    }
    if not isinstance(source,dict) or not isinstance(shadow,dict):
        return output
    try:
        captured=validate(source,now=now)
        if not -timedelta(minutes=5)<=now-captured<=timedelta(hours=36):
            output["reason"]="WEATHER_SOURCE_STALE"
            return output
    except (ValueError,TypeError,KeyError,OverflowError):
        output["reason"]="WEATHER_SOURCE_INVALID"
        return output
    if (shadow.get("status")!="SHADOW_ONLY"
            or shadow.get("production_recommendations")!="DISABLED"
            or not isinstance(shadow.get("predictions"),list)):
        output["reason"]="NO_VALID_SHADOW_FORECAST"
        return output
    map_club={club:city for city in source["cities"] if city["status"]=="FORECAST_AVAILABLE"
              for club in city["bundesliga_club_ids"]}
    output["available_cities"]=len({city["city"] for city in map_club.values()})
    observations=[]
    for row in shadow["predictions"]:
        if not isinstance(row,dict) or row.get("league")!="bundesliga":
            continue
        try:
            home_id=team_id("bundesliga",row["home"])
            city=map_club.get(home_id)
            if city is None:
                continue
            kickoff=utc(row["kickoff_utc"])
            pred=utc(row["prediction_utc"])
            if not (pred<=now+timedelta(minutes=5)
                    and now+timedelta(minutes=60)<kickoff<now+timedelta(days=8)):
                continue
            nearest=None
            for data in city["hourly_samples"]:
                moment=utc(data["valid_utc"])
                lag=abs((moment-kickoff).total_seconds())
                if nearest is None or lag<nearest[0]:
                    nearest=(lag,data)
            if nearest is None or nearest[0]>2*3600:
                continue
            d=nearest[1]
            if any(type(d[k]) not in (int,float) for k in
                   ("temperature_c","wind_speed_m_s")):
                continue
            observations.append({
                "league":"bundesliga",
                "home":row["home"][:100],"away":row["away"][:100],
                "city":city["city"],"city_display":city["display"],
                "kickoff_utc":kickoff.isoformat(),
                "forecast_valid_utc":d["valid_utc"],
                "forecast_issue_utc":city["model_updated_utc"],
                "air_temperature_c":d["temperature_c"],
                "wind_speed_m_s":d["wind_speed_m_s"],
                "precipitation_next_1h_mm":d["precipitation_next_1h_mm"],
                "geography":"CITY_CENTRE_PROXY_NOT_VERIFIED_STADIUM",
                "used_in_model":False,
                "production_recommendations":"DISABLED",
            })
        except (ValueError,TypeError,KeyError,OverflowError):
            continue
    observations.sort(key=lambda r:(r["kickoff_utc"],r["home"]))
    output["forecasts"]=observations[:12]
    output["status"]="RESEARCH_ONLY" if output["available_cities"] else "HOLD"
    output["reason"]=("CITY_PROXY_RESEARCH_ONLY" if output["available_cities"]
                      else "NO_VALID_CITY_FORECAST")
    return output


def publish(site,source_file="sources/weather_latest.json"):
    site=Path(site)
    source=None
    path=Path(source_file)
    if path.is_file():
        try:source=json.loads(path.read_text(encoding="utf-8"))
        except (ValueError,UnicodeError,OSError):pass
    shadow=json.loads((site/"shadow.json").read_text(encoding="utf-8"))
    result=build(shadow,source)
    (site/"weather_context.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"available_cities":result["available_cities"],
                      "matched_fixtures":len(result["forecasts"]),
                      "production_recommendations":"DISABLED"},ensure_ascii=False))
    return result


if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--site",default="app/site")
    a.add_argument("--input",default="sources/weather_latest.json")
    p=a.parse_args()
    publish(p.site,p.input)
