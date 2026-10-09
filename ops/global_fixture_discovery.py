"""Global fixture discovery from an unverified public provider; research only.

This adapter is isolated from model training, markets and betting. Provider
coverage is measured from actual returned rows, never inferred from marketing.
"""
import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE = "https://openfootapi.com/v1/matches?date="
SCHEMA = "football-king-global-fixture-discovery-v1"
MAX_BYTES = 2_000_000
MAX_ROWS = 5000
MAX_DAYS = 3

def _clock(s):
    if not isinstance(s,str):
        raise ValueError("INVALID_KICKOFF")
    x=datetime.fromisoformat(s.replace("Z","+00:00"))
    if x.tzinfo is None:
        raise ValueError("UNZONED_KICKOFF")
    return x.astimezone(timezone.utc)

def parse(payload, day):
    if not isinstance(payload,dict):
        raise ValueError("INVALID_RESPONSE")
    rows=payload.get("data")
    if isinstance(rows,dict):
        rows=rows.get("matches")
    if not isinstance(rows,list) or len(rows)>MAX_ROWS:
        raise ValueError("INVALID_MATCH_ARRAY")
    out=[]
    seen=set()
    rejected=0
    for row in rows:
        if not isinstance(row,dict):
            rejected+=1
            continue
        league=row.get("competition") or row.get("league")
        if isinstance(league,dict):
            league=league.get("name")
        home=row.get("home_team") or row.get("homeTeam") or row.get("home")
        away=row.get("away_team") or row.get("awayTeam") or row.get("away")
        if isinstance(home,dict):
            home=home.get("name")
        if isinstance(away,dict):
            away=away.get("name")
        raw_id=row.get("id") or row.get("match_id")
        raw_ko=row.get("kickoff_utc") or row.get("kickoff") or row.get("utcDate")
        try:
            ko=_clock(raw_ko)
        except (ValueError,TypeError,OverflowError):
            rejected+=1
            continue
        if not (type(raw_id) in (int,str) and str(raw_id).strip()
                and all(isinstance(v,str) and 0<len(v.strip())<=120
                        for v in (league,home,away))
                and home.casefold()!=away.casefold()
                and ko.date().isoformat()==day):
            rejected+=1
            continue
        key=str(raw_id)
        if key in seen:
            # Fail closed on duplicate identities instead of silently picking
            # one provider event with potentially contradictory details.
            raise ValueError("DUPLICATE_PROVIDER_MATCH_ID")
        seen.add(key)
        out.append({"source":"openfootapi_unverified","provider_match_id":key,
                    "competition":league,"home":home,"away":away,
                    "kickoff_utc":ko.isoformat(),
                    "independently_confirmed":False,
                    "market_odds_available":False,
                    "qualifies_for_recommendation":False})
    return out,rejected

def fetch(day, *, loader=None):
    if not isinstance(day,str) or date.fromisoformat(day).isoformat()!=day:
        raise ValueError("INVALID_DAY")
    url=BASE+day
    if loader is not None:
        return loader(url)
    req=Request(url,headers={"Accept":"application/json",
                              "User-Agent":"FootballKingGlobalResearch/1.0"})
    with urlopen(req,timeout=12) as response:
        if response.geturl()!=url:
            raise ValueError("UNEXPECTED_REDIRECT")
        raw=response.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:
        raise ValueError("RESPONSE_TOO_LARGE")
    return json.loads(raw)

def collect(now=None, *, loader=None, days=2):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None or type(days) is not int or not 1<=days<=MAX_DAYS:
        raise ValueError("INVALID_COLLECTION_POLICY")
    today=now.astimezone(timezone.utc).date()
    all_matches=[]
    failures=[]
    rejected=0
    for offset in range(days):
        day=(today+timedelta(days=offset)).isoformat()
        try:
            matches,ignored=parse(fetch(day,loader=loader),day)
            all_matches.extend(matches)
            rejected+=ignored
        except (HTTPError,URLError,TimeoutError,OSError,ValueError,KeyError,
                TypeError,json.JSONDecodeError) as err:
            failures.append({"date":day,"reason":type(err).__name__})
    # No fabricated source availability: count only accepted returned rows.
    leagues=sorted({m["competition"] for m in all_matches})
    return {"schema":SCHEMA,"as_of_utc":now.astimezone(timezone.utc).isoformat(),
            "status":"RESEARCH_ONLY" if all_matches else "HOLD",
            "provider":"openfootapi_unverified",
            "provider_live_access_confirmed":loader is None and not failures and bool(all_matches),
            "provider_claimed_coverage_not_verified":True,
            "days_requested":days,"request_failures":failures,
            "rejected_rows":rejected,"fixture_count":len(all_matches),
            "observed_competition_count":len(leagues),
            "observed_competitions":leagues,
            "fixtures":all_matches,
            "market_odds_available":False,
            "model_probabilities_available":False,
            "independent_calibration_verified":False,
            "qualifies_for_betting":False,
            "production_recommendations":"DISABLED"}

def verify(doc):
    if not isinstance(doc,dict) or doc.get("schema")!=SCHEMA:
        raise ValueError("INVALID_GLOBAL_SCHEMA")
    if (doc.get("production_recommendations")!="DISABLED"
            or doc.get("qualifies_for_betting") is not False
            or any(doc.get(k) is not False for k in (
                "market_odds_available","model_probabilities_available",
                "independent_calibration_verified"))
            or doc.get("provider_claimed_coverage_not_verified") is not True):
        raise ValueError("UNSAFE_GLOBAL_PROVENANCE")
    rows=doc.get("fixtures")
    if not isinstance(rows,list) or len(rows)>MAX_ROWS*MAX_DAYS:
        raise ValueError("INVALID_GLOBAL_FIXTURES")
    if doc.get("fixture_count")!=len(rows):
        raise ValueError("INVALID_GLOBAL_FIXTURE_COUNT")
    ids=set()
    for row in rows:
        if not isinstance(row,dict) or row.get("source")!="openfootapi_unverified":
            raise ValueError("INVALID_GLOBAL_ROW")
        if (row.get("independently_confirmed") is not False
                or row.get("market_odds_available") is not False
                or row.get("qualifies_for_recommendation") is not False):
            raise ValueError("UNSAFE_GLOBAL_ROW")
        _clock(row.get("kickoff_utc"))
        ident=row.get("provider_match_id")
        if not isinstance(ident,str) or not ident or ident in ids:
            raise ValueError("DUPLICATE_GLOBAL_ID")
        ids.add(ident)
    leagues=sorted({row["competition"] for row in rows})
    if (doc.get("observed_competitions")!=leagues
            or doc.get("observed_competition_count")!=len(leagues)):
        raise ValueError("FABRICATED_GLOBAL_COVERAGE")
    return True

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",default="global-fixtures.json")
    a=p.parse_args()
    result=collect()
    verify(result)
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"observed_competitions":result["observed_competition_count"],"fixtures":result["fixture_count"],"failures":result["request_failures"]},ensure_ascii=False))

if __name__=="__main__":
    main()
