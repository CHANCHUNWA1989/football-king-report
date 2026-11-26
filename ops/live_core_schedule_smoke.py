"""One no-key public schedule smoke; no raw rows, prices or forecast admission."""
import json
from live_core_same_batch_collection import clock,schedule_diagnostic
from secondary_sources import fetch,SD_BD
def probe(*,fetcher=fetch,now=clock):
    league="bundesliga"
    started=now()
    body,state=fetcher("thesportsdb",f"https://www.thesportsdb.com/api/v1/json/123/eventsnextleague.php?id={SD_BD[league]}",{})
    finished=now()
    accepted=0;diagnostic=None
    if state=="OK":
        try:
            rows,diagnostic=schedule_diagnostic(body,league,finished);accepted=len(rows)
        except (ValueError,TypeError,KeyError,OverflowError):state="INVALID_DATA"
    if state not in ("OK","RATE_LIMITED","KEY_REJECTED","PLAN_OR_LEAGUE_RESTRICTED","HTTP_ERROR","NETWORK_ERROR","INVALID_DATA"):state="OTHER_ERROR"
    return {"league":league,"requests_attempted":1,"response_status":state,
            "local_scheduled_rows":accepted,"schedule_diagnostic":diagnostic,"started_utc":started.isoformat(),
            "received_utc":finished.isoformat(),"native_clock_attested":False,
            "market_collection_attempted":False,"source_identity_authenticated":False,
            "authenticated_forward_samples":0,"production_recommendations":"DISABLED","status":"HOLD"}
if __name__=="__main__":print(json.dumps(probe(),sort_keys=True,allow_nan=False))
