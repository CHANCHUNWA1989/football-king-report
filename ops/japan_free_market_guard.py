"""Fail-closed publishing guard for FREE J1 market COVERAGE metadata only."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from japan_free_market import SCHEMA,utc

NAMES=("propline","therundown","the_odds_api_j1")
PROVIDER_KEYS=frozenset((
    "provider","configured","status","reason","requests_attempted",
    "upcoming_events","fresh_3way_event_count","fresh_spread_event_count",
    "fresh_totals_event_count","free_stale_quote_rejects",
    "market_quotes_are_not_executable","independently_calibrated_j1_model",
    "production_recommendations","provider_daily_remaining","quota_remaining"
))
ROOT_KEYS=frozenset((
    "schema","collected_utc","status","j1_free_prematch_sources",
    "cross_feed_consistency_observation",
    "the_odds_api_european_six_league_market_is_untouched",
    "j1_fixtures_not_independently_verified",
    "j1_model_remains_uncalibrated","j1_2026_27_outcomes_not_proven",
    "realtime_inplay_quotes_confirmed","free_tier_closing_lines_available",
    "raw_bookmaker_prices_or_names_redistributed","estimated_roi",
    "bet_recommendation_count","production_recommendations",
    "no_secret_values_logged_or_persisted"
))
CROSS_KEYS=frozenset((
    "same_fixture_two_api_observations","median_abs_home_probability_delta",
    "api_provider_count_is_not_independent_bookmaker_count",
    "independent_venue_quote_verified"
))
REQUIRED_FALSE=("realtime_inplay_quotes_confirmed",
                "free_tier_closing_lines_available",
                "raw_bookmaker_prices_or_names_redistributed")
REQUIRED_TRUE=("the_odds_api_european_six_league_market_is_untouched",
               "j1_fixtures_not_independently_verified",
               "j1_model_remains_uncalibrated",
               "j1_2026_27_outcomes_not_proven",
               "no_secret_values_logged_or_persisted")


def check(doc,*,now=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_VALIDATION_CLOCK")
    if (not isinstance(doc,dict) or set(doc)!=ROOT_KEYS
            or doc.get("schema")!=SCHEMA
            or doc.get("status") not in ("HOLD","RESEARCH_ONLY")
            or doc.get("production_recommendations")!="DISABLED"
            or doc.get("estimated_roi") is not None
            or doc.get("bet_recommendation_count")!=0
            or any(doc.get(x) is not False for x in REQUIRED_FALSE)
            or any(doc.get(x) is not True for x in REQUIRED_TRUE)):
        raise ValueError("INVALID_J1_MARKET_PUBLISH_METADATA")
    stamp=utc(doc["collected_utc"])
    if not -timedelta(minutes=5)<=now-stamp<=timedelta(hours=48):
        raise ValueError("J1_MARKET_METADATA_STALE_OR_FUTURE")
    sources=doc.get("j1_free_prematch_sources")
    if (not isinstance(sources,list) or len(sources)!=3
            or tuple(s.get("provider") for s in sources if isinstance(s,dict))!=NAMES):
        raise ValueError("WRONG_J1_PROVIDER_SET")
    active=False
    for x in sources:
        if (not isinstance(x,dict) or not set(x).issubset(PROVIDER_KEYS)
                or not (PROVIDER_KEYS-{"provider_daily_remaining","quota_remaining"}).issubset(set(x))
                or type(x.get("configured")) is not bool
                or x.get("status") not in ("HOLD","NOT_CONFIGURED","RESEARCH_ONLY")
                or not isinstance(x.get("reason"),str)
                or not 0<len(x["reason"])<=110
                or x.get("market_quotes_are_not_executable") is not True
                or x.get("independently_calibrated_j1_model") is not False
                or x.get("production_recommendations")!="DISABLED"):
            raise ValueError("UNSAFE_J1_PROVIDER_INFO")
        for field in ("requests_attempted","upcoming_events",
                      "fresh_3way_event_count","fresh_spread_event_count",
                      "fresh_totals_event_count","free_stale_quote_rejects"):
            v=x.get(field)
            if type(v) is not int or v<0 or v>2000:
                raise ValueError("BAD_J1_SOURCE_COUNT")
        for field in ("provider_daily_remaining","quota_remaining"):
            if field in x and (type(x[field]) is not int or not 0<=x[field]<=1000000):
                raise ValueError("INVALID_FREE_QUOTA_METADATA")
        if (not x["configured"] and
                (x["status"]!="NOT_CONFIGURED" or x["requests_attempted"]!=0)):
            raise ValueError("INVENTED_J1_KEY_CONNECTION")
        if x["status"]=="RESEARCH_ONLY":
            active=True
            if not x["configured"] or not any(x[k] for k in (
                "fresh_3way_event_count","fresh_spread_event_count",
                "fresh_totals_event_count")):
                raise ValueError("J1_SOURCE_COVERAGE_UNJUSTIFIED")
    if (doc["status"]=="RESEARCH_ONLY") != active:
        raise ValueError("J1_SOURCE_STATUS_TOTAL_MISMATCH")
    link=doc.get("cross_feed_consistency_observation")
    if not isinstance(link,dict) or set(link)!=CROSS_KEYS:
        raise ValueError("J1_CROSS_SOURCE_SCHEMA_UNSAFE")
    n=link["same_fixture_two_api_observations"]
    delta=link["median_abs_home_probability_delta"]
    if (type(n) is not int or not 0<=n<=120
            or (n==0 and delta is not None)
            or (n>0 and (type(delta) not in (float,int) or not 0<=delta<=1))
            or link["api_provider_count_is_not_independent_bookmaker_count"] is not True
            or link["independent_venue_quote_verified"] is not False):
        raise ValueError("FALSE_CROSS_FEED_EVIDENCE")
    return stamp


def latest_can_replace(previous,incoming,*,now=None):
    new=check(incoming,now=now)
    if previous is None:
        return True
    # Existing published snapshot can be much older than 48 hours.
    # Validate its structure at its OWN capture time, then compare stamps;
    # don't let a stale but correctly archived record block all future runs.
    old=check(previous,now=utc(previous["collected_utc"]))
    if new<old:return False
    if new==old and previous!=incoming:
        raise ValueError("SAME_TIME_CONFLICT")
    return new>old


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--previous",default="")
    p.add_argument("--decision",default="")
    a=p.parse_args()
    incoming=json.loads(Path(a.input).read_text(encoding="utf-8"))
    previous=json.loads(Path(a.previous).read_text(encoding="utf-8")) if a.previous and Path(a.previous).is_file() else None
    replace=latest_can_replace(previous,incoming)
    if a.decision:
        Path(a.decision).write_text(json.dumps({"replace":replace})+"\n",encoding="utf-8")
    print(json.dumps({"safe":True,"replace":replace,
                      "qualified_source_count":sum(s["status"]=="RESEARCH_ONLY"
                      for s in incoming["j1_free_prematch_sources"]),
                      "bets_authorized":0}))


if __name__=="__main__":
    main()
