"""Read-only exact archived Asia connector readiness. No market price inference."""
import hashlib
import json
import subprocess
from datetime import datetime
from research_strict_json import unique_object,reject_constant
PIN="79e691c61b69315dfcf9bcfa22d2dfe4714acd9d"
def inspect(raw):
    if type(raw) is not bytes or not 0<len(raw)<=2_000_000:
        raise ValueError("SIZE")
    if hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()!=PIN:
        raise ValueError("PIN_CHANGED")
    d=json.loads(raw.decode(),object_pairs_hook=unique_object,parse_constant=reject_constant)
    if d["schema"]!="football-king-asia-optional-connectors-v1" or d["production_recommendations"]!="DISABLED" or any(d[k] is not False for k in ("model_inputs_changed","market_odds_changed","verified_betting_advantage")):
        raise ValueError("UNSAFE_CAPTURE")
    stamp=datetime.fromisoformat(d["collected_utc"])
    if stamp.tzinfo is None:raise ValueError("UNZONED")
    w,k=d["open_meteo"],d["kleague"]
    if (type(w["requests_attempted"]) is not int or not 0<=w["requests_attempted"]<=100
            or type(k["requests_attempted"]) is not int or not 0<=k["requests_attempted"]<=100
            or any(type(x) is not bool for x in (w["upstream_issue_time_verified"],k["configured"],k["current_fixtures_verified"],k["odds_available"]))):
        raise ValueError("BAD_SOURCE_METADATA")
    return {"capture_blob":PIN,"collected_utc":d["collected_utc"],
            "weather_requests":w["requests_attempted"],"weather_issue_time_verified":w["upstream_issue_time_verified"],
            "kleague_configured":k["configured"],"kleague_requests":k["requests_attempted"],
            "kleague_fixture_verification_claim":k["current_fixtures_verified"],"kleague_odds_available_claim":k["odds_available"],
            "authenticated_market_quotes":0,"positive_ev_verified":False,
            "production_recommendations":"DISABLED","status":"HOLD"}
if __name__=="__main__":
    print(json.dumps(inspect(subprocess.check_output(["git","cat-file","blob",PIN],timeout=10)),sort_keys=True,allow_nan=False))
