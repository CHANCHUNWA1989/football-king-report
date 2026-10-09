"""Zero-key, low-rate football standings and historical-event discovery.

Read-only research metadata from:
 * TheSportsDB V1 league tables (six core leagues; FREE limit five rows)
 * OpenLigaDB current Bundesliga 1/2/3 tables (same provider as existing fixtures)
 * Figshare public Wyscout 2017/18 soccer event dataset catalogue

NO historical snapshots are constructed retroactively. Current league table
is a display-time research status only, not a frozen past forecast feature.
No live bookmaker data, reforecast, raw provider rows or betting output.
"""
import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

SCHEMA = "football-king-free-football-depth-v1"
TSDB = "https://www.thesportsdb.com/api/v1/json/123/lookuptable.php"
OLDB = "https://api.openligadb.de/getbltable/"
FIG = "https://api.figshare.com/v2/collections/4415000/articles"
TSDB_LEAGUES = (("epl",4328),("championship",4329),("bundesliga",4331),
                ("laliga",4335),("seriea",4332),("ligue1",4334))
GERMAN_LEAGUES = (("bundesliga","bl1"),("bundesliga2","bl2"),
                  ("germany_liga3","bl3"))
TOTAL_BUDGET = len(TSDB_LEAGUES) + len(GERMAN_LEAGUES) + 1
MAX_BYTES = 800_000
AGENT = "FootballKingFreeCoverage/1.0 (+https://github.com/CHANCHUNWA1989/football-king-report)"
PROVENANCE = "RESEARCH_ONLY_NEVER_BETTING"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, url):
        raise ValueError("UNTRUSTED_REDIRECT")


def get_json(url, *, opener=None):
    """Whitelist exact public route patterns and parse up to 800kB."""
    import re
    if not (
        re.fullmatch(r"https://www\.thesportsdb\.com/api/v1/json/123/lookuptable\.php\?l=\d{4}&s=\d{4}-\d{4}",url)
        or re.fullmatch(r"https://api\.openligadb\.de/getbltable/bl[123]/\d{4}",url)
        or url == FIG + "?page_size=10"
    ):
        raise ValueError("OUT_OF_SCOPE_PUBLIC_API")
    requester = opener or build_opener(NoRedirect()).open
    req=Request(url,headers={"Accept":"application/json","User-Agent":AGENT})
    try:
        with requester(req,timeout=12) as response:
            body=response.read(MAX_BYTES+1)
        if len(body)>MAX_BYTES:
            return None, "BODY_TOO_LARGE"
        return json.loads(body.decode("utf-8")), "OK"
    except HTTPError as e:
        return None, ("RATE_LIMITED" if e.code==429 else
                      "ACCESS_RESTRICTED" if e.code in (401,403) else "HTTP_ERROR")
    except (URLError,TimeoutError,OSError):
        return None, "NETWORK_ERROR"
    except (UnicodeError,ValueError,TypeError,json.JSONDecodeError):
        return None, "BAD_API_RESPONSE"


def tsdb_rows(document, league_id):
    if not isinstance(document,dict):
        raise ValueError("BAD_LEAGUE_TABLE_SHAPE")
    # The free V1 response contains at most five positions.
    rows=document.get("table")
    if rows is None:
        return 0
    if not isinstance(rows,list) or len(rows)>5:
        raise ValueError("FREE_TABLE_LIMIT_EXCEEDED")
    names=set()
    for item in rows:
        if not isinstance(item,dict):
            continue
        name=item.get("strTeam")
        if (isinstance(name,str) and 0<len(name.strip())<=130
                and (item.get("idLeague") is None
                     or str(item["idLeague"])==str(league_id))):
            names.add(name.casefold().strip())
    return len(names)


def openliga_rows(document):
    if not isinstance(document,list) or len(document)>50:
        raise ValueError("BAD_GERMAN_TABLE_SHAPE")
    names=set()
    scored=0
    for item in document:
        if not isinstance(item,dict):
            continue
        team=item.get("teamInfo")
        if not isinstance(team,dict):
            continue
        name=team.get("teamName")
        if not isinstance(name,str) or not 0<len(name.strip())<=130:
            continue
        token=name.strip().casefold()
        if token in names:
            raise ValueError("DUPLICATE_GERMAN_TABLE_TEAM")
        names.add(token)
        if type(item.get("points")) is int and 0<=item["points"]<=160:
            scored+=1
    return len(names),scored


def figshare_rows(document):
    if not isinstance(document,list) or len(document)>10:
        raise ValueError("BAD_HISTORICAL_CATALOG")
    ids=set()
    for item in document:
        if not isinstance(item,dict):
            continue
        identity=item.get("id")
        title=item.get("title")
        if (type(identity) is int and identity>0
                and isinstance(title,str) and 0<len(title.strip())<=300):
            ids.add(identity)
    return len(ids)


def collect(*,now=None,requester=None,pause=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_CAPTURE_CLOCK")
    season=now.year if now.month>=7 else now.year-1
    season_text=f"{season}-{season+1}"
    plan=(
        [("thesportsdb_free_table",league,
          TSDB+"?"+urlencode({"l": ident,"s": season_text}),ident)
         for league,ident in TSDB_LEAGUES]
        + [("openligadb_table",league,OLDB+f"{short}/{season}",None)
           for league,short in GERMAN_LEAGUES]
        + [("figshare_wyscout_archive","historic_2017_18",FIG+"?page_size=10",None)]
    )
    if len(plan)!=TOTAL_BUDGET:
        raise ValueError("UNEXPECTED_SOURCE_REQUEST_COUNT")
    results=[]
    report={
        "schema":SCHEMA,"as_of_utc":now.isoformat(),
        "source_uses_current_season_not_sealed_past_forecast":True,
        "status":"HOLD","provenance":PROVENANCE,
        "requests_attempted":0,"budget_per_week":TOTAL_BUDGET,
        "providers":("thesportsdb_free_table","openligadb_table","figshare_wyscout_archive"),
        "six_core_leagues_research_targeted":len(TSDB_LEAGUES),
        "source_data_independently_verified":False,
        "full_six_league_standings_verified":False,
        "historical_archive_is_live":False,
        "historical_2017_18_events_not_2026_current":True,
        "original_provider_payload_redistributed":False,
        "current_team_probabilities_unchanged":True,
        "bookmaker_quotes_available":False,
        "production_recommendations":"DISABLED",
        "observations":results
    }
    exhausted=set()
    for name,league,url,league_id in plan:
        row={"provider":name,"league":league,"status":"HOLD",
             "valid_rows":0,"rankings_with_points":0,
             "reason":"UNKNOWN","raw_data_published":False}
        if name in exhausted:
            row.update(status="HOLD",reason="PROVIDER_RATE_LIMIT_STOP")
            results.append(row)
            continue
        if name=="thesportsdb_free_table" and report["requests_attempted"] and requester is None:
            # Pace six requests at <= 26/min; shared free API has 30/min cap.
            (pause or time.sleep)(2.35)
        report["requests_attempted"]+=1
        raw,status=get_json(url,opener=requester)
        if status!="OK":
            row["reason"]=status
            if status in ("RATE_LIMITED","ACCESS_RESTRICTED"):
                exhausted.add(name)
            results.append(row)
            continue
        try:
            if name=="thesportsdb_free_table":
                count=tsdb_rows(raw,league_id)
                row["valid_rows"]=count
                row["status"]="PARTIAL" if count else "HOLD"
                row["reason"]="FREE_TIER_AT_MOST_FIVE_STANDINGS_NOT_FULL_TABLE" if count else "NO_FEATURED_FREE_TABLE"
            elif name=="openligadb_table":
                teams,points=openliga_rows(raw)
                row["valid_rows"]=teams
                row["rankings_with_points"]=points
                row["status"]="PARTIAL" if teams else "HOLD"
                row["reason"]="LIVE_TABLE_NOT_POINT_IN_TIME_OR_INDEPENDENT" if teams else "EMPTY_GERMAN_TABLE"
            else:
                count=figshare_rows(raw)
                row["valid_rows"]=count
                row["status"]="PARTIAL" if count else "HOLD"
                row["reason"]="HISTORICAL_2017_18_EVENT_ARTICLE_CATALOG_ONLY" if count else "EMPTY_HISTORICAL_CATALOG"
        except (KeyError,TypeError,ValueError,OverflowError):
            row["reason"]="SOURCE_SCHEMA_NOT_VERIFIED"
        results.append(row)
    report["valid_sources"]=sum(x["status"]=="PARTIAL" for x in results)
    report["status"]="RESEARCH_ONLY" if report["valid_sources"] else "HOLD"
    return report


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--output",default="football-depth-audit.json")
    args=p.parse_args(argv)
    doc=collect()
    dest=Path(args.output)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":doc["status"],
                      "valid_sources":doc["valid_sources"],
                      "attempted":doc["requests_attempted"],
                      "by_source":{n:sum(x["status"]=="PARTIAL" for x in doc["observations"] if x["provider"]==n)
                                   for n in doc["providers"]},
                      "production_recommendations":"DISABLED"},ensure_ascii=False))


if __name__=="__main__":
    main()
