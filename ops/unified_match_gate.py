"""Fail-closed unified football match decision gate.

An auditable orchestration layer for screenshots, independent sources,
market quotes, model calibration, and settlement evidence. No scraping,
network access, model promotion, or betting execution.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from live_market_research import utc

SCHEMA="football-king-unified-decision-v1"
REQUIRED_EVIDENCE=300
MAX_SCREENSHOT_AGE=120
MAX_STATS_AGE=180
MAX_ODDS_AGE=120


def _clock(value, captured, max_age):
    try:
        age=(captured-utc(value)).total_seconds()
        return -10 <= age <= max_age
    except (ValueError,TypeError,OverflowError):
        return False


def evaluate(case, *, now=None):
    if not isinstance(case,dict):
        raise ValueError("INVALID_CASE")
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    result={
        "schema":SCHEMA,"status":"HOLD","production_recommendations":"DISABLED",
        "can_publish_pick":False,"can_execute_bet":False,
        "recommendation":None,"model_edge":None,
        "gate_checks":{},"blockers":[],
        "captured_at_utc":now.isoformat(),
        "input_is_research_only":True,
    }
    checks=result["gate_checks"]
    def check(name,good,reason):
        checks[name]=bool(good)
        if not good:
            result["blockers"].append(reason)

    fixture=case.get("fixture")
    fixture=fixture if isinstance(fixture,dict) else {}
    home=fixture.get("home")
    away=fixture.get("away")
    league=fixture.get("league")
    event_id=fixture.get("event_id")
    check("fixture_identity",
          all(isinstance(x,str) and x.strip() and len(x)<=120
              for x in (home,away,league,event_id))
          and home.strip().casefold()!=away.strip().casefold()
          if isinstance(home,str) and isinstance(away,str) else False,
          "MISSING_OR_AMBIGUOUS_FIXTURE_ID")
    check("fixture_cross_source",
          fixture.get("independent_fixture_sources",0)>=2
          if type(fixture.get("independent_fixture_sources")) is int else False,
          "NO_INDEPENDENT_FIXTURE_CROSSCHECK")
    screenshot=case.get("screenshot")
    screenshot=screenshot if isinstance(screenshot,dict) else {}
    check("screenshot_clock",
          _clock(screenshot.get("observed_at_utc"),now,MAX_SCREENSHOT_AGE),
          "SCREENSHOT_STALE_OR_MISSING_CLOCK")
    check("screenshot_score_and_minute",
          type(screenshot.get("home_goals")) is int
          and type(screenshot.get("away_goals")) is int
          and type(screenshot.get("minute")) in (int,float)
          and 0<=screenshot["home_goals"]<=25
          and 0<=screenshot["away_goals"]<=25
          and 0<=screenshot["minute"]<=125,
          "SCREENSHOT_SCORE_OR_MINUTE_UNVERIFIED")
    check("fixture_id_in_screenshot",
          screenshot.get("event_id")==event_id
          and isinstance(event_id,str) and bool(event_id),
          "SCREENSHOT_FIXTURE_ID_MISMATCH")
    stats=case.get("live_stats")
    stats=stats if isinstance(stats,dict) else {}
    check("stats_clock",
          _clock(stats.get("updated_at_utc"),now,MAX_STATS_AGE),
          "LIVE_STATS_STALE_OR_UNAVAILABLE")
    check("stats_independent",
          stats.get("independently_verified") is True
          and stats.get("event_id")==event_id
          and isinstance(event_id,str) and bool(event_id),
          "LIVE_STATS_NOT_INDEPENDENTLY_VERIFIED")
    market=case.get("market")
    market=market if isinstance(market,dict) else {}
    check("market_clock",
          _clock(market.get("last_update_utc"),now,MAX_ODDS_AGE),
          "MARKET_QUOTE_STALE_OR_MISSING")
    check("market_identity",
          market.get("event_id")==event_id
          and market.get("league")==league
          and isinstance(event_id,str) and bool(event_id),
          "MARKET_FIXTURE_OR_LEAGUE_MISMATCH")
    check("market_validated",
          market.get("validated_by_market_quote_gate") is True
          and market.get("market_key") in ("h2h","totals","spreads"),
          "MARKET_NOT_VALIDATED")
    check("market_executable",
          market.get("bookmaker_quote_executable_verified") is True,
          "BOOKMAKER_EXECUTION_NOT_VERIFIED")
    model=case.get("model")
    model=model if isinstance(model,dict) else {}
    check("model_supported_league",
          model.get("supported_league")==league
          and model.get("supported_market")==market.get("market_key")
          and isinstance(league,str) and bool(league),
          "LEAGUE_OR_MARKET_NOT_CALIBRATED")
    check("model_calibration",
          model.get("calibration_verified") is True
          and model.get("leakage_audit_passed") is True
          and model.get("out_of_sample_verified") is True,
          "MODEL_CALIBRATION_OR_LEAKAGE_UNVERIFIED")
    samples=model.get("independent_settled_forward_samples")
    check("settled_evidence",
          type(samples) is int and samples>=REQUIRED_EVIDENCE,
          "INSUFFICIENT_INDEPENDENT_SETTLED_SAMPLES")
    check("ev_independent",
          model.get("ev_provenance_verified") is True
          and model.get("market_baseline_beaten_out_of_sample") is True,
          "NO_VERIFIED_INCREMENTAL_EDGE")
    # Never allow untrusted JSON booleans to self-certify model promotion.
    # Independent review and operational approvals must be implemented in a
    # separate authenticated promotion workflow, which does not exist yet.
    check("independent_approval",
          False,"NO_INDEPENDENT_SIGNED_PROMOTION_APPROVAL")
    result["checks_passed"]=sum(checks.values())
    result["checks_total"]=len(checks)
    result["reason"]=result["blockers"][0] if result["blockers"] else "NO_RELEASE_AUTHORITY"
    return result


def main(argv=None):
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",default="unified-match-gate.json")
    a=p.parse_args(argv)
    case=json.loads(Path(a.input).read_text(encoding="utf-8"))
    result=evaluate(case)
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],
                      "checks_passed":result["checks_passed"],
                      "checks_total":result["checks_total"],
                      "blockers":result["blockers"],
                      "production_recommendations":"DISABLED"},ensure_ascii=False))


if __name__=="__main__":
    main()
