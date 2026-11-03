"""Fail-closed research-only audit of manually supplied in-play evidence.

Does not fetch bookmaker prices, calculate EV, publish picks or unlock production.
Fresh capture time alone does not prove upstream freshness or source authenticity.
"""
import argparse
import json
import math
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from pathlib import Path


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("TIMESTAMP_MISSING")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMEZONE_MISSING")
    return dt.astimezone(timezone.utc)


def _check_corner_fixture_binding(snapshot, fixture, kickoff):
    """Match native provider event identities to a separately supplied fixture map.

    The map must have been DECLARED before kickoff; this function cannot
    authenticate that claimed registration time or any upstream provider.
    It is consistency checking, not cryptographic provenance validation.
    """
    if fixture is None:
        raise ValueError("TRUSTED_FIXTURE_REQUIRED")
    if not isinstance(fixture, dict):
        raise ValueError("INVALID_FIXTURE_BINDING")
    if (fixture.get("event_id") != snapshot["event_id"]
            or not isinstance(fixture.get("kickoff_utc"), str)
            or _utc(fixture["kickoff_utc"]) != kickoff):
        raise ValueError("FIXTURE_BINDING_CONFLICT")
    registered = _utc(fixture["registered_at_utc"])
    if registered > kickoff - timedelta(minutes=10):
        raise ValueError("FIXTURE_NOT_PRE_REGISTERED")
    providers = fixture.get("source_events")
    required = ("score", "stats", "quote")
    if not isinstance(providers, dict) or set(providers) != set(required):
        raise ValueError("INVALID_FIXTURE_BINDING")
    for channel in required:
        source = providers[channel]
        observed = snapshot[channel]
        if not isinstance(source, dict):
            raise ValueError("INVALID_FIXTURE_BINDING")
        for field in ("source", "source_event_id", "source_url"):
            expected = source.get(field)
            actual = observed.get(field)
            if (not isinstance(expected, str) or not expected.strip()
                    or len(expected) > 2048):
                raise ValueError("INVALID_FIXTURE_BINDING")
            if field == "source_url":
                try:
                    parsed = urlsplit(expected)
                    if (parsed.scheme != "https" or not parsed.hostname
                            or parsed.username is not None
                            or parsed.password is not None
                            or parsed.port is not None or parsed.fragment
                            or len(expected) > 2048):
                        raise ValueError("INVALID_SOURCE_URL")
                except ValueError as exc:
                    raise ValueError("INVALID_SOURCE_URL") from exc
            if type(actual) is not str or actual != expected:
                raise ValueError("SOURCE_EVENT_IDENTITY_CONFLICT")


def audit_live_snapshot(snapshot, *, max_age_seconds=90, trusted_fixture=None):
    """Audit one consistent evidence cut; never certify positive EV.

    Required quote line is the signed handicap on the selected side, or the
    total-goals/total-corners threshold. This validator checks only structure and timing,
    NOT the vendor's licence, true bookability or probability calibration.
    """
    out = {
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "certified_positive_ev": False,
        "source_authenticity_verified": False,
        "market_executable_verified": False,
        "probability_calibrated": False,
        "reasons": [],
    }
    if not isinstance(snapshot, dict):
        out["reasons"].append("INVALID_SNAPSHOT")
        return out
    try:
        if (type(max_age_seconds) not in (int, float)
                or not math.isfinite(max_age_seconds)
                or not 0 < max_age_seconds <= 300):
            raise ValueError("INVALID_AGE_LIMIT")
        event_id = snapshot["event_id"]
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("EVENT_ID_MISSING")
        now = _utc(snapshot["decision_utc"])
        kickoff = _utc(snapshot["kickoff_utc"])
        if now < kickoff:
            raise ValueError("NOT_IN_PLAY")
        records = {key: snapshot[key] for key in ("score", "stats", "quote")}
        if not all(isinstance(r, dict) for r in records.values()):
            raise ValueError("INVALID_RECORD")
        upstream_times = {}
        for key, record in records.items():
            if record.get("event_id") != event_id:
                raise ValueError("EVENT_ID_MISMATCH")
            if not isinstance(record.get("source"), str) or not record["source"].strip():
                raise ValueError("SOURCE_MISSING")
            updated = _utc(record["upstream_updated_utc"])
            captured = _utc(record["captured_utc"])
            if not kickoff <= updated <= captured <= now:
                raise ValueError("INVALID_TIME_ORDER")
            if (now - updated).total_seconds() > max_age_seconds:
                raise ValueError("STALE_UPSTREAM")
            upstream_times[key] = updated

        # A scoreboard source may update its clock every second. Compare
        # sources against the LAST MATERIAL EVENT (goal, red card or VAR
        # correction), not against mere scoreboard clock-heartbeat time.
        # The event timestamp must be supplied by traceable match evidence;
        # never silently infer it from the latest score or capture timestamp.
        score = records["score"]
        material = _utc(score["last_material_event_utc"])
        if not kickoff <= material <= upstream_times["score"]:
            raise ValueError("INVALID_MATERIAL_EVENT_TIME")
        if upstream_times["stats"] < material:
            raise ValueError("STATS_BEFORE_MATERIAL_EVENT")
        if upstream_times["quote"] < material:
            raise ValueError("QUOTE_BEFORE_MATERIAL_EVENT")

        if (type(score.get("home_goals")) is not int
                or type(score.get("away_goals")) is not int
                or min(score["home_goals"], score["away_goals"]) < 0):
            raise ValueError("INVALID_SCORE")

        stats = records["stats"]
        quote = records["quote"]
        market = quote.get("market")
        selection = quote.get("selection")
        if market == "corners_totals":
            _check_corner_fixture_binding(snapshot, trusted_fixture, kickoff)
            # An apparently fresh live quote is not evidence that the
            # underlying match is still in regulation play. Require an
            # explicit score-source status, never infer it from quote.in_play.
            match_status = score.get("match_status")
            valid_statuses = ("FIRST_HALF", "HALF_TIME", "SECOND_HALF")
            if type(match_status) is not str or match_status not in valid_statuses:
                raise ValueError("MATCH_STATUS_MISSING_OR_INVALID")
            elapsed = (now - kickoff).total_seconds()
            # Broad windows are an anomaly check, not an exact match clock.
            # Scheduled kickoff drift cannot be used to certify source status.
            if ((match_status == "FIRST_HALF" and elapsed > 75 * 60)
                    or (match_status == "HALF_TIME"
                        and not 35 * 60 <= elapsed <= 100 * 60)
                    or (match_status == "SECOND_HALF"
                        and not 40 * 60 <= elapsed <= 150 * 60)):
                raise ValueError("MATCH_STATUS_CLOCK_CONFLICT")
            if selection not in ("over", "under"):
                raise ValueError("CORNER_SELECTION_MISSING")
            counts = []
            for key in ("home_corners", "away_corners"):
                value = stats.get(key)
                if type(value) is not int or not 0 <= value <= 200:
                    raise ValueError("INVALID_CORNER_COUNT")
                counts.append(value)
            # This is the time of the latest actual corner, not a clock tick.
            # When no corners occurred, the kickoff is the only valid anchor.
            last_corner = _utc(stats["last_corner_event_utc"])
            if not kickoff <= last_corner <= now:
                raise ValueError("INVALID_CORNER_EVENT_TIME")
            if not sum(counts) and last_corner != kickoff:
                raise ValueError("INVALID_ZERO_CORNER_ANCHOR")
            if sum(counts) and last_corner <= kickoff:
                raise ValueError("INVALID_CORNER_EVENT_ANCHOR")
            if upstream_times["stats"] < last_corner:
                raise ValueError("STATS_BEFORE_CORNER_EVENT")
            if upstream_times["quote"] < last_corner:
                raise ValueError("QUOTE_BEFORE_CORNER_EVENT")
        else:
            for key in ("home_xg", "away_xg"):
                value = stats.get(key)
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError("INVALID_XG")
            if market == "totals":
                if selection not in ("over", "under"):
                    raise ValueError("TOTAL_SELECTION_MISSING")
            elif market == "asian_handicap":
                if selection not in ("home", "away"):
                    raise ValueError("HANDICAP_SELECTION_MISSING")
            else:
                raise ValueError("UNSUPPORTED_MARKET")
        if quote.get("in_play") is not True:
            raise ValueError("NOT_LIVE_QUOTE")
        line, price = quote.get("line"), quote.get("decimal_price")
        if (type(line) not in (float, int) or not math.isfinite(line)
                or type(price) not in (float, int) or not math.isfinite(price)
                or price <= 1 or abs(line * 4 - round(line * 4)) > 1e-9):
            raise ValueError("INVALID_QUOTE")
        if market in ("totals", "corners_totals") and line < 0:
            raise ValueError("INVALID_TOTAL_LINE")
        if market == "corners_totals" and sum(counts) > line:
            raise ValueError("CORNER_MARKET_ALREADY_DECIDED")
        if not isinstance(quote.get("bookmaker"), str) or not quote["bookmaker"].strip():
            raise ValueError("BOOKMAKER_MISSING")

        out["status"] = "RESEARCH_ONLY"
        out["reasons"] = ["TIMING_CHECK_PASSED_NOT_VERIFIED_EV"]
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        reason = str(exc).strip("'") if str(exc) else "INVALID_DATA"
        out["reasons"].append(reason)
    return out


def main(argv=None):
    """Standalone offline check of authorized JSON evidence; no network calls."""
    parser = argparse.ArgumentParser(description="In-play research input safety check; never a betting signal")
    parser.add_argument("snapshot", type=Path, help="Local JSON with score, stats and in-play market evidence")
    parser.add_argument("--fixture-manifest", type=Path, default=None,
                        help="Separate, pre-registered fixture/provider ID map for corner totals")
    args = parser.parse_args(argv)
    try:
        if args.snapshot.stat().st_size > 512_000:
            raise ValueError("INPUT_TOO_LARGE")
        with args.snapshot.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        # Always evaluate freshness relative to the actual execution clock.
        # A snapshot must not arbitrarily claim an earlier decision clock.
        if not isinstance(payload, dict):
            raise ValueError("INVALID_SNAPSHOT")
        payload["decision_utc"] = datetime.now(timezone.utc).isoformat()
        fixture = None
        if args.fixture_manifest is not None:
            if args.fixture_manifest.stat().st_size > 64_000:
                raise ValueError("FIXTURE_MANIFEST_TOO_LARGE")
            with args.fixture_manifest.open(encoding="utf-8") as handle:
                fixture = json.load(handle)
        result = audit_live_snapshot(payload, trusted_fixture=fixture)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        result = {
            "status": "HOLD",
            "production_recommendations": "DISABLED",
            "certified_positive_ev": False,
            "reasons": [str(exc) if str(exc) else "INPUT_READ_FAILED"],
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "RESEARCH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
