"""Research-only four-market UEFA Champions League intake (2026-11-03).

The UEFA fixture list supports names and scheduled kickoffs, NOT a provider's
native fixture ID, authenticated bookmaker odds, a corner/HT model, or EV.
This sidecar deliberately reuses Asian settlement and quote chronology helpers.
It never feeds production selections or calls external APIs.
"""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from asian_ev_research import asian_net
from asian_ev_quote_gate import assess_quote

SCHEMA = "football-king-ucl-four-market-research-v1"
KICKOFF_UTC = "2026-11-03T20:00:00+00:00"
FIXTURE_LIST_URL = (
    "https://www.uefa.com/uefachampionsleague/news/"
    "02a8-2174c9e9019d-f909a77bd77a-1000--2026-27-champions-league-all-the-phase-fixtures/"
)
# IDs below are local request IDs, NOT UEFA IDs. Lines are USER-REQUESTED,
# not independently observed bookmaker lines.
CASES = (
    ("ucl26m4-atletico-bayern", "Atlético de Madrid", "Bayern München",
     "asian_handicap", "HOME", 0.25),
    ("ucl26m4-feyenoord-inter", "Feyenoord", "Inter",
     "corners_total", "OVER", 9.0),
    ("ucl26m4-barcelona-villa", "Barcelona", "Aston Villa",
     "first_half_goals", "OVER", 1.75),
    ("ucl26m4-villarreal-psg", "Villarreal", "Paris Saint-Germain",
     "asian_handicap", "AWAY", -0.75),
)
CASE_BY_ID = {row[0]: row for row in CASES}
GRADES = {1.0: "FULL_WIN", 0.5: "HALF_WIN", 0.0: "PUSH",
          -0.5: "HALF_LOSS", -1.0: "FULL_LOSS"}
GRADE_NAMES = tuple(GRADES.values())
PRODUCTION_RECOMMENDATIONS = "DISABLED"


def _utc(value):
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("INVALID_TIME")
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("NAIVE_TIME")
    return dt.astimezone(timezone.utc)


def _case(case_id):
    if not isinstance(case_id, str) or case_id not in CASE_BY_ID:
        raise ValueError("UNKNOWN_UCL_CASE")
    return CASE_BY_ID[case_id]


def settle(case_id, *, home_goals=None, away_goals=None, count=None):
    """Grade exact five-way Asian outcomes; odds=2 only maps grade to labels.

    For handicaps pass the selected team's match goal difference via scores.
    For other markets pass a FIRST-HALF goal total or FULL-TIME corner total.
    Neither input is a validated real match result.
    """
    _, _, _, market, selection, line = _case(case_id)
    if market == "asian_handicap":
        if (count is not None or type(home_goals) is not int
                or type(away_goals) is not int
                or not 0 <= home_goals <= 25 or not 0 <= away_goals <= 25):
            raise ValueError("INVALID_HANDICAP_SCORE")
        margin = (home_goals - away_goals if selection == "HOME"
                  else away_goals - home_goals)
        signed_line = line
    else:
        if (home_goals is not None or away_goals is not None
                or type(count) is not int or not 0 <= count <= 60
                or (market == "first_half_goals" and count > 25)):
            raise ValueError("INVALID_TOTAL_COUNT")
        margin = count
        signed_line = -line
    return GRADES[asian_net(margin, signed_line, 2.0)]


def hypothetical_distribution(case_id, probabilities):
    """Grade a SUPPLIED integer outcome distribution; never estimate one.

    Handicap keys are selected-side goal margins; corners/HT goals are totals.
    Caller-controlled probabilities are assumptions, not calibrated forecasts.
    """
    case = _case(case_id)
    market = case[3]
    if not isinstance(probabilities, dict) or not 1 <= len(probabilities) <= 70:
        raise ValueError("MISSING_ASSUMPTION_DISTRIBUTION")
    grades = {name: 0.0 for name in GRADE_NAMES}
    seen = set()
    total = 0.0
    for key, probability in probabilities.items():
        if (not isinstance(key, str) or not key
                or key != str(int(key)) if isinstance(key, str)
                and key.lstrip("-").isdigit() else True):
            raise ValueError("INVALID_OUTCOME_KEY")
        outcome = int(key)
        if outcome in seen or not (-25 <= outcome <= 25 if market == "asian_handicap"
                                    else 0 <= outcome <= (25 if market == "first_half_goals" else 60)):
            raise ValueError("INVALID_OUTCOME_SUPPORT")
        if (type(probability) not in (float, int)
                or not math.isfinite(probability) or probability < 0):
            raise ValueError("INVALID_ASSUMPTION_PROBABILITY")
        seen.add(outcome)
        total += probability
        if market == "asian_handicap":
            net = asian_net(outcome, case[5], 2.0)
        else:
            net = asian_net(outcome, -case[5], 2.0)
        grades[GRADES[net]] += probability
    if abs(total - 1.0) > 1e-9:
        raise ValueError("ASSUMPTION_NOT_NORMALIZED")
    return {name: round(value, 8) for name, value in grades.items()}


def _quote_status(case, quote, now):
    if quote is None:
        return "MISSING_QUOTE"
    if not isinstance(quote, dict):
        return "INVALID_QUOTE"
    case_id, _, _, market, selection, line = case
    if (quote.get("fixture_id") != case_id
            or quote.get("market_id") != market
            or quote.get("selection") != selection
            or type(quote.get("line")) not in (int, float)
            or not math.isfinite(quote["line"])
            or quote["line"] != line):
        return "QUOTE_FIXTURE_MARKET_LINE_MISMATCH"
    # Bookmaker/origin names are string claims, not proof of executable odds.
    if not all(isinstance(quote.get(k), str) and quote[k].strip()
               for k in ("source", "bookmaker_id", "provider_fixture_id")):
        return "MISSING_QUOTE_ORIGIN_CLAIMS"
    try:
        updated = _utc(quote.get("observed_at_utc"))
        captured = _utc(quote.get("captured_at_utc"))
        kickoff = _utc(KICKOFF_UTC)
    except (ValueError, TypeError, OverflowError):
        return "INVALID_QUOTE_TIME"
    if not updated <= captured <= now < kickoff:
        return "QUOTE_CHRONOLOGY_MISMATCH"
    if (now - captured).total_seconds() > 120:
        return "STALE_CAPTURE"
    checked = assess_quote(quote, now_utc=now, kickoff_utc=kickoff)
    if not checked["eligible_for_research"]:
        return "QUOTE_REJECTED_" + checked["reasons"][0]
    return "STRUCTURAL_ONLY_SOURCE_UNAUTHENTICATED"


def analyze(*, now_utc=None, quotes=None, distributions=None):
    """Four fixed user requests; even complete supplied data cannot unlock bets."""
    now = _utc(now_utc or datetime.now(timezone.utc))
    quotes = {} if quotes is None else quotes
    distributions = {} if distributions is None else distributions
    ids = set(CASE_BY_ID)
    if (not isinstance(quotes, dict) or not isinstance(distributions, dict)
            or not set(quotes) <= ids or not set(distributions) <= ids):
        raise ValueError("INVALID_UCL_INPUT_SCOPE")
    records = []
    for case in CASES:
        case_id, home, away, market, selection, line = case
        quote_status = _quote_status(case, quotes.get(case_id), now)
        model_status = "MISSING_DISTRIBUTION"
        grades = None
        if case_id in distributions:
            try:
                grades = hypothetical_distribution(case_id, distributions[case_id])
                model_status = "UNVERIFIED_ASSUMPTION_ONLY"
            except (ValueError, TypeError, OverflowError):
                model_status = "INVALID_ASSUMPTION_DISTRIBUTION"
        records.append({
            "case_id": case_id, "competition": "UEFA Champions League",
            "home": home, "away": away, "kickoff_utc": KICKOFF_UTC,
            "fixture_source_url": FIXTURE_LIST_URL,
            "provider_native_fixture_id": None,
            "market": market, "selection": selection,
            "user_requested_line_not_bookmaker_quote": line,
            "quote_status": quote_status, "model_status": model_status,
            "hypothetical_five_grade_probabilities": grades,
            "market_price_authenticated": False,
            "model_distribution_calibrated": False,
            "real_value_verified": False, "status": "HOLD",
        })
    return {
        "schema": SCHEMA, "generated_utc": now.isoformat(),
        "status": "HOLD", "research_only": True,
        "cases": records, "fixture_count": 4,
        "fixture_list_is_not_provider_native_identity": True,
        "bookmaker_quotes_redistributed": False,
        "independently_authenticated_odds": False,
        "independent_forecast_calibration_verified": False,
        "positive_expected_value_verified": False,
        "bets_authorized": 0,
        "production_recommendations": PRODUCTION_RECOMMENDATIONS,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="ucl-four-market-research.json")
    args = parser.parse_args()
    report = analyze()
    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("UCL_RESEARCH:", report["status"], "CASES:", report["fixture_count"],
          "PRODUCTION:", report["production_recommendations"])


if __name__ == "__main__":
    main()
