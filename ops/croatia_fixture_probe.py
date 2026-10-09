"""Optional, no-key Croatia Prva NL fixture *coverage* probe (not odds).

Tries official TheSportsDB V1 event title lookup and SportScore's public
date-scoped match list. Validates aliases and kickoff against a user-supplied
case, but will NEVER treat either as a verified bookmaker quote or a
complete source of live shots/xG. One call per source; failures => HOLD.
Public SportScore data display needs a visible link: https://sportscore.com/.
"""
import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

from live_market_research import example, utc

SCHEMA = "football-king-croatia-source-probe-v1"
TSDB = "https://www.thesportsdb.com/api/v1/json/123/searchevents.php"
SPORTSCORE = "https://sportscore.com/api/v1/fixtures/"
MAX_BYTES = 1_200_000
MAX_REQUESTS = 2
AGENT = "FootballKingCroatiaResearch/1.0 (+https://github.com/CHANCHUNWA1989/football-king-report)"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError("UNTRUSTED_REDIRECT")


def team_identity(value):
    if not isinstance(value,str):
        return None
    letters = "".join(ch for ch in unicodedata.normalize("NFKD", value.casefold())
                      if ch.isalnum() and not unicodedata.combining(ch))
    return {"sesvete":"sesvete","nksesvete":"sesvete",
            "jadranlp":"jadran_lp","jadranlukaploce":"jadran_lp",
            "nkjadranlukaploce":"jadran_lp"}.get(letters)


def read(base,params,*,opener=None):
    if base not in (TSDB,SPORTSCORE):
        raise ValueError("DISALLOWED_FIXTURE_SOURCE")
    url=base+"?"+urlencode(params)
    req=Request(url,headers={"User-Agent":AGENT,"Accept":"application/json"})
    requester=opener or build_opener(NoRedirect()).open
    try:
        with requester(req,timeout=12) as response:
            data=response.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:
            return None,"RESPONSE_TOO_LARGE"
        return json.loads(data.decode("utf-8")),"OK"
    except HTTPError as e:
        return None,"RATE_LIMITED" if e.code==429 else "ACCESS_DENIED" if e.code in (401,403) else "HTTP_ERROR"
    except (URLError,TimeoutError,OSError):
        return None,"NETWORK_ERROR"
    except (UnicodeError,ValueError,TypeError,json.JSONDecodeError):
        return None,"BAD_JSON_OR_REDIRECT"


def candidates(document, provider, expected, at):
    """Accepted fields are source-specific and keep first-party UTC as provenance."""
    if not isinstance(document,dict):
        raise ValueError("NOT_AN_OBJECT")
    rows=document.get("events") if provider=="thesportsdb" else document.get("matches",document.get("fixtures"))
    if rows is None:
        rows=[]
    if not isinstance(rows,list) or len(rows)>200:
        raise ValueError("INVALID_MATCH_LIST_SIZE")
    matched=0
    timed=0
    for row in rows:
        if not isinstance(row,dict):
            continue
        if provider=="thesportsdb":
            a,b=row.get("strHomeTeam"),row.get("strAwayTeam")
            timestamp=row.get("strTimestamp")
        else:
            a,b=row.get("home",row.get("home_team")),row.get("away",row.get("away_team"))
            if isinstance(a,dict):
                a=a.get("name")
            if isinstance(b,dict):
                b=b.get("name")
            timestamp=row.get("time",row.get("kickoff_utc"))
        if (team_identity(a),team_identity(b))!=expected:
            continue
        matched+=1
        try:
            date=utc(timestamp)
            if abs((date-at).total_seconds())<=3*3600:
                timed+=1
        except (ValueError,TypeError,OverflowError):
            continue
    return {"alias_identity_matches":matched,"plausible_utc_kickoffs":timed,
            "reported_records_capped":len(rows)}


def collect(case=None, *, requester=None, now=None):
    case=case or example()
    if (not isinstance(case,dict)
            or case.get("league")!="croatia_prva_nl"
            or (team_identity(case.get("home")),team_identity(case.get("away")))
               !=("sesvete","jadran_lp")):
        raise ValueError("UNRECOGNIZED_CROATIA_CASE")
    ko=utc(case["kickoff_utc"])
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_CLOCK")
    report={
        "schema":SCHEMA,"captured_utc":now.isoformat(),
        "event":"NK Sesvete vs NK Jadran Luka Ploce",
        "league":"croatia_prva_nl",
        "status":"HOLD",
        "reason":"INDEPENDENT_LIVE_DATA_NOT_AVAILABLE",
        "requests_attempted":0,"maximum_requests":MAX_REQUESTS,
        "provider_reports":[],
        "event_utc_kickoff_source_crosscheck_complete":False,
        "event_has_independently_verified_live_stats":False,
        "current_bookmaker_lines_verified":False,
        "source_score_used_to_rewrite_predictions":False,
        "live_market_model_ready":False,
        "recommendation":None,
        "production_recommendations":"DISABLED",
        "raw_api_data_published":False,
        "attribution_when_data_displayed":"Powered by SportScore",
        "attribution_url":"https://sportscore.com/",
        "attribution_link_required_for_public_display":True,
    }
    search={
        "e":"Sesvete_vs_Jadran_Luka_Ploce",
        "d":ko.date().isoformat(),
    }
    plan=[("thesportsdb",TSDB,search),
          ("sportscore",SPORTSCORE,{"sport":"football","date":ko.date().isoformat(),"limit":200})]
    for provider,endpoint,params in plan:
        report["requests_attempted"]+=1
        data,why=read(endpoint,params,opener=requester)
        obs={
            "provider":provider,"status":"HOLD","reason":why,
            "alias_identity_matches":0,"plausible_utc_kickoffs":0,
            "source_snapshot_updated_utc":None,
            "independently_verified_live_shots_or_xg":False,
            "can_replace_bookmaker_odds":False,
        }
        if why=="OK":
            try:
                result=candidates(data,provider,("sesvete","jadran_lp"),ko)
                obs.update({key:result[key] for key in ("alias_identity_matches","plausible_utc_kickoffs")})
                obs["status"]="PARTIAL" if result["plausible_utc_kickoffs"] else "HOLD"
                obs["reason"]=("MATCH_KICKOFF_MATCHES_BUT_NO_LIVE_OR_ODDS_ATTESTATION"
                               if obs["status"]=="PARTIAL" else "NO_MATCH_OR_UNVERIFIED_KICKOFF")
            except (ValueError,TypeError,KeyError,OverflowError):
                obs["reason"]="PROVIDER_SCHEMA_UNKNOWN"
        report["provider_reports"].append(obs)
    # Two publishers do not prove independent original data provenance;
    # free providers may republish the same upstream feeds.
    report["status"]="PARTIAL" if any(x["status"]=="PARTIAL" for x in report["provider_reports"]) else "HOLD"
    report["reason"]=("AT_LEAST_ONE_NAMED_FIXTURE_FOUND_RESEARCH_ONLY"
                      if report["status"]=="PARTIAL"
                      else "NO_VERIFIED_FREE_CROATIA_FIXTURE_MATCH")
    return report


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",default="croatia-free-coverage.json")
    args=parser.parse_args(argv)
    report=collect()
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],"reason":report["reason"],
                      "requests_attempted":report["requests_attempted"],
                      "provider_reports":report["provider_reports"],
                      "production_recommendations":"DISABLED"},ensure_ascii=False))


if __name__=="__main__":
    main()
