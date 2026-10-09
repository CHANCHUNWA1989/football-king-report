"""MET Norway City-centre forecast context: free, credited, never a betting signal.

Uses six approximate German CITY CENTRES (not football stadium positions),
read-only global Locationforecast 2.0 from the Norwegian Meteorological
Institute under CC BY 4.0. All queries are credential-free; once per day.
No venue-level, present-match, calibration or winning-probability claims.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlencode

SCHEMA="football-king-metno-city-weather-v1"
PROVIDER="met_norway_locationforecast"
BASE="https://api.met.no/weatherapi/locationforecast/2.0/compact"
USER_AGENT="FootballKingResearch/1.0 (+https://github.com/CHANCHUNWA1989/football-king-report)"
LICENSE="https://creativecommons.org/licenses/by/4.0/"
ATTRIBUTION="Weather forecast data: Norwegian Meteorological Institute (MET Norway), CC BY 4.0"
# Coordinates are approximate CITY CENTRES, not stadiums or neutral-ground venues.
# Only these well-established Bundesliga club-city identities are eligible.
CITY_POINTS=(
    ("munich", "慕尼黑市中心", 48.137, 11.576, ("bayernmunchen",)),
    ("dortmund", "多蒙特市中心", 51.514, 7.466, ("borussiadortmund",)),
    ("cologne", "科隆市中心", 50.938, 6.959, ("fckoln",)),
    ("freiburg", "弗賴堡市中心", 47.998, 7.842, ("scfreiburg",)),
    ("leipzig", "萊比錫市中心", 51.340, 12.373, ("rbleipzig",)),
    ("frankfurt", "法蘭克福市中心", 50.111, 8.682, ("eintrachtfrankfurt",)),
)
MAX_RESPONSE=700_000
MAX_CITY_CALLS=len(CITY_POINTS)
MAX_FORECAST_ENTRIES=70


class StopRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("UNTRUSTED_WEATHER_REDIRECT")


def utc(value):
    if not isinstance(value, str) or not value:
        raise ValueError("INVALID_MET_TIME")
    d=datetime.fromisoformat(value.replace("Z","+00:00"))
    if d.tzinfo is None:
        raise ValueError("NO_UTC_IN_MET_TIME")
    return d.astimezone(timezone.utc)


def bounded(v, low, high):
    if type(v) not in (float,int) or not low <= v <= high:
        return None
    return round(float(v),2)


def extract_city(payload, now):
    if not isinstance(payload,dict):
        raise ValueError("MET_RESPONSE_NOT_OBJECT")
    prop=payload.get("properties")
    if not isinstance(prop,dict):
        raise ValueError("MET_PROPERTIES_ABSENT")
    meta=prop.get("meta") or {}
    updated=utc(meta["updated_at"])
    if not -timedelta(minutes=5) <= now-updated <= timedelta(hours=24):
        raise ValueError("MET_FORECAST_ISSUE_TIME_BAD")
    items=prop.get("timeseries")
    if not isinstance(items,list) or not 1<=len(items)<=300:
        raise ValueError("MET_BAD_TIME_SERIES")
    series=[];seen=set()
    for item in items:
        if not isinstance(item,dict):
            continue
        at=utc(item["time"])
        if not now <= at <= now+timedelta(days=9):
            continue
        if at.hour % 3 != 0 or at.minute != 0:
            continue
        if at in seen:
            continue
        seen.add(at)
        data=item.get("data") or {}
        instant=(data.get("instant") or {}).get("details") or {}
        if not isinstance(instant,dict):
            continue
        temp=bounded(instant.get("air_temperature"),-70,60)
        wind=bounded(instant.get("wind_speed"),0,100)
        if temp is None or wind is None:
            continue
        rain=(data.get("next_1_hours") or {}).get("details") or {}
        precipitation=bounded(rain.get("precipitation_amount"),0,500)
        series.append({"valid_utc":at.isoformat(),"temperature_c":temp,
                       "wind_speed_m_s":wind,"precipitation_next_1h_mm":precipitation})
        if len(series)>=MAX_FORECAST_ENTRIES:
            break
    if not series:
        raise ValueError("MET_NO_FUTURE_HOURLY_OBSERVATIONS")
    series.sort(key=lambda r:r["valid_utc"])
    return updated.isoformat(),series


def request_city(lat,lon,*,client=None):
    url=BASE+"?"+urlencode({"lat":f"{lat:.3f}","lon":f"{lon:.3f}"})
    req=Request(url,headers={"User-Agent":USER_AGENT,"Accept":"application/json"})
    opener=client or build_opener(StopRedirect()).open
    with opener(req,timeout=14) as result:
        payload=result.read(MAX_RESPONSE+1)
        if len(payload)>MAX_RESPONSE:
            raise ValueError("MET_TOO_LARGE")
    return json.loads(payload.decode("utf-8"))


def collect(*,now=None,client=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    output={
        "schema":SCHEMA,"provider":PROVIDER,
        "captured_utc":now.isoformat(),"status":"HOLD",
        "request_count":0,"max_requests_per_daily_run":MAX_CITY_CALLS,
        "location_accuracy":"APPROXIMATE_CITY_CENTRE_NOT_STADIUM",
        "attribution":ATTRIBUTION,"license_url":LICENSE,
        "licence_attribution_required":True,
        "source_data_used_in_model":False,"verified_betting_advantage":False,
        "current_executable_bookmaker_odds":False,
        "production_recommendations":"DISABLED",
        "cities":[],"warnings":[],
    }
    for city,display,lat,lon,club_ids in CITY_POINTS:
        output["request_count"]+=1
        entry={"city":city,"display":display,"latitude":lat,"longitude":lon,
               "bundesliga_club_ids":list(club_ids),
               "status":"HOLD","model_updated_utc":None,
               "hourly_samples":[]}
        try:
            body=request_city(lat,lon,client=client)
            updated,rows=extract_city(body,now)
            entry["model_updated_utc"]=updated
            entry["hourly_samples"]=rows
            entry["status"]="FORECAST_AVAILABLE"
        except HTTPError as e:
            entry["status"]="ACCESS_DENIED" if e.code in (401,403) else "RATE_LIMITED" if e.code==429 else "HTTP_UNAVAILABLE"
        except (ValueError,TypeError,KeyError,UnicodeError,json.JSONDecodeError):
            entry["status"]="INVALID_OR_UNAVAILABLE"
        except (TimeoutError,URLError,OSError):
            entry["status"]="NETWORK_UNAVAILABLE"
        output["cities"].append(entry)
    found=sum(c["status"]=="FORECAST_AVAILABLE" for c in output["cities"])
    if found:
        output["status"]="PARTIAL_COVERAGE" if found<MAX_CITY_CALLS else "RESEARCH_ONLY"
    if found<MAX_CITY_CALLS:
        output["warnings"].append("SOME_CITIES_UNAVAILABLE_NOT_SYNTHESIZED")
    output["warnings"].append("CITY_CENTRE_PROXY_NOT_STADIUM_OR_LIVE_WEATHER")
    output["warnings"].append("WEATHER_HAS_NO_VALIDATED_EFFECT_ON_MODEL_WIN_PROBABILITY")
    return output


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",default="sources/weather_latest.json")
    args=p.parse_args()
    out=collect()
    destination=Path(args.output)
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":out["status"],"cities_with_forecast":sum(
        c["status"]=="FORECAST_AVAILABLE" for c in out["cities"]),
        "requests":out["request_count"],"production_recommendations":"DISABLED"}))


if __name__=="__main__":
    main()
