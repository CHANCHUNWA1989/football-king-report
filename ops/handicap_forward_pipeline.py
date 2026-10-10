"""Fail-closed prospective Asian-spread PAPER settlement evidence chain.

Inputs: already-sanitized The Odds API quote-audit JSON (from
ops/market_quote_gate.py), and an independent FREE result-source audit.
Never scrape bookmaker sites, write sportsbook raw prices into the public
website, claim executable quotations, infer ROI from a 1X2 consensus, or
authorize wagers. The output is metadata and pooled paper statistics only.

Provider names and source timestamps are claims in supplied JSON, not signed
proof of genuine exchange execution or a legally permissible bookmaker quote.
"""
import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from asian_handicap_research import grade, quarter_units
from odds_market import SPORTS
from source_publish_guard import verify
from team_identity import team_id

SCHEMA = "football-king-asian-spread-forward-paper-audit-v1"
QUOTE_SCHEMA = "football-king-quote-freshness-v1"
LEAGUE_BY_SPORT = {sport: league for league, sport in SPORTS.items()}
ACCEPTED_PROVIDER_NAMES = frozenset(("thesportsdb", "api_football", "football_data_org"))
MAX_QUOTES = 10000
MAX_FIXTURES = 150
MAX_CAPTURE_AGE = timedelta(days=7)
MAX_RESULT_AGE = timedelta(days=7)


def utc(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIME")
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return d.astimezone(timezone.utc)


def blank(now):
    return {
        "schema": SCHEMA, "checked_utc": now.isoformat(), "status": "HOLD",
        "reason": "NO_VALID_PROSPECTIVE_ASIAN_QUOTE_SNAPSHOT",
        "research_only": True,
        "qualified_pre_match_quote_count": 0,
        "candidate_quote_count": 0, "candidate_fixtures": 0,
        "two_publisher_exact_score_matches": 0,
        "two_publisher_match_is_not_cryptographic_authentication": True,
        "independent_quote_provenance_authenticated": False,
        "licensed_executable_prices_confirmed": False,
        "genuine_forward_market_roi_verified": False,
        "can_calibrate_model_using_quote_prices": False,
        "bets_authorized": 0,
        "production_recommendations": "DISABLED",
        "rejected": {},
        "paper_five_grade_counts": {key: 0 for key in (
            "FULL_WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "FULL_LOSS")},
        "model_accuracy_or_ev_from_this_audit": None,
        "paper_net_units_per_one_unit_quote": None,
        "paper_roi_is_not_executable_betting_roi": True,
        "no_raw_bookmaker_quotes_redistributed": True,
    }


def analyze(quote_report, results_report, *, now=None, verifier=verify):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    report = blank(now)
    if (not isinstance(quote_report, dict)
            or quote_report.get("schema") != QUOTE_SCHEMA
            or quote_report.get("production_recommendations") != "DISABLED"
            or quote_report.get("executable_bookmaker_price_verified") is not False
            or quote_report.get("market_snapshot_research_only") is not True
            or not isinstance(quote_report.get("quotes"), list)
            or len(quote_report["quotes"]) > MAX_QUOTES):
        return report
    report["candidate_quote_count"] = len(quote_report["quotes"])
    try:
        captured = utc(quote_report["captured_utc"])
        if not timedelta(minutes=-5) <= now - captured <= MAX_CAPTURE_AGE:
            report["reason"] = "QUOTE_CAPTURE_OUTSIDE_FORWARD_WINDOW"
            return report
        sport = quote_report["league"]
        league = LEAGUE_BY_SPORT.get(sport)
        home, away = quote_report["home"], quote_report["away"]
        hkey, akey = team_id(league, home), team_id(league, away)
        if not league or not hkey or not akey or hkey == akey:
            raise ValueError("BAD_LEAGUE_FIXTURE_IDENTITY")
    except (ValueError, TypeError, KeyError, OverflowError):
        report["reason"] = "INVALID_QUOTE_METADATA"
        return report
    if (not isinstance(results_report, dict)
            or results_report.get("production_recommendations") != "DISABLED"):
        report["reason"] = "NO_RESULT_PUBLISHER_SNAPSHOT"
        return report
    try:
        result_captured = verifier(results_report)
        if (not -timedelta(minutes=5) <= now - result_captured <= MAX_RESULT_AGE
                or result_captured < captured
                or not isinstance(results_report.get("sampled_fixtures"), list)
                or len(results_report["sampled_fixtures"]) > MAX_FIXTURES):
            raise ValueError("BAD_RESULT_SOURCE_TIME")
    except (ValueError, TypeError, OverflowError, KeyError):
        report["reason"] = "UNVERIFIED_RESULT_SOURCE_ENVELOPE"
        return report

    results = defaultdict(lambda: defaultdict(set))
    for row in results_report["sampled_fixtures"]:
        if not isinstance(row, dict) or row.get("provider") not in ACCEPTED_PROVIDER_NAMES:
            continue
        if row.get("status") != "FINISHED" or row.get("league") != league:
            continue
        try:
            pair = (team_id(league, row["home"]), team_id(league, row["away"]))
            ko = utc(row["kickoff_utc"])
            score = row["score_ft"]
            if (not isinstance(score, list) or len(score) != 2 or
                    not all(type(x) is int and 0 <= x <= 30 for x in score) or
                    not all(pair) or pair[0] == pair[1]):
                continue
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
        results[(pair[0], pair[1], ko.isoformat())][row["provider"]].add(tuple(score))

    rejected = Counter()
    accepted = []
    seen = set()
    crosschecked_fixtures = set()
    for item in quote_report["quotes"]:
        if not isinstance(item, dict):
            rejected["MALFORMED_QUOTE"] += 1
            continue
        try:
            if (item.get("status") != "FRESH_OBSERVATION_NOT_EXECUTABLE"
                    or item.get("source") != "the_odds_api_v4"
                    or item.get("market") != "spreads"
                    or item.get("outcome") not in (home, away)):
                raise ValueError("NOT_ELIGIBLE_SPREAD")
            event_id = item["event_id"]
            bookmaker = item["bookmaker"]
            if not all(isinstance(x, str) and 0 < len(x) <= 120
                       for x in (event_id, bookmaker)):
                raise ValueError("MISSING_QUOTE_IDENTITY")
            ko, updated = utc(item["kickoff_utc"]), utc(item["market_last_update_utc"])
            # Strict PREMATCH-only: no early whistle, no unknown time.
            if not (updated <= captured <= ko - timedelta(minutes=10)):
                raise ValueError("NO_SEALED_PREMATCH_PRICE")
            if captured - updated > timedelta(seconds=120):
                raise ValueError("STALE_MARKET_PRICE")
            price = item["decimal_odds"]
            if (type(price) not in (float, int) or not math.isfinite(price)
                    or not 1.01 <= price <= 100):
                raise ValueError("INVALID_DECIMAL_PRICE")
            handicap = item["point"]
            quarter_units(handicap)
            identity = (event_id, bookmaker, item["outcome"], str(handicap), ko.isoformat())
            if identity in seen:
                raise ValueError("DUPLICATE_PRICE")
            seen.add(identity)
            if ko + timedelta(minutes=105) > now:
                raise ValueError("NOT_YET_MATURED")
            side = "HOME" if item["outcome"] == home else "AWAY"
            observations = defaultdict(set)
            for (hh, aa, ts), publishers in results.items():
                if (hh, aa) != (hkey, akey):
                    continue
                if abs((utc(ts)-ko).total_seconds()) <= 45*60:
                    for provider, votes in publishers.items():
                        observations[provider].update(votes)
            if len(observations) < 2:
                raise ValueError("LESS_THAN_TWO_INDEPENDENT_SCORE_PUBLISHERS")
            if any(len(v) != 1 for v in observations.values()):
                raise ValueError("CONFLICTING_SCORE_WITHIN_PUBLISHER")
            exact_scores = {next(iter(v)) for v in observations.values()}
            if len(exact_scores) != 1:
                raise ValueError("DIFFERENT_FULL_TIME_SCORE_ACROSS_PUBLISHERS")
            score = next(iter(exact_scores))
            result = grade(score[0], score[1], side, handicap)
            profit = {"FULL_WIN": price - 1, "HALF_WIN": (price - 1) / 2,
                      "PUSH": 0, "HALF_LOSS": -0.5, "FULL_LOSS": -1}[result]
            accepted.append((result, profit))
            crosschecked_fixtures.add((hkey, akey, ko.isoformat()))
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            rejected[str(exc)] += 1
            continue

    report["qualified_pre_match_quote_count"] = len(accepted)
    report["candidate_fixtures"] = len(crosschecked_fixtures)
    report["two_publisher_exact_score_matches"] = len(crosschecked_fixtures)
    report["rejected"] = dict(rejected)
    if accepted:
        counts = Counter(r for r, _ in accepted)
        report["paper_five_grade_counts"] = {
            k: counts[k] for k in report["paper_five_grade_counts"]}
        report["paper_net_units_per_one_unit_quote"] = round(
            sum(profit for _, profit in accepted) / len(accepted), 6)
        report["status"] = "RESEARCH_ONLY"
        report["reason"] = "UNAUTHENTICATED_EXECUTION_PAPER_SETTLEMENT_ONLY"
    else:
        report["reason"] = "NO_TWO_SOURCE_FINAL_WITH_VALID_PREMATCH_SPREAD"
    return report


def publish(site, *, quotes, sources, now=None):
    def read(path):
        f=Path(path)
        if not f.is_file() or f.stat().st_size > 1_500_000:
            return None
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (UnicodeError, ValueError, OSError):
            return None
    summary=analyze(read(quotes), read(sources), now=now)
    Path(site).mkdir(parents=True, exist_ok=True)
    (Path(site)/"handicap_forward_audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k:summary.get(k) for k in (
        "status", "reason", "candidate_quote_count",
        "qualified_pre_match_quote_count", "two_publisher_exact_score_matches",
        "production_recommendations")}, ensure_ascii=False))
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--site", default="app/site")
    parser.add_argument("--quotes", default="evidence/authorized_asian_quote_audit.json")
    parser.add_argument("--sources", default="sources/latest.json")
    args=parser.parse_args()
    publish(args.site, quotes=args.quotes, sources=args.sources)
