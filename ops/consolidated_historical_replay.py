"""Run both frozen historical studies from one digest-checked fetch per season."""
import json
from urllib.request import Request, build_opener
from live_core_multi_source import NoRedirect, LIMIT
import live_core_low_score_calibration as low
import live_core_halftime_dynamics as half

def run(fetch_bytes):
    raw = {season:fetch_bytes(season) for season in ("2020-21","2021-22")}
    result = {
        "low_score": low.report(*(low.parse(raw[s],s) for s in raw)),
        "halftime": half.report(*(half.parse(raw[s],s) for s in raw)),
        "source_pins": low.PINS, "historical_only": True,
        "production_recommendations": "DISABLED", "verified_forward_sample_credit": 0,
        "positive_ev_verified": False, "status": "HOLD"}
    return result

def fetch(season):
    if season not in low.PINS:
        raise ValueError("UNKNOWN_SEASON")
    url=f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/en.1.json"
    with build_opener(NoRedirect()).open(Request(url,headers={"User-Agent":"FootballKingResearch/1.0","Accept":"application/json"}),timeout=15) as res:
        if res.geturl()!=url or res.status!=200:
            raise ValueError("HTTP_SOURCE")
        raw=res.read(LIMIT+1)
    if len(raw)>LIMIT:
        raise ValueError("SIZE_LIMIT")
    return raw

if __name__=="__main__":
    print(json.dumps(run(fetch),sort_keys=True,allow_nan=False))
