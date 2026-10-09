"""Fail-closed BSD free consensus research gate, no market merge without A/B."""
import argparse,json,math
from datetime import datetime,timedelta,timezone
from pathlib import Path
from bsd_free import SCHEMA,LICENSE,MAX_CALLS,MAX_MARKETS,stamp

STATUSES=("NOT_CONFIGURED","HOLD","RESEARCH_ONLY","NO_COMPARABLE_MARKET")
LEAGUES=("epl","championship","bundesliga","laliga","seriea","ligue1")
FIELDS={"league","source_event_id","home","away","kickoff_utc",
        "market_last_update_utc","p_home","p_draw","p_away",
        "market_source","raw_prices_published","not_executable_odds"}
def validate(data,*,now=None):
    now=now or datetime.now(timezone.utc)
    if not isinstance(data,dict):raise ValueError("BSD_INVALID_RESEARCH_OBJECT")
    if (data.get("schema")!=SCHEMA or data.get("provider")!="bzzoiro_sports_data"
            or data.get("status") not in STATUSES
            or data.get("license_url")!=LICENSE
            or data.get("production_recommendations")!="DISABLED"
            or data.get("free_tier_only") is not True
            or data.get("raw_quotes_published") is not False
            or data.get("licensed_per_bookmaker_prices_available") is not False
            or data.get("independently_verified_market_advantage") is not False
            or data.get("replaces_current_market_automatically") is not False):
        raise ValueError("BSD_UNSAFE_PROVENANCE")
    captured=stamp(data["captured_utc"])
    if not -timedelta(minutes=5)<=now-captured<=timedelta(days=5):
        raise ValueError("BSD_STALE_OR_FUTURE_CAPTURE")
    if (type(data.get("requests_attempted")) is not int
            or not 0<=data["requests_attempted"]<=MAX_CALLS
            or data.get("max_calls")!=MAX_CALLS):
        raise ValueError("BSD_UNBOUNDED_API_REQUESTS")
    if type(data.get("key_present")) is not bool:
        raise ValueError("BSD_MISLEADING_KEY_PRESENCE")
    for field in ("league_count","fixture_count","market_count"):
        value=data.get(field)
        if type(value) is not int or not 0<=value<=200:
            raise ValueError("BSD_INVALID_COUNTS")
    events=data.get("events")
    if (not isinstance(events,list) or len(events)>MAX_MARKETS
            or len(events)!=data["market_count"]):
        raise ValueError("BSD_MARKET_COUNT_MISMATCH")
    if events and data["status"]!="RESEARCH_ONLY":
        raise ValueError("BSD_UNQUALIFIED_MARKET_EXPOSURE")
    if data["status"]=="NOT_CONFIGURED" and (data["key_present"] or events or data["requests_attempted"]):
        raise ValueError("BSD_NOT_CONFIGURED_CANNOT_HAVE_MARKETS")
    seen=set()
    for row in events:
        if not isinstance(row,dict) or set(row)!=FIELDS:
            raise ValueError("BSD_UNAUTHORIZED_RAW_MARKET_FIELDS")
        if (row["league"] not in LEAGUES
                or row["market_source"]!="BSD_FREE_CONSENSUS_ONLY"
                or row["raw_prices_published"] is not False
                or row["not_executable_odds"] is not True
                or not isinstance(row["home"],str) or not row["home"]
                or not isinstance(row["away"],str) or not row["away"]
                or not row["source_event_id"]):
            raise ValueError("BSD_INVALID_MARKET_EVENT")
        ident=(row["league"],row["source_event_id"])
        if ident in seen:raise ValueError("BSD_DUPLICATE_FIXTURE")
        seen.add(ident)
        pt=[row["p_home"],row["p_draw"],row["p_away"]]
        if (not all(type(p) in (int,float) and math.isfinite(p) and 0<=p<=1 for p in pt)
                or abs(sum(pt)-1)>.001):
            raise ValueError("BSD_INVALID_PROBABILITIES")
        updated,kick=stamp(row["market_last_update_utc"]),stamp(row["kickoff_utc"])
        if (updated>captured+timedelta(minutes=5)
                or updated>=kick
                or kick<=captured+timedelta(minutes=10)):
            raise ValueError("BSD_MARKET_TIME_LEAKAGE")
    return captured

def should_replace(new,old):
    a=validate(new)
    if old is None:return True
    b=validate(old)
    if a==b and new!=old:
        raise ValueError("BSD_SAME_TIMESTAMP_CONFLICT")
    return a>b

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--previous",default="")
    p.add_argument("--decision",default="")
    args=p.parse_args()
    new=json.loads(Path(args.input).read_text(encoding="utf-8"))
    old=json.loads(Path(args.previous).read_text(encoding="utf-8")) if args.previous and Path(args.previous).is_file() else None
    replace=should_replace(new,old)
    if args.decision:
        Path(args.decision).write_text(json.dumps({"replace":replace})+"\n",encoding="utf-8")
    print(json.dumps({"valid":True,"replace":replace,"derived_markets":len(new["events"]),
        "status":new["status"],"production_recommendations":"DISABLED"}))
if __name__=="__main__":main()
