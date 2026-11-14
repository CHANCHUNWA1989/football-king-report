"""Research-only predeclared multi-market watchlist and complete-cohort review.

The same pre-match selection IDs are evaluated whether PRIORITY, WATCH,
EXCLUDED or HOLD. Nothing here independently authenticates the pre-match clock,
source rights, bookmaker executability or final score. Never issues bets.
"""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from math import isfinite
from pathlib import Path

from ops.asian_ev_research import asian_net
from ops.research_safe_output import write_new_private_json

DECISIONS = ("PRIORITY_RESEARCH", "WATCH", "EXCLUDED", "HOLD")
MARKET_SIDES = {
    "h2h": ("home", "draw", "away"),
    "asian_handicap": ("home", "away"),
    "totals": ("over", "under"),
}
MAX_ROWS = 1000


def _time(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIME")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_TIME") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("NAIVE_TIME")
    return dt.astimezone(timezone.utc)


def _line(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("INVALID_LINE")
    try:
        line = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("INVALID_LINE") from exc
    if not line.is_finite() or abs(line) > 25 or line * 4 != (line * 4).to_integral_value():
        raise ValueError("INVALID_QUARTER_LINE")
    return line


def _price(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("INVALID_ODDS")
    try:
        odds = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("INVALID_ODDS") from exc
    if not odds.is_finite() or not 1 < odds <= 100:
        raise ValueError("INVALID_ODDS")
    return odds


def _label(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ValueError("INVALID_" + name)
    return value


def _watchlist(rows, now):
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError("INVALID_WATCHLIST")
    normalized = []
    ids, markets = set(), set()
    fixtures = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("INVALID_WATCHLIST_ROW")
        if any(key in row for key in (
                "home_goals", "away_goals", "score_ft", "outcome", "result",
                "historical_outcome", "finished_at_utc")):
            raise ValueError("POSTMATCH_FIELDS_IN_WATCHLIST")
        sid = _label(row.get("selection_id"), "SELECTION_ID")
        fixture = _label(row.get("fixture_id"), "FIXTURE_ID")
        competition = _label(row.get("competition"), "COMPETITION")
        _label(row.get("model_version"), "MODEL_VERSION")
        market, side = row.get("market"), row.get("selection")
        if market not in MARKET_SIDES or side not in MARKET_SIDES[market]:
            raise ValueError("INVALID_MARKET_SELECTION")
        decision = row.get("decision")
        if decision not in DECISIONS:
            raise ValueError("INVALID_PREMATCH_DECISION")
        line = _line(row.get("line"))
        if (market == "h2h" and line != 0) or (market == "totals" and line < 0):
            raise ValueError("INVALID_MARKET_LINE")
        registered, kickoff = _time(row.get("registered_at_utc")), _time(row.get("kickoff_at_utc"))
        if registered >= kickoff or registered > now:
            raise ValueError("NOT_PREMATCH_REGISTRATION")
        fixture_identity = (competition, kickoff)
        if fixture in fixtures and fixtures[fixture] != fixture_identity:
            raise ValueError("CONFLICTING_FIXTURE_IDENTITY")
        fixtures[fixture] = fixture_identity
        if sid in ids:
            raise ValueError("DUPLICATE_SELECTION_ID")
        identity = (fixture, market, side, line)
        # Prevent adding multiple prices on the same original decision as
        # separate winning observations after inspecting the result.
        if identity in markets:
            raise ValueError("DUPLICATE_MARKET_DECISION")
        ids.add(sid)
        markets.add(identity)
        raw_odds = row.get("decimal_odds")
        odds = None
        if raw_odds is None:
            if decision != "HOLD":
                raise ValueError("UNPRICED_ACTIVE_CANDIDATE")
            if any(row.get(key) is not None
                   for key in ("bookmaker", "quote_updated_at_utc", "captured_at_utc")):
                raise ValueError("PARTIAL_QUOTE_EVIDENCE")
        else:
            odds = _price(raw_odds)
            _label(row.get("bookmaker"), "BOOKMAKER")
            quoted = _time(row.get("quote_updated_at_utc"))
            captured = _time(row.get("captured_at_utc"))
            if not (quoted <= captured <= registered < kickoff):
                raise ValueError("QUOTE_REGISTRATION_CHRONOLOGY")
            if (captured - quoted).total_seconds() > 1200 or (registered - captured).total_seconds() > 1200:
                raise ValueError("STALE_QUOTE_AT_REGISTRATION")
        normalized.append({
            "selection_id": sid, "fixture_id": fixture,
            "market": market, "selection": side, "line": line,
            "decision": decision, "decimal_odds": odds,
            "kickoff": kickoff, "registered": registered,
        })
    return normalized


def _manifest_digest(rows):
    # Byte-equivalent canonical JSON from the full submitted manifest.
    # SHA alone is not evidence of pre-match creation or independent custody.
    try:
        raw = json.dumps(rows, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("INVALID_MANIFEST_SERIALIZATION") from exc
    return hashlib.sha256(raw).hexdigest()


def seal_manifest(watchlist, *, issued_at_utc):
    """Create an *unattested local* prior-content pin, not a trusted timestamp.

    A real pre-match proof still requires a genuinely independent, immutable
    external record made before kickoff. Self-entered timestamps are not proof.
    """
    issued = _time(issued_at_utc)
    # Validate every row's own chronology independently of a seal clock,
    # then check the asserted seal time against all individual registrations.
    cohort = _watchlist(watchlist, datetime.max.replace(tzinfo=timezone.utc))
    if not cohort:
        raise ValueError("EMPTY_WATCHLIST_NOT_SEALABLE")
    if issued >= min(row["kickoff"] for row in cohort):
        raise ValueError("PIN_NOT_PREMATCH")
    if issued < max(row["registered"] for row in cohort):
        raise ValueError("PIN_BEFORE_REGISTRATION")
    return {
        "schema": "football-king-local-watchlist-pin-v1",
        "manifest_sha256": _manifest_digest(watchlist),
        "selection_count": len(cohort),
        "issued_at_utc": issued.isoformat(),
        "manifest_source_provenance": "LOCAL_UNATTESTED",
        "external_attestation_verified": False,
        "production_recommendations": "DISABLED",
    }


def _verify_manifest_pin(watchlist, pin, now, digest):
    """Fail closed on a changed watchlist, pin shape, time or self-approval."""
    if not isinstance(pin, dict):
        raise ValueError("INVALID_MANIFEST_PIN")
    expected_keys = {
        "schema", "manifest_sha256", "selection_count", "issued_at_utc",
        "manifest_source_provenance", "external_attestation_verified",
        "production_recommendations",
    }
    if set(pin) != expected_keys:
        raise ValueError("INVALID_MANIFEST_PIN")
    issued = _time(pin["issued_at_utc"])
    if issued > now:
        raise ValueError("FUTURE_MANIFEST_PIN")
    expected = seal_manifest(watchlist, issued_at_utc=pin["issued_at_utc"])
    if (pin.get("schema") != expected["schema"]
            or pin.get("manifest_source_provenance") != "LOCAL_UNATTESTED"
            or pin.get("external_attestation_verified") is not False
            or pin.get("production_recommendations") != "DISABLED"):
        raise ValueError("INVALID_MANIFEST_PIN")
    if type(pin.get("selection_count")) is not int:
        raise ValueError("INVALID_MANIFEST_PIN")
    supplied = pin.get("manifest_sha256")
    if (not isinstance(supplied, str) or len(supplied) != 64
            or any(c not in "0123456789abcdef" for c in supplied)):
        raise ValueError("INVALID_MANIFEST_PIN")
    if (pin["selection_count"] != expected["selection_count"]
            or supplied != digest or pin["issued_at_utc"] != expected["issued_at_utc"]):
        raise ValueError("WATCHLIST_MANIFEST_MISMATCH")
    return True


def _results(rows):
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError("INVALID_RESULTS")
    entries = {}
    duplicates = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("INVALID_RESULT_ROW")
        event = _label(row.get("fixture_id"), "RESULT_FIXTURE_ID")
        if event in entries:
            duplicates.add(event)
        else:
            entries[event] = row
    return entries, duplicates


def _settle(row, h, a):
    odds = float(row["decimal_odds"])
    line = float(row["line"])
    market, side = row["market"], row["selection"]
    if market == "h2h":
        outcome = "home" if h > a else "away" if a > h else "draw"
        return odds - 1 if outcome == side else -1.0
    if market == "asian_handicap":
        margin = h - a if side == "home" else a - h
        return asian_net(margin, line, odds)
    goals = h + a
    return asian_net(goals if side == "over" else -goals,
                     -line if side == "over" else line, odds)


def _grade(net, odds):
    # Grade by exact quarter-line net returns, not naive binary win rate.
    possible = (
        ("FULL_WIN", float(odds) - 1),
        ("HALF_WIN", (float(odds) - 1) / 2),
        ("PUSH", 0.0),
        ("HALF_LOSS", -0.5),
        ("FULL_LOSS", -1.0),
    )
    for name, value in possible:
        if abs(net - value) < 1e-8:
            return name
    raise ValueError("UNKNOWN_SETTLEMENT_GRADE")


def review(watchlist, results, *, checked_at_utc, manifest_pin=None):
    """Descriptive audit of ALL predeclared selections, not only winning picks.

    The inputs can be edited by their provider. Timestamp checks and hashes
    alone cannot prove immutable pre-match capture or independent final scores.
    """
    now = _time(checked_at_utc)
    cohort = _watchlist(watchlist, now)
    # Invariant: every original decision belongs to the same content digest;
    # a separate local prior pin must match it byte-for-byte to be reported.
    manifest_digest = _manifest_digest(watchlist)
    pinned = (_verify_manifest_pin(watchlist, manifest_pin, now, manifest_digest)
              if manifest_pin is not None else False)
    final, duplicate_finals = _results(results)
    by_decision = {decision: {
        "all_predeclared": 0, "scored_research_only": 0,
        "pending_or_unverifiable": 0, "missing_usable_price": 0,
        "hypothetical_net_units": 0.0,
        "settlement_grades": dict.fromkeys(
            ("FULL_WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "FULL_LOSS"), 0),
    } for decision in DECISIONS}
    cases = []
    for item in cohort:
        event, decision = item["fixture_id"], item["decision"]
        aggregate = by_decision[decision]
        aggregate["all_predeclared"] += 1
        result_status = "NO_RESULT"
        net = None
        grade = None
        source = final.get(event)
        if event in duplicate_finals:
            result_status = "AMBIGUOUS_DUPLICATE_RESULT"
        elif source is not None:
            try:
                result_ko = _time(source.get("kickoff_at_utc"))
                finished = _time(source.get("finished_at_utc"))
                h, a = source.get("home_goals"), source.get("away_goals")
                if (result_ko != item["kickoff"] or finished > now
                        or finished < result_ko + timedelta(minutes=90)
                        or type(h) is not int or type(a) is not int
                        or h < 0 or a < 0 or h > 50 or a > 50):
                    raise ValueError("INVALID_FINAL_RESULT")
                result_status = "OBSERVED_NOT_INDEPENDENTLY_VERIFIED"
                if item["decimal_odds"] is not None:
                    net = _settle(item, h, a)
                    if not isfinite(net):
                        raise ValueError("INVALID_NET")
                    grade = _grade(net, item["decimal_odds"])
            except (ValueError, TypeError, OverflowError):
                result_status = "INVALID_FINAL_RESULT"
                net, grade = None, None
        if result_status == "OBSERVED_NOT_INDEPENDENTLY_VERIFIED" and net is not None:
            aggregate["scored_research_only"] += 1
            aggregate["hypothetical_net_units"] += net
            aggregate["settlement_grades"][grade] += 1
        else:
            aggregate["pending_or_unverifiable"] += 1
            if item["decimal_odds"] is None:
                aggregate["missing_usable_price"] += 1
        cases.append({
            "selection_id": item["selection_id"], "fixture_id": event,
            "decision": decision, "market": item["market"],
            "selection": item["selection"], "line": str(item["line"]),
            "result_status": result_status,
            "settlement_grade_research_only": grade,
            "hypothetical_net_units": round(net, 6) if net is not None else None,
            "score_source_independently_verified": False,
            "prematch_capture_independently_attested": False,
        })
    for group in by_decision.values():
        group["hypothetical_net_units"] = round(group["hypothetical_net_units"], 6)
        group["hypothetical_roi_settled_only"] = (
            round(group["hypothetical_net_units"] / group["scored_research_only"], 6)
            if group["scored_research_only"] else None)
    return {
        "schema": "football-king-complete-watchlist-research-review-v1",
        "status": "RESEARCH_ONLY" if any(
            x["scored_research_only"] for x in by_decision.values()) else "HOLD",
        "checked_at_utc": now.isoformat(),
        "predeclared_count": len(cohort),
        "manifest_local_sha256": manifest_digest,
        "manifest_pin_matches_content": pinned,
        "manifest_pin_kind": "LOCAL_UNATTESTED" if pinned else "NONE",
        "manifest_digest_is_external_attestation": False,
        "distinct_fixtures": len({x["fixture_id"] for x in cohort}),
        "all_decisions_retained": True,
        "results_independently_verified": False,
        "prematch_manifest_independently_attested": False,
        "traded_prices_verified": False,
        "hypothetical_returns_are_actual_bets": False,
        "model_improvement_verified": False,
        "production_recommendations": "DISABLED",
        "by_decision": by_decision,
        "cases": cases,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--watchlist", required=True)
    parser.add_argument("--results")
    parser.add_argument("--checked-at-utc")
    parser.add_argument("--manifest-pin",
                        help="Previously stored local pin JSON; not external attestation")
    parser.add_argument("--seal-only", action="store_true",
                        help="Prepare an UNATTESTED content pin before kickoff")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    watchlist = json.loads(Path(args.watchlist).read_text(encoding="utf-8"))
    if args.seal_only:
        if args.results or args.checked_at_utc or args.manifest_pin:
            parser.error("--seal-only requires only --watchlist and --output")
        # The normal CLI cannot take a caller-supplied/backdated issue clock.
        # This is still a LOCAL, NOT externally attested receipt.
        result = seal_manifest(watchlist,
                               issued_at_utc=datetime.now(timezone.utc).isoformat())
        summary = {"selection_count": result["selection_count"],
                   "external_attestation_verified": False,
                   "production_recommendations": "DISABLED"}
    else:
        if not args.results or not args.checked_at_utc:
            parser.error("review requires --results and --checked-at-utc")
        pin = (json.loads(Path(args.manifest_pin).read_text(encoding="utf-8"))
               if args.manifest_pin else None)
        result = review(watchlist,
                        json.loads(Path(args.results).read_text(encoding="utf-8")),
                        checked_at_utc=args.checked_at_utc, manifest_pin=pin)
        summary = {"status": result["status"],
                   "predeclared_count": result["predeclared_count"],
                   "manifest_pin_matches_content": result["manifest_pin_matches_content"],
                   "production_recommendations": "DISABLED"}
    # Never clobber prior local pins, other review outputs, or input JSON.
    # The new file is owner-readable only; O_EXCL also blocks symlink aliases.
    write_new_private_json(args.output, result)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    main()
