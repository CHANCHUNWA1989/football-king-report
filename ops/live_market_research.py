"""Research-only point-in-time Asian totals / handicap snapshot analyzer.

This module deliberately cannot produce bet advice or executable prices:
it checks known screenshot data and tests mathematically correct Asian
quarter-line payouts, without assuming a verified live feed exists.
No API credentials, no sportsbook scraping, no odds URL, no recommendation
promotion, and no alteration of archived 1X2 shadow forecasts.
"""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "football-king-live-asian-research-v1"
SUPPORTED = {"croatia_prva_nl"}
MAX_MARKETS = 40
MAX_LAG_SECONDS = 120
DEFAULT_SENSITIVITY = (1.5, 1.6, 1.7, 1.8)


def utc(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_TIMESTAMP")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return dt.astimezone(timezone.utc)


def quarter_legs(line):
    """A 1.75 total splits 50/50 into 1.5 and 2.0 total goals."""
    if type(line) not in (float, int) or not math.isfinite(line):
        raise ValueError("INVALID_ASIAN_LINE")
    q = line * 4
    if abs(q-round(q))>1e-8 or abs(line)>12:
        raise ValueError("LINE_MUST_BE_QUARTER_GOAL")
    units=int(round(q))
    if units % 2:
        return ((units-1)/4, (units+1)/4)
    return (units/4,)


def payout(market, total_home, total_away):
    """Return profit per unit stake, including the Asian half-win/half-loss."""
    if not isinstance(market, dict):
        raise ValueError("INVALID_MARKET")
    kind=market.get("kind")
    side=market.get("side")
    line=market.get("line")
    price=market.get("odds")
    if (kind not in ("totals", "handicap")
            or (kind=="totals" and side not in ("over","under"))
            or (kind=="handicap" and side not in ("home","away"))
            or type(price) not in (int,float) or not math.isfinite(price)
            or not 1.01 <= price <= 100.0
            or type(total_home) is not int or type(total_away) is not int
            or min(total_home,total_away)<0 or max(total_home,total_away)>30):
        raise ValueError("BAD_MARKET_OR_SCORE")
    legs=quarter_legs(line)
    returns=[]
    for leg in legs:
        if kind=="totals":
            diff = (total_home + total_away - leg)
            if side=="under":
                diff = -diff
        else:
            diff = (total_home-total_away+leg) if side=="home" else (
                total_away-total_home+leg)
        returns.append(price-1 if diff>0 else -1.0 if diff<0 else 0.0)
    return sum(returns)/len(returns)


def poisson_weights(lamb):
    if type(lamb) not in (float,int) or not math.isfinite(lamb) or not .01 <= lamb <= 8:
        raise ValueError("UNVERIFIED_INTENSITY")
    prob=math.exp(-lamb)
    weights=[prob]
    for n in range(1,60):
        prob*=lamb/n
        weights.append(prob)
    return weights


def totals_ev(market, lamb, already_goals=0):
    """Hypothetical Poisson sensitivity, never a calibrated live model."""
    if market.get("kind")!="totals" or type(already_goals) is not int or not 0 <= already_goals <= 20:
        raise ValueError("ONLY_RESEARCH_TOTALS")
    return round(sum(p*payout(market,already_goals+n,0)
                     for n,p in enumerate(poisson_weights(lamb))),5)


def analyze(case, *, now=None):
    if not isinstance(case,dict):
        raise ValueError("CASE_NOT_OBJECT")
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_ANALYSIS_CLOCK")
    out={
        "schema":SCHEMA,"status":"HOLD",
        "reason":"UNVERIFIED_IN_PLAY_COVERAGE",
        "league":case.get("league"),
        "match":None,
        "market_count":0,
        "snapshot_research_only":True,
        "live_odds_verified":False,
        "source_independently_verified":False,
        "live_shots_xg_verified":False,
        "league_covered_by_main_calibrated_model":False,
        "hypothetical_sensitivity_not_calibrated_probability":True,
        "point_in_time_snapshot_attested":False,
        "market_values_already_expired_or_unknown":True,
        "recommended_market":None,
        "execution_permission":False,
        "no_bookmaker_or_api_contact":True,
        "production_recommendations":"DISABLED",
        "markets":[],
    }
    if case.get("league") not in SUPPORTED:
        out["reason"]="LEAGUE_NOT_SUPPORTED_FOR_MANUAL_RESEARCH"
        return out
    home,away=case.get("home"),case.get("away")
    if (not all(isinstance(x,str) and 0<len(x.strip())<=120 for x in (home,away))
            or home.strip().casefold()==away.strip().casefold()):
        out["reason"]="INVALID_TEAM_IDENTITIES"
        return out
    try:
        recorded=utc(case["observed_at_utc"])
        kickoff=utc(case["kickoff_utc"])
    except (KeyError,ValueError,TypeError,OverflowError):
        out["reason"]="INVALID_KICKOFF_OR_SCREENSHOT_TIME"
        return out
    # An exchange screenshot is not a cryptographically verified book quote.
    # Allow 8 minute tolerance for user device clock and injury-time delays.
    minute=case.get("minute")
    h=case.get("home_goals")
    a=case.get("away_goals")
    if (type(minute) not in (float,int) or not 0 <= minute <= 125
            or type(h) is not int or type(a) is not int
            or min(h,a)<0 or max(h,a)>25
            or abs((recorded-kickoff).total_seconds()/60-minute)>8):
        out["reason"]="GAME_CLOCK_OR_SCORE_UNVERIFIED"
        return out
    out["match"]={"home":home,"away":away,"home_goals":h,
                  "away_goals":a,"minute":minute,"kickoff_utc":kickoff.isoformat(),
                  "observed_at_utc":recorded.isoformat()}
    markets=case.get("markets")
    if not isinstance(markets,list) or len(markets)>MAX_MARKETS:
        out["reason"]="BAD_MARKET_COLLECTION"
        return out
    found=[]
    for m in markets:
        try:
            # Even for 1.5 line require a VALID handicap-side convention.
            value=payout(m, h, a)
            if not isinstance(m.get("market_id"),str) or not 0<len(m["market_id"])<=80:
                continue
            if any(x["market_id"]==m["market_id"] for x in found):
                out["reason"]="DUPLICATE_MARKET_IDENTIFIERS"
                return out
            found.append({"market_id":m["market_id"],
                          "kind":m["kind"],"side":m["side"],
                          "line":m["line"],"odds":m["odds"],
                          "current_score_payout_if_final":round(value,4)})
        except (ValueError,TypeError,KeyError,OverflowError):
            continue
    out["market_count"]=len(found)
    if not found:
        out["reason"]="NO_VALID_SCREENSHOT_MARKETS"
        return out
    out["markets"]=found
    verified_at=case.get("bookmaker_quote_updated_utc")
    if verified_at is None:
        out["reason"]="SCREENSHOT_HAS_NO_VERIFIABLE_BOOKMAKER_QUOTE_TIMESTAMP"
    else:
        try:
            updated=utc(verified_at)
            if 0 <= (recorded-updated).total_seconds() <= MAX_LAG_SECONDS and (
                    now-recorded).total_seconds() <= MAX_LAG_SECONDS and (
                    now-recorded).total_seconds() >= -10:
                out["point_in_time_snapshot_attested"]=bool(
                    case.get("source_time_attested") is True)
                out["live_odds_verified"]=out["point_in_time_snapshot_attested"]
                out["market_values_already_expired_or_unknown"]=False
                out["reason"]="LIVE_MARKET_RESEARCH_ONLY_NO_CALIBRATED_LEAGUE_MODEL"
            else:
                out["reason"]="STALE_LIVE_MARKET_OR_SCREENSHOT"
        except (ValueError,TypeError,OverflowError):
            out["reason"]="INVALID_BOOKMAKER_UPDATE_TIME"

    scenarios=[]
    already=h+a
    for m in found:
        if m["kind"]!="totals":
            continue
        for lam in DEFAULT_SENSITIVITY:
            scenarios.append({"market_id":m["market_id"],
                              "remaining_goals_assumption":lam,
                              "hypothetical_ev":totals_ev(m,lam,already)})
    out["hypothetical_scenarios"]=scenarios
    # Deliberate HOLD even with good time metadata: no calibrated model for
    # Croatian second tier, no independent bookmaker executable quote, and
    # no verified shot/xG momentum source.
    return out


def example():
    """User-visible 30:09 0-0 screenshot; source quote time is unknown."""
    return {
        "league":"croatia_prva_nl",
        "home":"NK Sesvete","away":"NK Jadran Luka Ploce",
        "kickoff_utc":"2026-10-09T13:00:00+00:00",
        "observed_at_utc":"2026-10-09T13:30:09+00:00",
        "minute":30.15,"home_goals":0,"away_goals":0,
        "home_corners":0,"away_corners":1,
        "home_yellows":0,"away_yellows":0,
        "bookmaker_quote_updated_utc":None,
        "source_time_attested":False,
        "markets":[
            {"market_id":"over_1_5","kind":"totals","side":"over","line":1.5,"odds":1.81},
            {"market_id":"under_1_5","kind":"totals","side":"under","line":1.5,"odds":1.99},
            {"market_id":"over_1_75","kind":"totals","side":"over","line":1.75,"odds":2.06},
            {"market_id":"under_1_75","kind":"totals","side":"under","line":1.75,"odds":1.74},
            {"market_id":"over_1_25","kind":"totals","side":"over","line":1.25,"odds":1.52},
            {"market_id":"under_1_25","kind":"totals","side":"under","line":1.25,"odds":2.38},
            {"market_id":"home_plus_0_25","kind":"handicap","side":"home","line":.25,"odds":1.76},
            {"market_id":"away_minus_0_25","kind":"handicap","side":"away","line":-.25,"odds":2.06},
            {"market_id":"home_0","kind":"handicap","side":"home","line":0,"odds":2.19},
            {"market_id":"away_0","kind":"handicap","side":"away","line":0,"odds":1.66},
            {"market_id":"home_plus_0_5","kind":"handicap","side":"home","line":.5,"odds":1.53},
            {"market_id":"away_minus_0_5","kind":"handicap","side":"away","line":-.5,"odds":2.40}
        ]
    }


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--case", default=None)
    parser.add_argument("--output", default="live-asian-research.json")
    args=parser.parse_args(argv)
    case=json.loads(Path(args.case).read_text(encoding="utf-8")) if args.case else example()
    report=analyze(case)
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",
                                 encoding="utf-8")
    print(json.dumps({"status":report["status"],"reason":report["reason"],
                      "market_count":report["market_count"],
                      "recommended_market":report["recommended_market"],
                      "production_recommendations":"DISABLED"},ensure_ascii=False))


if __name__=="__main__":
    main()
