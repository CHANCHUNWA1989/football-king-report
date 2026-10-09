"""Six-league independent FIXTURE kickoff audit using free 1X2 market metadata.

The Odds API fixtures are independent of OpenFootball/OpenLigaDB schedule
records; two fixture schedules are NOT two independently verified FINAL SCORES.
Do not label unobserved kickoffs/results verified or authorize picks.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from team_identity import team_id, folded

LEAGUES = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")
MAX_MARKET_AGE_H = 26
KICKOFF_AGREEMENT_MIN = 45


def clock(v):
    dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("NO_UTC_OFFSET")
    return dt.astimezone(timezone.utc)


def audit(report, market, shadow=None):
    try:
        report_time = clock(report["checked_utc"])
        market_time = clock(market["as_of_utc"])
        fresh = (market.get("status") == "RESEARCH_ONLY"
                 and market.get("production_recommendations") == "DISABLED"
                 and -300 <= (report_time-market_time).total_seconds() <= MAX_MARKET_AGE_H*3600)
    except (KeyError, TypeError, ValueError, OverflowError):
        fresh = False
        market_time = None
    fixtures = (report.get("fixtures") or {}).get("matches") or []
    source_records = report.get("fixture_source_records") or []
    if not isinstance(source_records,list):
        source_records=[]
    shadow = shadow if isinstance(shadow,dict) and shadow.get("status")=="SHADOW_ONLY" else {}
    candidates = shadow.get("predictions") or []
    if not isinstance(candidates,list):
        candidates=[]
    markets = market.get("events") if fresh and isinstance(market.get("events"),list) else []
    if not isinstance(fixtures,list) or not isinstance(markets,list):
        raise ValueError("INVALID_SOURCE_COLLECTION")
    observed_league_labels = sorted({
        str(r.get("league")) for r in fixtures if isinstance(r,dict)
    })
    representative_fixture_fields = [{
        key:str(value)[:85] for key,value in row.items()
        if key in ("league","league_code","league_key","competition",
                   "competition_name","source","source_key","division","league_name","event_id")
    } for row in fixtures[:3] if isinstance(row,dict)]
    status = {
        "observed_original_league_labels":observed_league_labels[:18],
        "representative_fixture_fields":representative_fixture_fields,
        "schema":"football-king-independent-schedule-1",
        "status":"PARTIAL_FIXTURE_ONLY" if fresh else "HOLD",
        "report_as_of_utc":report.get("checked_utc"),
        "market_as_of_utc": market.get("as_of_utc") if fresh else None,
        "reference":"OpenFootball / OpenLigaDB vs The Odds API V4",
        "results_independently_verified_all_leagues":False,
        "results_independently_verified":False,
        "kickoff_has_two_source_confirmation":False,
        "source_is_free_derived_market":True,
        "league_coverage":[],
        "total_confirmed_kickoffs":0,
        "total_conflicting_kickoffs":0,
        "total_ambiguous_candidates":0,
        "source_age_reliable":False,
        "production_recommendations":"DISABLED",
    }
    for league in LEAGUES:
        these = [r for r in fixtures if isinstance(r,dict) and r.get("league")==league]
        # The legacy V4.1 combined report omits per-match league; its per-league
        # source records DO preserve the league and window size. Our frozen
        # pre-match shadow candidates preserve league for precise kickoff checks.
        shadow_these = [r for r in candidates if isinstance(r,dict) and r.get("league")==league]
        using_shadow_fallback = not these
        observable = shadow_these if using_shadow_fallback else these
        source_windows = [r.get("window_matches") for r in source_records
                          if isinstance(r,dict) and r.get("league")==league
                          and type(r.get("window_matches")) is int and r.get("window_matches")>=0]
        public_count = max(source_windows) if source_windows else len(these)
        there = [r for r in markets if isinstance(r,dict) and r.get("league")==league]
        unique = {}
        for x in there:
            key = (team_id(league,x.get("home")),team_id(league,x.get("away")))
            if all(key):
                unique.setdefault(key,[]).append(x)
        matched=conflict=ambiguous=precise=alias_hits=0
        for x in observable:
            if not x.get("kickoff_utc") or x.get("status") == "FINISHED":
                continue
            try:
                local=clock(x["kickoff_utc"])
            except (ValueError,TypeError,OverflowError):
                continue
            precise += 1
            key=(team_id(league,x.get("home")),team_id(league,x.get("away")))
            others=unique.get(key,[]) if all(key) else []
            if len(others)>1:
                ambiguous += 1
                continue
            if not others:
                continue
            ref=others[0]
            try:
                other_kickoff=clock(ref["kickoff_utc"])
            except (ValueError,TypeError,KeyError,OverflowError):
                continue
            delta=abs((other_kickoff-local).total_seconds())/60
            if delta <= KICKOFF_AGREEMENT_MIN:
                matched += 1
                if (folded(ref.get("home"))!=folded(x.get("home"))
                        or folded(ref.get("away"))!=folded(x.get("away"))):
                    alias_hits += 1
            elif delta <= 7*24*60:
                conflict += 1  # often a rescheduling disagreement, not a verified wrong source
        status["league_coverage"].append({
            "league":league, "public_fixtures":public_count,
            "precise_scheduled_kickoffs":precise, "market_fixture_metadata":len(there),
            "precise_kickoff_is_shadow_eligible_subset":using_shadow_fallback,
            "public_fixtures_from_source_records":bool(source_windows),
            "two_source_kickoff_agreements":matched, "time_disagreements_needing_review":conflict,
            "ambiguous_club_pairings":ambiguous, "curated_alias_matches":alias_hits,
            "score_crosschecked_with_market":0, "score_source_not_supplied_by_odds":True,
        })
        status["total_confirmed_kickoffs"] += matched
        status["total_conflicting_kickoffs"] += conflict
        status["total_ambiguous_candidates"] += ambiguous
    status["kickoff_has_two_source_confirmation"] = bool(status["total_confirmed_kickoffs"])
    status["warning"] = ("An independent quote-provider fixture list can confirm approximate kickoff "
                         "agreement, not 90-minute result correctness or quotation availability.")
    return status


def publish(site, market_file):
    site=Path(site)
    report=json.loads((site/"report.json").read_text(encoding="utf-8"))
    market=json.loads(Path(market_file).read_text(encoding="utf-8")) if Path(market_file).is_file() else {}
    shadow=json.loads((site/"shadow.json").read_text(encoding="utf-8")) if (site/"shadow.json").is_file() else {}
    result=audit(report,market,shadow)
    (site/"league_coverage.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"league_coverage":result["league_coverage"],
                      "total_confirmed_kickoffs":result["total_confirmed_kickoffs"],
                      "total_conflicting_kickoffs":result["total_conflicting_kickoffs"],
                      "observed_original_league_labels":result["observed_original_league_labels"],
                      "representative_fixture_fields":result["representative_fixture_fields"],
                      "production_recommendations":"DISABLED"},ensure_ascii=False))
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--site",default="app/site")
    parser.add_argument("--market",default="market/latest.json")
    options=parser.parse_args()
    publish(options.site,options.market)
