"""Classify free research-market fallback without inventing executable odds.

The Odds API no-vig probabilities and BSD free consensus are research baselines.
Even when a backup works, this module never replaces a primary quote or
authorizes EV/betting recommendations. Source timestamps are mandatory.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def utc(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_MARKET_TIME")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("NAIVE_MARKET_TIME")
    return result.astimezone(timezone.utc)


def fresh(value, now, hours):
    try:
        d = now - utc(value)
        return timedelta(minutes=-5) <= d <= timedelta(hours=hours)
    except (ValueError, TypeError, OverflowError):
        return False


def route(primary, bsd, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    primary_ok = (isinstance(primary, dict)
                  and primary.get("source_state") == "RESEARCH_ONLY"
                  and primary.get("production_recommendations") == "DISABLED"
                  and type(primary.get("matched_count")) is int
                  and primary["matched_count"] > 0
                  and fresh(primary.get("market_as_of_utc"), now, 16))
    bsd_ok = (isinstance(bsd, dict)
              and bsd.get("status") == "RESEARCH_ONLY"
              and bsd.get("source_state") == "RESEARCH_ONLY"
              and bsd.get("production_recommendations") == "DISABLED"
              and bsd.get("market_is_executable") is False
              and bsd.get("automatic_replacement_of_main_market") is False
              and type(bsd.get("time_valid_shadow_pairs")) is int
              and bsd["time_valid_shadow_pairs"] > 0
              and fresh(bsd.get("last_source_checked_utc"), now, 12)
              and fresh(bsd.get("created_utc"), now, 12))
    if primary_ok:
        status = "PRIMARY_RESEARCH_CONSENSUS"
        source = "the_odds_api_derived_probability"
    elif bsd_ok:
        status = "BSD_FREE_RESEARCH_CONSENSUS_BACKUP"
        source = "bsd_free_derived_consensus"
    else:
        status = "NO_FRESH_COMPARABLE_RESEARCH_MARKET"
        source = None
    return {
        "schema": "football-king-research-market-failover-v1",
        "generated_utc": now.isoformat(),
        "status": status,
        "source_used_for_research_context": source,
        "primary_time_valid_pairs": primary.get("matched_count", 0) if primary_ok else 0,
        "bsd_time_valid_pairs": bsd.get("time_valid_shadow_pairs", 0) if bsd_ok else 0,
        "historical_market_basis_only": True,
        "executable_bookmaker_quote_available": False,
        "positive_ev_verified": False,
        "automatic_primary_market_substitution": False,
        "production_recommendations": "DISABLED",
        "reason": ("NO_AUTHENTICATED_EXECUTABLE_BOOKMAKER_PRICE"
                   if source is not None else "NO_FRESH_RESEARCH_CONSENSUS_OR_EXECUTABLE_ODDS"),
    }


def publish(site):
    site = Path(site)
    def read(name):
        try:
            obj = json.loads((site / name).read_text(encoding="utf-8"))
            return obj if isinstance(obj, dict) else None
        except (OSError, UnicodeError, ValueError):
            return None
    out = route(read("market_status.json"), read("bsd_backup.json"))
    (site / "research_market_failover.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="app/site")
    publish(Path(p.parse_args().site))
