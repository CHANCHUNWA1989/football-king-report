"""Private, zero-credit deep-line candidate capture from existing inputs.

This adapter does not fetch odds, publish raw quotes, authenticate sources,
prove actual kickoff, sign an archive, or authorize recommendations.
"""
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from asian_handicap_research import quarter_units
from deep_handicap_diagnostics import _joint
from model_dixon_coles_forward import _case
from odds_market import SPORTS
from team_identity import team_id

SCHEMA = "football-king-deep-handicap-private-candidate-v1"
MAX_QUOTES = 10000
MAX_ROWS = 3000
PACE = .85


def _time(s):
    if not isinstance(s, str):
        raise ValueError("BAD_TIME")
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return t.astimezone(timezone.utc)


def _digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _text(s):
    return isinstance(s, str) and 0 < len(s) <= 128 and s == s.strip() and s.isprintable()


def _line(report, now):
    if (not isinstance(report, dict) or report.get("schema") != "football-king-quote-freshness-v1"
            or report.get("production_recommendations") != "DISABLED"
            or report.get("market_snapshot_research_only") is not True
            or report.get("executable_bookmaker_price_verified") is not False
            or report.get("status") != "RESEARCH_ONLY"
            or type(report.get("matched_events")) is not int or report["matched_events"] != 1):
        raise ValueError("MISSING_ELIGIBLE_PRIVATE_QUOTE_REPORT")
    home, away = report["home"], report["away"]
    if not _text(home) or not _text(away) or home == away:
        raise ValueError("BAD_MARKET_TEAM_IDENTITY")
    captured = _time(report["captured_utc"])
    if not timedelta(0) <= now-captured <= timedelta(seconds=120):
        raise ValueError("STALE_OR_FUTURE_CAPTURE")
    quotes = report["quotes"]
    if (not isinstance(quotes, list) or not 0 < len(quotes) <= MAX_QUOTES
            or type(report.get("quotes_accepted")) is not int
            or report["quotes_accepted"] != len(quotes)):
        raise ValueError("INVALID_QUOTE_BATCH")
    groups = defaultdict(dict)
    events, kickoffs = set(), set()
    for q in quotes:
        if not isinstance(q, dict):
            raise ValueError("BAD_QUOTE_ROW")
        if q.get("market") != "spreads":
            continue
        if (q.get("source") != "the_odds_api_v4"
                or q.get("status") != "FRESH_OBSERVATION_NOT_EXECUTABLE"
                or q.get("quote_pre_match_at_capture") is not True
                or q.get("market_phase_at_capture") != "PREMATCH"
                or q.get("outcome") not in (home, away)
                or not _text(q.get("event_id")) or not _text(q.get("bookmaker"))):
            raise ValueError("INVALID_SPREAD_CLAIM")
        ko, updated = _time(q["kickoff_utc"]), _time(q["market_last_update_utc"])
        if not updated <= captured <= now < ko-timedelta(minutes=10):
            raise ValueError("NO_PREMATCH_TIME_ORDER")
        if now-updated > timedelta(seconds=120):
            raise ValueError("STALE_MARKET_UPDATE")
        price = q["decimal_odds"]
        if type(price) not in (int, float) or not math.isfinite(price) or not 1.01 <= price <= 100:
            raise ValueError("INVALID_PRICE_INPUT")
        units = quarter_units(q["point"])
        side = "HOME" if q["outcome"] == home else "AWAY"
        signed = units if side == "HOME" else -units
        key = (q["bookmaker"], signed)
        if side in groups[key]:
            raise ValueError("DUPLICATE_SPREAD_SIDE")
        groups[key][side] = updated
        events.add(q["event_id"])
        kickoffs.add(ko)
    if len(events) != 1 or len(kickoffs) != 1 or not groups:
        raise ValueError("AMBIGUOUS_OR_MISSING_MARKET_EVENT")
    if any(set(g) != {"HOME", "AWAY"} or g["HOME"] != g["AWAY"] for g in groups.values()):
        raise ValueError("INCOMPLETE_OR_ASYNCHRONOUS_SPREAD_PAIR")
    lines = {key[1] for key in groups}
    if len(lines) != 1:
        raise ValueError("MULTIPLE_MARKET_LINES_NO_PRESELECTED_POLICY")
    signed = lines.pop()
    if abs(signed) < 6:
        raise ValueError("NOT_DEEP_LINE")
    return next(iter(events)), next(iter(kickoffs)), "HOME" if signed < 0 else "AWAY", -abs(signed)/4


def capture(shadow, quote_report, *, now):
    """Create at most one private candidate, never retroactively fill a result.

    The supplied clock is a claim until externally witnessed. Pair selection
    is price-independent: require unanimous complete same-book spread lines.
    """
    out = {"schema": SCHEMA, "status": "HOLD", "production_recommendations": "DISABLED",
           "private_research_only": True, "candidate": None,
           "source_authenticated": False, "actual_kickoff_authenticated": False,
           "external_archive_witness_verified": False, "qualifies_for_betting": False,
           "true_forward_sample_count": 0, "positive_expected_value_verified": False,
           "raw_quotes_emitted": False}
    try:
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise ValueError("BAD_CAPTURE_CLOCK")
        now = now.astimezone(timezone.utc)
        event, ko, side, line = _line(quote_report, now)
        if (not isinstance(shadow, dict) or shadow.get("schema") != "football-king-uncalibrated-shadow-1"
                or shadow.get("production_recommendations") != "DISABLED"
                or shadow.get("status") != "SHADOW_ONLY"):
            raise ValueError("MISSING_SHADOW_REPORT")
        rows = shadow["predictions"]
        if (not isinstance(rows, list) or not 0 < len(rows) <= MAX_ROWS
                or type(shadow.get("predictions_count")) is not int
                or shadow["predictions_count"] != len(rows)):
            raise ValueError("INVALID_SHADOW_BATCH")
        source_at = _time(shadow["as_of_utc"])
        if not timedelta(0) <= now-source_at <= timedelta(hours=10):
            raise ValueError("STALE_OR_FUTURE_SHADOW")
        league = next((k for k,v in SPORTS.items() if v == quote_report["league"]), None)
        if league is None:
            raise ValueError("UNSUPPORTED_LEAGUE")
        home, away = quote_report["home"], quote_report["away"]
        # Exact names and recorded kickoff only; native cross-source mapping
        # remains unverified. Reject any duplicate same-team candidate.
        matches = [r for r in rows if isinstance(r, dict) and r.get("league") == league
                   and r.get("home") == home and r.get("away") == away]
        if len(matches) != 1:
            raise ValueError("AMBIGUOUS_OR_MISSING_SHADOW_MATCH")
        r = matches[0]
        if _time(r["kickoff_utc"]) != ko:
            raise ValueError("KICKOFF_MISMATCH")
        if sum(isinstance(x, dict) and x.get("event_id") == r.get("event_id") for x in rows) != 1:
            raise ValueError("DUPLICATE_SHADOW_EVENT")
        # Reuse existing strict source-row/training/1X2 consistency checks.
        # No claim that the Dixon-Coles output is a DHE distribution.
        projection = _case(r, source_at, now)
        h, a = projection["expected_home_goals"], projection["expected_away_goals"]
        home_id, away_id = team_id(league, home), team_id(league, away)
        if not home_id or not away_id or home_id == away_id:
            raise ValueError("UNMAPPED_TEAM")
        identity = {"league_id": league, "fixture_id": r["event_id"], "home_id": home_id,
                    "away_id": away_id, "kickoff_utc": ko.isoformat(),
                    "side": side, "handicap": line, "information_cutoff_utc": now.isoformat()}
        evidence = {"shadow_projection_sha256": projection["source_projection_sha256"],
                    "private_quote_report_sha256": _digest(quote_report),
                    "market_event_id": event, "recorded_capture_utc": now.isoformat(),
                    "cross_source_native_id_mapping_verified": False}
        candidate = {**identity, "data_kind": "EXTERNAL_UNAUTHENTICATED", "evidence": evidence,
                     "production_recommendations": "DISABLED", "source_rates_are_rounded": True}
        ref = _digest({"identity": identity, "evidence": evidence, "pace": PACE})
        for name, pace, model in (("baseline", 1.0, "dhe-independent-poisson-rounded-v1"),
                                  ("challenger", PACE, "dhe-halftime-two-goal-pace085-v1")):
            candidate[name] = {**identity, "model_id": model, "recorded_utc": now.isoformat(),
                               "archive_reference": ref,
                               "probabilities": _joint(h,a,side,line,pace)["grades"]}
        # Digest binds output bytes, not an independent witness or attestation.
        out.update(candidate=candidate, candidate_sha256=_digest(candidate),
                   reason="CANDIDATE_READY_FOR_PRIVATE_EXTERNAL_WITNESS")
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError):
        out["reason"] = "INPUT_OR_EVIDENCE_GATE_REJECTED"
    return out
