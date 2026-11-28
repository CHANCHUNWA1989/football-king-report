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
        # The documented v1 response exposes a stable competitionId, not
        # necessarily a human-readable league name. Preserve the opaque ID
        # rather than inventing a name or fuzzy-matching a league.
        if "competitionId" in row:
            ident=row["competitionId"]
            if (not isinstance(ident,str) or not ident.startswith("comp_")
                    or not 5<len(ident)<=120 or not all(c.isascii() and (c.isalnum() or c in "_-") for c in ident)):
                rejected+=1
                continue
            league=ident
        home=row.get("home_team") or row.get("homeTeam") or row.get("home")
        away=row.get("away_team") or row.get("awayTeam") or row.get("away")
        if isinstance(home,dict):
            home=home.get("name")
        if isinstance(away,dict):
            away=away.get("name")
        raw_id=row.get("id") or row.get("match_id")
        try:
            clocks=[_clock(row[key]) for key in ("kickoffAt","kickoff_utc","kickoff","utcDate")
                    if key in row and row[key] is not None]
            if not clocks or any(value!=clocks[0] for value in clocks):
                raise ValueError("MISSING_OR_CONFLICTING_KICKOFF")
            ko=clocks[0]
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
    seen_global=set()
    rejected=0
    stopped=False
    for offset in range(days):
        day=(today+timedelta(days=offset)).isoformat()
        if stopped:
            failures.append({"date":day,"reason":"SKIPPED_PROVIDER_ACCESS_OR_RATE_LIMIT"})
            continue
        try:
            matches,ignored=parse(fetch(day,loader=loader),day)
            duplicate_ids={m["provider_match_id"] for m in matches}&seen_global
            if duplicate_ids:
                raise ValueError("DUPLICATE_CROSS_DAY_PROVIDER_ID")
            seen_global.update(m["provider_match_id"] for m in matches)
            all_matches.extend(matches)
            rejected+=ignored
        except HTTPError as err:
            # Record only the bounded numeric status, never body, headers,
            # URL, token or exception message. Do not retry access denial or
            # rate limits on another date in the same collection.
            code=err.code
            if type(code) is int and 400<=code<=599:
                failures.append({"date":day,"reason":"HTTPError","http_status":code})
                stopped=code in (401,402,403,429)
            else:
                failures.append({"date":day,"reason":"HTTPError"})
        except (URLError,TimeoutError,OSError,ValueError,KeyError,
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
    if (doc.get("status") not in ("HOLD","RESEARCH_ONLY")
            or doc.get("provider")!="openfootapi_unverified"
            or type(doc.get("days_requested")) is not int
            or not 1<=doc["days_requested"]<=MAX_DAYS
            or not isinstance(doc.get("request_failures"),list)
            or len(doc["request_failures"])>doc["days_requested"]
            or type(doc.get("rejected_rows")) is not int
            or doc["rejected_rows"]<0):
        raise ValueError("INVALID_GLOBAL_AUDIT")
    asof=_clock(doc.get("as_of_utc"))
    requested=[(asof.date()+timedelta(days=i)).isoformat()
               for i in range(doc["days_requested"])]
    failure_dates=[]
    stop_day=None
    # Older sealed reports lack the optional numeric status; retain compatibility.
    for failure in doc["request_failures"]:
        if (not isinstance(failure,dict)
                or set(failure)-{"date","reason","http_status"}
                or not isinstance(failure.get("date"),str)
                or not isinstance(failure.get("reason"),str)):
            raise ValueError("INVALID_GLOBAL_FAILURE")
        if "http_status" in failure and (failure["reason"]!="HTTPError"
                or type(failure["http_status"]) is not int
                or not 400<=failure["http_status"]<=599):
            raise ValueError("INVALID_GLOBAL_HTTP_STATUS")
        day=failure["date"]
        if day not in requested or (failure_dates and day<=failure_dates[-1]):
            raise ValueError("INVALID_GLOBAL_FAILURE_DATE")
        failure_dates.append(day)
        skipped=failure["reason"]=="SKIPPED_PROVIDER_ACCESS_OR_RATE_LIMIT"
        if skipped != (stop_day is not None):
            raise ValueError("INVALID_GLOBAL_STOP_SEQUENCE")
        if failure.get("http_status") in (401,402,403,429):
            stop_day=day
    if stop_day is not None and any(d not in failure_dates
                                    for d in requested if d>stop_day):
        raise ValueError("INVALID_GLOBAL_STOP_SEQUENCE")
    rows=doc.get("fixtures")
    if not isinstance(rows,list) or len(rows)>MAX_ROWS*MAX_DAYS:
        raise ValueError("INVALID_GLOBAL_FIXTURES")
    live=doc.get("provider_live_access_confirmed")
    if type(live) is not bool or (live and (not rows or failure_dates)):
        raise ValueError("INCONSISTENT_GLOBAL_LIVE_ACCESS")
    if type(doc.get("fixture_count")) is not int or doc["fixture_count"]!=len(rows):
        raise ValueError("INVALID_GLOBAL_FIXTURE_COUNT")
    ids=set()
    for row in rows:
        if not isinstance(row,dict) or row.get("source")!="openfootapi_unverified":
            raise ValueError("INVALID_GLOBAL_ROW")
        if (row.get("independently_confirmed") is not False
                or row.get("market_odds_available") is not False
                or row.get("qualifies_for_recommendation") is not False):
            raise ValueError("UNSAFE_GLOBAL_ROW")
        ko=_clock(row.get("kickoff_utc"))
        if ko.date().isoformat() in failure_dates:
            raise ValueError("GLOBAL_FIXTURE_ON_FAILED_DAY")
        if ko.date().isoformat() not in requested:
            raise ValueError("OUT_OF_WINDOW_GLOBAL_KICKOFF")
        if (not all(isinstance(row.get(k),str) and 0<len(row[k].strip())<=120
                    for k in ("competition","home","away"))
                or row["home"].casefold()==row["away"].casefold()):
            raise ValueError("INVALID_GLOBAL_TEAM_IDENTITY")
        ident=row.get("provider_match_id")
        if not isinstance(ident,str) or not ident or ident in ids:
            raise ValueError("DUPLICATE_GLOBAL_ID")
        ids.add(ident)
    if doc["status"]!=("RESEARCH_ONLY" if rows else "HOLD"):
        raise ValueError("FABRICATED_GLOBAL_STATUS")
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
