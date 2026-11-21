"""Offline HKJC-line *reference* triage, never a quote/EV/forecast verifier.

A mirror's claimed HKJC price is NOT an authenticated HKJC bookmaker quote.
A human-transcribed official screenshot is NOT an authenticated feed event.
No network, scraping, betting, or public redistribution of raw prices.
"""
import math
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

SOURCE_HOSTS = {
    "HKJC_MANUAL_REFERENCE": frozenset({"football.hkjc.com"}),
    "THIRD_PARTY_HKJC_MIRROR": frozenset({"bogo.hk", "playplay.football"}),
}
MARKET_SELECTIONS = {
    "FT_1X2": frozenset({"HOME", "DRAW", "AWAY"}),
    "ASIAN_HANDICAP": frozenset({"HOME", "AWAY"}),
    "TOTALS": frozenset({"OVER", "UNDER"}),
}
REQUIRED = frozenset({
    "source_type", "source_url", "source_fixture_id", "home", "away",
    "kickoff_utc", "source_updated_utc", "captured_utc", "market",
    "selection", "line", "price_format", "price",
})
MAX_AGE = timedelta(minutes=10)
MIN_TO_KICKOFF = timedelta(minutes=5)


def _time(value):
    if type(value) is not str:
        raise ValueError("MISSING_SOURCE_OR_CAPTURE_TIME")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if parsed.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return parsed.astimezone(timezone.utc)


def _valid_url(url, source_type):
    if type(url) is not str or len(url) > 1500:
        return False
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname in SOURCE_HOSTS[source_type]
                and parsed.username is None and parsed.password is None
                and parsed.port is None and not parsed.fragment and not parsed.query)
    except (KeyError, ValueError):
        return False


def _reference_decimal(price, price_format):
    """Normalize format for a private structural threshold test ONLY."""
    if type(price) not in (float, int) or not math.isfinite(price):
        raise ValueError("INVALID_REFERENCE_PRICE")
    if price_format == "HK_ODDS_WATER" and 0.01 <= price <= 20:
        return float(price) + 1.0
    if price_format == "DECIMAL" and 1.01 <= price <= 100:
        return float(price)
    raise ValueError("INVALID_PRICE_FORMAT_OR_RANGE")


def audit(snapshot, *, as_of_utc):
    """Check source claims and freshness. NEVER certify EV/tradability.

    The return omits source's raw price and normalized price to avoid
    republishing unlicensed third-party quote data.
    """
    out = {
        "status": "HOLD", "reason": "INVALID_INPUT",
        "research_only": True, "source_kind": None,
        "reference_price_at_least_1_80": False,
        "line_quarters": None, "market": None, "selection": None,
        "source_original_update_authenticated": False,
        "official_hkjc_quote_authenticated": False,
        "licensed_executable_quote_verified": False,
        "formal_prematch_prediction_sealed": False,
        "positive_ev_verified": False, "betting_authorized": False,
        "eligible_for_formal_forward_scoring": False,
        "production_recommendations": "DISABLED",
    }
    try:
        if type(snapshot) is not dict or set(snapshot) != REQUIRED:
            raise ValueError("MISSING_OR_EXTRA_FIELDS")
        source = snapshot["source_type"]
        if source not in SOURCE_HOSTS or not _valid_url(snapshot["source_url"], source):
            raise ValueError("UNTRUSTED_OR_MISMATCHED_SOURCE_URL")
        out["source_kind"] = source
        names = (snapshot["source_fixture_id"], snapshot["home"], snapshot["away"])
        if (any(type(x) is not str or not x.strip() or len(x) > 128 for x in names)
                or snapshot["home"].casefold() == snapshot["away"].casefold()):
            raise ValueError("MISSING_OR_AMBIGUOUS_FIXTURE_IDENTITY")
        market, side = snapshot["market"], snapshot["selection"]
        if market not in MARKET_SELECTIONS or side not in MARKET_SELECTIONS[market]:
            raise ValueError("UNSUPPORTED_MARKET_OR_SELECTION")
        out["market"], out["selection"] = market, side
        line = snapshot["line"]
        if market == "FT_1X2":
            if line is not None or snapshot["price_format"] != "DECIMAL":
                raise ValueError("INVALID_1X2_POINT_OR_FORMAT")
        else:
            if (type(line) not in (int, float) or not math.isfinite(line)
                    or (market == "TOTALS" and not (0.25 <= line <= 20))
                    or (market == "ASIAN_HANDICAP" and not (-10 <= line <= 10))
                    or abs(line * 4 - round(line * 4)) > 1e-8):
                raise ValueError("INVALID_ASIAN_QUARTER_POINT")
            out["line_quarters"] = int(round(line * 4))
        fmt = snapshot["price_format"]
        # A 1X2 quote must be decimal: a Hong Kong water price would refer
        # to a different market with a different settlement structure.
        if fmt not in ({"DECIMAL"} if market == "FT_1X2"
                       else {"DECIMAL", "HK_ODDS_WATER"}):
            raise ValueError("INVALID_MARKET_ODDS_FORMAT")
        decimal = _reference_decimal(snapshot["price"], fmt)
        out["reference_price_at_least_1_80"] = decimal >= 1.80
        now = _time(as_of_utc)
        kickoff = _time(snapshot["kickoff_utc"])
        updated = _time(snapshot["source_updated_utc"])
        captured = _time(snapshot["captured_utc"])
        if (not timedelta(0) <= now - captured <= MAX_AGE
                or not timedelta(0) <= captured - updated <= MAX_AGE
                or not timedelta(0) <= now - updated <= MAX_AGE):
            raise ValueError("STALE_OR_FUTURE_SOURCE_TIME")
        if (kickoff - now < MIN_TO_KICKOFF or updated >= kickoff
                or captured >= kickoff):
            raise ValueError("IN_PLAY_OR_TOO_CLOSE_TO_KICKOFF")
        return {**out, "status": "RESEARCH_ONLY",
                "reason": ("THIRD_PARTY_MIRROR_NOT_HKJC_AUTHENTICATED"
                           if source == "THIRD_PARTY_HKJC_MIRROR"
                           else "MANUAL_REFERENCE_NOT_HKJC_AUTHENTICATED")}
    except (ValueError, TypeError, OverflowError, KeyError) as exc:
        # Bad sources, stale quotes and fake clocks cannot pass into the model.
        return {**out, "reason": str(exc)}
