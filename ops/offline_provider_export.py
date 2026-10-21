"""Convert documented fixture/odds export into daily research input.

This is an offline adapter, NOT a live odds feed. Export must supply a source
record for every fixture and quote. No missing prices or dates are invented.
"""
from datetime import datetime, timezone

def _utc(s):
    if not isinstance(s, str):
        raise ValueError("MISSING_TIME")
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("INVALID_TIME") from None
    if d.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return d.astimezone(timezone.utc)

def adapt_export(export, *, generated_utc):
    """Expect {source,fixtures:[{id,home,away,kickoff_utc,quotes:[...]}]}.

    Quote fields: id, bookmaker, market, selection, line, decimal_odds,
    quote_utc. Only the latest PREMATCH quote per fixture is used; selecting
    one is not a betting recommendation or price-execution verification.
    """
    now = _utc(generated_utc)
    if not isinstance(export, dict) or not isinstance(export.get("source"), str) or not export["source"].strip():
        raise ValueError("MISSING_SOURCE")
    fixtures = export.get("fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("INVALID_FIXTURES")
    rows = []
    for f in fixtures:
        if not isinstance(f, dict):
            raise ValueError("INVALID_FIXTURE")
        fixture_id = f.get("id")
        if not isinstance(fixture_id, str) or not fixture_id.strip():
            raise ValueError("MISSING_FIXTURE_ID")
        kickoff = _utc(f.get("kickoff_utc"))
        quotes = f.get("quotes", [])
        if not isinstance(quotes, list):
            raise ValueError("INVALID_QUOTES")
        candidates = []
        for q in quotes:
            if not isinstance(q, dict):
                raise ValueError("INVALID_QUOTE")
            quoted = _utc(q.get("quote_utc"))
            if quoted > now or quoted >= kickoff:
                continue
            candidates.append((quoted, q))
        chosen = max(candidates, key=lambda x: x[0])[1] if candidates else None
        quote = None
        if chosen is not None:
            quote = {
                "provider": export["source"], "fixture_id": fixture_id,
                "provider_quote_id": chosen.get("id"),
                "bookmaker": chosen.get("bookmaker"), "market": chosen.get("market"),
                "selection": chosen.get("selection"), "line": chosen.get("line"),
                "decimal_odds": chosen.get("decimal_odds"),
                "quote_utc": chosen.get("quote_utc")
            }
        rows.append({
            "fixture_id": fixture_id, "home_team": f.get("home"),
            "away_team": f.get("away"), "kickoff_utc": f.get("kickoff_utc"),
            "quote": quote
        })
    return {"generated_utc": now.isoformat(), "rows": rows,
            "source_independently_verified": False,
            "production_recommendations": "HOLD"}
