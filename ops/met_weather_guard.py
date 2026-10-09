"""Fail-closed, source-attributed MET Norway weather publication guard."""
import argparse
import json
import math
from datetime import datetime,timezone,timedelta
from pathlib import Path
from met_weather import CITY_POINTS,SCHEMA,PROVIDER,LICENSE,MAX_CITY_CALLS,MAX_FORECAST_ENTRIES,utc

VALID={"HOLD","PARTIAL_COVERAGE","RESEARCH_ONLY"}
CITY_STATES={"HOLD","FORECAST_AVAILABLE","ACCESS_DENIED","RATE_LIMITED","HTTP_UNAVAILABLE","INVALID_OR_UNAVAILABLE","NETWORK_UNAVAILABLE"}


def validate(d,*,now=None):
    now=now or datetime.now(timezone.utc)
    if not isinstance(d,dict):
        raise ValueError("INVALID_WEATHER_REPORT")
    if (d.get("schema")!=SCHEMA or d.get("provider")!=PROVIDER
            or d.get("status") not in VALID
            or d.get("production_recommendations")!="DISABLED"
            or d.get("current_executable_bookmaker_odds") is not False
            or d.get("source_data_used_in_model") is not False
            or d.get("verified_betting_advantage") is not False
            or d.get("licence_attribution_required") is not True
            or d.get("license_url")!=LICENSE
            or d.get("location_accuracy")!="APPROXIMATE_CITY_CENTRE_NOT_STADIUM"
            or not d.get("attribution")):
        raise ValueError("UNSAFE_WEATHER_PROVENANCE")
    captured=utc(d["captured_utc"])
    if not -timedelta(minutes=5)<=now-captured<=timedelta(days=5):
        raise ValueError("BAD_WEATHER_CAPTURE_TIME")
    cities=d.get("cities")
    if not isinstance(cities,list) or len(cities)!=len(CITY_POINTS):
        raise ValueError("INVALID_WEATHER_CITY_COUNT")
    if (type(d.get("request_count")) is not int
            or d["request_count"]<0 or d["request_count"]>MAX_CITY_CALLS
            or d.get("max_requests_per_daily_run")!=MAX_CITY_CALLS):
        raise ValueError("WEATHER_API_REQUEST_BUDGET_EXCEEDED")
    good=0
    for row,config in zip(cities,CITY_POINTS):
        id_,name,lat,lon,clubs=config
        if (not isinstance(row,dict)
                or row.get("city")!=id_
                or row.get("display")!=name
                or row.get("latitude")!=lat or row.get("longitude")!=lon
                or row.get("bundesliga_club_ids")!=list(clubs)
                or row.get("status") not in CITY_STATES
                or not isinstance(row.get("hourly_samples"),list)
                or len(row["hourly_samples"])>MAX_FORECAST_ENTRIES):
            raise ValueError("WEATHER_CITY_IDENTITY_INVALID")
        if row["status"]!="FORECAST_AVAILABLE":
            if row["hourly_samples"] or row.get("model_updated_utc") is not None:
                raise ValueError("WEATHER_FAILED_CITY_HAS_SYNTHETIC_DATA")
            continue
        good+=1
        updated=utc(row["model_updated_utc"])
        if not -timedelta(minutes=5)<=captured-updated<=timedelta(hours=24):
            raise ValueError("WEATHER_FORECAST_ISSUE_TIME_INVALID")
        if not row["hourly_samples"]:
            raise ValueError("WEATHER_NO_FORECAST_POINTS")
        previous=None
        for point in row["hourly_samples"]:
            if not isinstance(point,dict) or set(point)!={
                "valid_utc","temperature_c","wind_speed_m_s","precipitation_next_1h_mm"
            }:
                raise ValueError("UNEXPECTED_WEATHER_METADATA")
            moment=utc(point["valid_utc"])
            if (moment<=previous if previous is not None else False):
                raise ValueError("OUT_OF_ORDER_WEATHER_FORECAST")
            previous=moment
            if not captured-timedelta(minutes=15)<=moment<=captured+timedelta(days=9):
                raise ValueError("WEATHER_FORECAST_OUT_OF_WINDOW")
            for name,minval,maxval in (
                ("temperature_c",-70,60),("wind_speed_m_s",0,100),
                ("precipitation_next_1h_mm",0,500)):
                v=point[name]
                if v is not None and (type(v) not in (int,float)
                                       or not math.isfinite(v) or not minval<=v<=maxval):
                    raise ValueError("WEATHER_VALUE_RANGE_INVALID")
            if point["temperature_c"] is None or point["wind_speed_m_s"] is None:
                raise ValueError("WEATHER_INCOMPLETE_POINT")
    if d["status"]=="RESEARCH_ONLY" and good!=len(cities):
        raise ValueError("FALSIFIED_WEATHER_FULL_COVERAGE")
    if d["status"]=="PARTIAL_COVERAGE" and not 0<good<len(cities):
        raise ValueError("FALSIFIED_WEATHER_PARTIAL_COVERAGE")
    if d["status"]=="HOLD" and good:
        raise ValueError("FALSIFIED_WEATHER_HOLD")
    return captured


def replace(incoming,old):
    t=validate(incoming)
    if old is None:
        return True
    o=validate(old)
    if t==o and incoming!=old:
        raise ValueError("WEATHER_CONFLICTING_SAME_CAPTURE")
    return t>o


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--previous",default="")
    p.add_argument("--decision",default="")
    args=p.parse_args()
    d=json.loads(Path(args.input).read_text(encoding="utf-8"))
    old=json.loads(Path(args.previous).read_text(encoding="utf-8")) if args.previous and Path(args.previous).is_file() else None
    should=replace(d,old)
    if args.decision:
        Path(args.decision).write_text(json.dumps({"replace":should})+"\n",encoding="utf-8")
    print(json.dumps({"valid_weather_context":True,"replace":should,"city_count":len(d["cities"]),
                      "production_recommendations":"DISABLED"}))


if __name__=="__main__":
    main()
