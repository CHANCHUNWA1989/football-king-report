"""Research-only matching of forecasts to earlier free market snapshots."""
import argparse
import hashlib
import json
import math
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from team_identity import team_id


def iso(v):
    t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("naive time")
    return t.astimezone(timezone.utc)


def identity(s):
    if not isinstance(s, str):
        return ""
    return "".join(c for c in unicodedata.normalize("NFKD", s.casefold())
                   if c.isalnum() and not unicodedata.combining(c))


def vector(row):
    try:
        v = [float(row[k]) for k in ("p_home", "p_draw", "p_away")]
        return v if all(math.isfinite(n) and 0 <= n <= 1 for n in v) and abs(sum(v)-1)<.001 else None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def variant_vector(forecast):
    if not isinstance(forecast,dict):
        return None
    rows={}
    for plain,field in (("home","ab_candidate_p_home"),("draw","ab_candidate_p_draw"),
                        ("away","ab_candidate_p_away")):
        rows["p_"+plain]=forecast.get(field)
    if any(v is None for v in rows.values()):
        return None
    return vector(rows)


def pair(shadow, market):
    out = {"status": "HOLD", "reason": "NO_VALID_DATA", "matched_count": 0,
           "exclusions": {}, "comparisons": [], "production_recommendations": "DISABLED"}
    if not isinstance(shadow, dict) or not isinstance(market, dict):
        return out
    forecasts = shadow.get("predictions")
    quotes = market.get("events")
    if (shadow.get("status") != "SHADOW_ONLY" or market.get("status") != "RESEARCH_ONLY"
            or not isinstance(forecasts, list) or not isinstance(quotes, list)
            or shadow.get("production_recommendations") != "DISABLED"
            or market.get("production_recommendations") != "DISABLED"):
        return out
    try:
        forecast_at, market_at = iso(shadow["as_of_utc"]), iso(market["as_of_utc"])
    except (TypeError, ValueError, KeyError):
        out["reason"] = "INVALID_TIME"
        return out
    lag = (forecast_at - market_at).total_seconds()
    if not 0 <= lag <= 750*60:
        out["reason"] = "MARKET_NOT_PRIOR_OR_TOO_OLD"
        return out
    # Index each validated market observation once. Previously every forecast
    # scanned every quote (quadratic work for multi-league fixture catalogues).
    # Index remains league-scoped and conservative; no fuzzy matching.
    market_index = {}
    for m in quotes:
        if not isinstance(m, dict) or vector(m) is None or not m.get("source_event_id"):
            continue
        league = m.get("league")
        home_id = team_id(league, m.get("home"))
        away_id = team_id(league, m.get("away"))
        if not home_id or not away_id or home_id == away_id:
            continue
        try:
            quote_kickoff = iso(m["kickoff_utc"])
            quote_updated = iso(m["market_last_update_utc"])
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
            continue
        if quote_updated > market_at:
            continue
        market_index.setdefault((league, home_id, away_id), []).append(
            (m, quote_kickoff, quote_updated))
    paired_market_ids = set()
    alias_matches = 0
    for f in forecasts:
        why, hits = None, []
        try:
            if f.get("production_recommendations") != "DISABLED" or vector(f) is None:
                raise ValueError("INVALID_FORECAST")
            pred, kickoff = iso(f["prediction_utc"]), iso(f["kickoff_utc"])
            if (abs((pred-forecast_at).total_seconds())>120
                    or market_at > pred
                    or (kickoff-pred).total_seconds()<=600):
                raise ValueError("INVALID_FORECAST_TIME")
            home_id = team_id(f.get("league"), f.get("home"))
            away_id = team_id(f.get("league"), f.get("away"))
            if not home_id or not away_id or home_id == away_id:
                raise ValueError("INVALID_FORECAST_TEAMS")
            for m, quote_kickoff, quote_updated in market_index.get(
                    (f.get("league"), home_id, away_id), []):
                if (abs((quote_kickoff - kickoff).total_seconds()) <= 2700
                        and quote_updated <= pred):
                    hits.append(m)
            if len(hits) != 1:
                why = "AMBIGUOUS_MARKET_MATCH" if hits else "NO_EXACT_TIME_VALID_MARKET_MATCH"
            else:
                m = hits[0]
                market_key = (f.get("league"), str(m["source_event_id"]))
                if market_key in paired_market_ids:
                    raise ValueError("MARKET_ALREADY_PAIRED")
                paired_market_ids.add(market_key)
                if (identity(m.get("home")) != identity(f.get("home"))
                        or identity(m.get("away")) != identity(f.get("away"))):
                    alias_matches += 1
                fingerprint = hashlib.sha256(
                    (str(f.get("league"))+str(m["source_event_id"])+pred.isoformat()).encode()).hexdigest()
                out["comparisons"].append({
                    "case_id": fingerprint, "league": f["league"],
                    "home": f["home"], "away": f["away"],
                    "kickoff_utc": kickoff.isoformat(), "prediction_utc": pred.isoformat(),
                    "market_snapshot_utc": market_at.isoformat(),
                    "market_updated_utc": m["market_last_update_utc"],
                    "market_event_id": m["source_event_id"],
                    "model": vector(f), "market": vector(m),
                    "ab": variant_vector(f),
                    "ab_model": f.get("ab_model") if variant_vector(f) else None,
                    "result": None, "historical_outcome": None, "available_for_betting": False,
                    "production_recommendations": "DISABLED"})
        except ValueError as exc:
            why = ("MARKET_ALREADY_PAIRED" if str(exc) == "MARKET_ALREADY_PAIRED"
                   else "INVALID_FORECAST_OR_QUOTE")
        except (KeyError, TypeError, AttributeError):
            why = "INVALID_FORECAST_OR_QUOTE"
        if why:
            out["exclusions"][why] = out["exclusions"].get(why, 0) + 1
    out["matched_count"] = len(out["comparisons"])
    out["verified_alias_pairs"] = alias_matches
    out["matching_policy"] = "explicit-league-scoped-alias-or-exact; no-fuzzy-match"
    out["reason"] = "NO_TIME_VALID_UNAMBIGUOUS_PAIRS" if not out["matched_count"] else "UNSETTLED_RESEARCH_PAIRS"
    out["status"] = "RESEARCH_ONLY" if out["matched_count"] else "HOLD"
    return out


def publish(site, market_file):
    site = Path(site)
    shadow = json.loads((site/"shadow.json").read_text(encoding="utf-8"))
    p = Path(market_file)
    market = {"status": "HOLD", "events": [],
              "production_recommendations": "DISABLED"}
    if p.is_file():
        try:
            incoming = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(incoming, dict):
                market = incoming
        except (OSError, UnicodeError, ValueError):
            # Corrupt or partial quota-limited uploads should not crash the
            # entire mobile publication. Fail closed, never invent quotes.
            pass
    paired = pair(shadow, market)
    collection_path = Path("market/collection_status.json")
    collection = {}
    if collection_path.is_file():
        try:
            raw = json.loads(collection_path.read_text(encoding="utf-8"))
            if (raw.get("schema") == "football-king-free-market-collection-status-v1"
                    and raw.get("production_recommendations") == "DISABLED"
                    and raw.get("collection_status") in ("RESEARCH_ONLY", "HOLD")):
                collection = raw
        except (json.JSONDecodeError, UnicodeError, OSError, AttributeError):
            collection = {}
    summary = {k:v for k,v in paired.items() if k != "comparisons"}
    summary.update({"source": "The Odds API (de-vigged EU 1X2 research)",
                    "source_state": market["status"],
                    "market_as_of_utc": market.get("as_of_utc"),
                    "model_as_of_utc": shadow.get("as_of_utc"),
                    "market_events": market.get("event_count", 0),
                    "model_events": len(shadow.get("predictions", [])),
                    "quota": collection.get("quota") if collection else market.get("quota"),
                    "last_collection_state": collection.get("collection_status"),
                    "last_collection_reason": collection.get("collection_reason"),
                    "last_collection_at_utc": collection.get("as_of_utc"),
                    "no_executable_odds_or_return_claims": True})
    (site/"market_status.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
    (site/"market_comparison.json").write_text(json.dumps(paired,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return summary


if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--site",default="app/site")
    a.add_argument("--market",default="market/latest.json")
    x=a.parse_args()
    print(json.dumps(publish(x.site,x.market),ensure_ascii=False))
