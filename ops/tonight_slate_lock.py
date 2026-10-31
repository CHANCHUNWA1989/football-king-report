"""Strict research-only forward slate and five-way Asian market outcome audit.

A sealed Git commit supplies the point-in-time history. This tool never
publishes betting recommendations, market profitability, Brier or model scores.
Unpriced qualitative ideas must not be laundered into certified forecasts.
"""
import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = "football-king-20261031-wide-research-audit-v1"
CATEGORIES = ("FULL_WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "FULL_LOSS")


def utc(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_TIMESTAMP")
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return instant.astimezone(timezone.utc)


def _quarter(value):
    return type(value) in (int, float) and math.isfinite(value) and abs(value * 4 - round(value * 4)) < 1e-9


def classify(direction, home_goals, away_goals):
    """Five-way return for any Asian quarter-line; no odds or ROI involved."""
    if (not isinstance(direction, dict)
            or type(home_goals) is not int or type(away_goals) is not int
            or min(home_goals, away_goals) < 0):
        raise ValueError("INVALID_OUTCOME_INPUT")
    market, side, line = (direction.get("market"), direction.get("side"),
                          direction.get("line"))
    if not _quarter(line):
        raise ValueError("INVALID_QUARTER_LINE")
    if market == "asian_handicap" and side in ("home", "away"):
        selected_margin = home_goals - away_goals if side == "home" else away_goals - home_goals
        difference = lambda threshold: selected_margin + threshold
    elif market == "totals" and side in ("over", "under") and line >= 0:
        scored = home_goals + away_goals
        difference = (lambda threshold: scored - threshold) if side == "over" else (lambda threshold: threshold - scored)
    else:
        raise ValueError("INVALID_MARKET_SIDE")
    # Even-quarter whole/half lines settle as a single component. Odd-quarter
    # lines split into adjacent whole/half lines (e.g. 2.25 -> 2.0 + 2.5).
    components = [line]
    if int(round(line * 4)) % 2:
        components = [line - .25, line + .25]
    outcomes = []
    for component in components:
        score = difference(component)
        outcomes.append(1 if score > 1e-9 else -1 if score < -1e-9 else 0)
    total = sum(outcomes)
    if total == len(outcomes):
        return "FULL_WIN"
    if total == -len(outcomes):
        return "FULL_LOSS"
    if total == 0:
        return "PUSH"
    if total > 0:
        return "HALF_WIN"
    return "HALF_LOSS"


def validate(data):
    """Audit the entire pre-kickoff search universe without dropping abstentions."""
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError("INVALID_SLATE_SCHEMA")
    if (data.get("production_recommendations") != "DISABLED"
            or data.get("status") != "RESEARCH_ONLY"
            or data.get("official_model_predictions") != 0
            or data.get("independently_calibrated_probabilities") is not False
            or data.get("executable_prices_verified") is not False
            or data.get("sources_independently_confirmed_each_fixture") is not False
            or data.get("fixtures_without_provider_ids_are_unverified") is not True
            or data.get("matches_with_confirmed_executable_market_prices") != 0):
        raise ValueError("UNSAFE_SLATE_CLAIMS")
    fixed = utc(data["sealed_research_as_of_utc"])
    events = data.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 500:
        raise ValueError("INVALID_SLATE_SIZE")
    seen, identities = set(), set()
    directions = 0
    abstentions = 0
    incomplete_ids = 0
    for item in events:
        if not isinstance(item, dict):
            raise ValueError("INVALID_EVENT")
        league, home, away = item.get("league"), item.get("home"), item.get("away")
        case_id, source_id, source_url = (item.get("case_id"),
                                          item.get("source_fixture_id"),
                                          item.get("fixture_source_url"))
        if (not all(isinstance(s, str) and s.strip()
                    for s in (league, home, away, case_id, source_url))
                or home == away or not source_url.startswith("https://")):
            raise ValueError("INVALID_FIXTURE_IDENTITY")
        ko = utc(item["kickoff_utc"])
        if not fixed < ko - timedelta(minutes=10):
            raise ValueError("LATE_OR_INPLAY_BACKFILLED_FIXTURE")
        if case_id in seen:
            raise ValueError("DUPLICATE_CASE_ID")
        seen.add(case_id)
        identity = (league, home.casefold(), away.casefold(), ko.isoformat())
        if identity in identities:
            raise ValueError("DUPLICATE_FIXTURE")
        identities.add(identity)
        if source_id is not None:
            if (not isinstance(source_id, str)
                    or not source_id.startswith("oddstorm:")
                    or not source_id.split(":", 1)[1].isdigit()
                    or not source_url.startswith(
                        "https://www.oddstorm.com/odds/match/"
                        + source_id.split(":", 1)[1] + "-")):
                raise ValueError("PROVIDER_ID_SOURCE_URL_MISMATCH")
        else:
            if source_url != "https://www.livescore.mobi/football/2026-10-31/":
                raise ValueError("UNVERIFIED_FIXTURE_SOURCE")
            incomplete_ids += 1
        idea = item.get("research_direction")
        if idea is None:
            abstentions += 1
            continue
        if not isinstance(idea, dict):
            raise ValueError("INVALID_IDEA")
        if not isinstance(source_id, str):
            raise ValueError("DIRECTION_WITHOUT_PROVIDER_ID")
        if (idea.get("basis") != "assistant_unpriced_hypothesis_not_model"
                or idea.get("observed_decimal_price") is not None
                or idea.get("model_probability") is not None
                or idea.get("certified_positive_ev") is not False
                or idea.get("production_recommendations") != "DISABLED"):
            raise ValueError("FORGED_MARKET_OR_MODEL_EVIDENCE")
        line = idea.get("line")
        if not _quarter(line):
            raise ValueError("BAD_MARKET_LINE")
        market, side = idea.get("market"), idea.get("side")
        if not ((market == "totals" and side in ("over", "under") and line >= 0)
                or (market == "asian_handicap" and side in ("home", "away"))):
            raise ValueError("INVALID_MARKET_SIDE")
        if "minimum_future_price_to_reconsider" in idea:
            value = idea["minimum_future_price_to_reconsider"]
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 1:
                raise ValueError("INVALID_PRICE_THRESHOLD")
        directions += 1
    return {
        "status": "RESEARCH_ONLY",
        "production_recommendations": "DISABLED",
        "official_model_predictions": 0,
        "independently_certified_forward_cases": 0,
        "certified_positive_ev_cases": 0,
        "executable_quotes": 0,
        "fixtures_recorded": len(events),
        "unpriced_research_directions": directions,
        "abstentions_recorded": abstentions,
        "provider_ids_missing": incomplete_ids,
        "settlements": 0,
        "roi": None,
        "brier": None,
        "log_loss": None,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit a sealed research slate; never releases bets")
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.input.stat().st_size > 500000:
            raise ValueError("INPUT_TOO_LARGE")
        data = json.loads(args.input.read_text(encoding="utf-8"))
        report = validate(data)
        print(json.dumps(report, sort_keys=True))
        return 0
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, OverflowError) as e:
        print(json.dumps({
            "status": "HOLD", "production_recommendations": "DISABLED",
            "reason": str(e) or "INVALID_INPUT"
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
