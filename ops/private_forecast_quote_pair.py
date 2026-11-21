"""Private, offline 1X2 quote/forecast pairing research.

Never serialize raw bookmaker quotes to public Actions artifacts. Inputs are
caller-supplied, not authenticated or certified by this module.
"""
import math
from datetime import datetime, timezone

SCHEMA = "football-king-private-forecast-quote-pair-v1"


def _time(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIMESTAMP")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return stamp.astimezone(timezone.utc)


def _hold(reason, **details):
    return {"schema": SCHEMA, "status": "HOLD", "reason": reason,
            "production_recommendations": "DISABLED",
            "positive_ev_verified": False, "independent_provenance_verified": False,
            "recommendation_ready": False, **details}


def pair(payload, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        return _hold("INVALID_NOW")
    if (not isinstance(payload, dict) or set(payload) !=
            {"schema", "production_recommendations", "forecasts", "quotes"}
            or payload.get("schema") != SCHEMA
            or payload.get("production_recommendations") != "DISABLED"):
        return _hold("INVALID_CONTRACT")
    forecasts, quotes = payload["forecasts"], payload["quotes"]
    if (not isinstance(forecasts, list) or not isinstance(quotes, list)
            or len(forecasts) > 250 or len(quotes) > 10000):
        return _hold("INVALID_COHORT")
    try:
        by_fixture = {}
        for f in forecasts:
            if not isinstance(f, dict) or set(f) != {
                "fixture_id", "kickoff_utc", "forecast_utc", "probabilities",
                "model_id", "source_authenticity_verified", "independently_timestamped"
            }:
                raise ValueError("INVALID_FORECAST")
            key = f["fixture_id"]
            if not isinstance(key, str) or not key.strip() or key in by_fixture:
                raise ValueError("DUPLICATE_FORECAST")
            if not isinstance(f["model_id"], str) or not f["model_id"].strip():
                raise ValueError("INVALID_MODEL")
            if (f["source_authenticity_verified"] is not False
                    or f["independently_timestamped"] is not False):
                raise ValueError("SELF_CERTIFIED_FORECAST")
            kick, cutoff = _time(f["kickoff_utc"]), _time(f["forecast_utc"])
            if not cutoff < kick or not now < kick:
                raise ValueError("FORECAST_NOT_PREMATCH")
            probs = f["probabilities"]
            if (not isinstance(probs, dict) or set(probs) != {"H", "D", "A"}
                    or any(type(v) not in (int, float) or not math.isfinite(v)
                           or not 0 <= v <= 1 for v in probs.values())
                    or abs(sum(probs.values()) - 1) > 1e-6):
                raise ValueError("INVALID_PROBABILITIES")
            by_fixture[key] = f
        seen = set()
        matches = []
        rejected = {"UNMATCHED_FIXTURE": 0, "STALE_QUOTE": 0, "INVALID_QUOTE": 0}
        for q in quotes:
            if not isinstance(q, dict) or set(q) != {
                "fixture_id", "kickoff_utc", "observed_utc", "market",
                "selection", "decimal_odds", "source", "quote_id"
            }:
                raise ValueError("INVALID_QUOTE_CONTRACT")
            identity = (q["fixture_id"], q["quote_id"])
            if (not isinstance(q["fixture_id"], str) or
                    not isinstance(q["quote_id"], str) or not q["quote_id"] or
                    identity in seen):
                raise ValueError("DUPLICATE_OR_INVALID_QUOTE_ID")
            seen.add(identity)
            f = by_fixture.get(q["fixture_id"])
            if f is None:
                rejected["UNMATCHED_FIXTURE"] += 1
                continue
            if (q["market"] != "h2h" or q["selection"] not in ("H", "D", "A")
                    or not isinstance(q["source"], str) or not q["source"].strip()
                    or type(q["decimal_odds"]) not in (int, float)
                    or not math.isfinite(q["decimal_odds"])
                    or not 1.01 <= q["decimal_odds"] <= 100):
                rejected["INVALID_QUOTE"] += 1
                continue
            if q["kickoff_utc"] != f["kickoff_utc"]:
                rejected["INVALID_QUOTE"] += 1
                continue
            observed = _time(q["observed_utc"])
            if (observed >= _time(f["kickoff_utc"]) or observed > now
                    or (now - observed).total_seconds() > 1200):
                rejected["STALE_QUOTE"] += 1
                continue
            p = f["probabilities"][q["selection"]]
            ev = p * q["decimal_odds"] - 1
            # No price, bookmaker, quote ID or provider identity in the report.
            matches.append({"fixture_id": f["fixture_id"], "selection": q["selection"],
                            "model_id": f["model_id"], "model_probability": round(p, 6),
                            "research_ev_per_unit": round(ev, 6),
                            "research_only": True, "independently_verified": False})
        return _hold("UNVERIFIED_MODEL_PROVENANCE_AND_EXECUTABILITY",
                     paired_research_quotes=len(matches),
                     rejected_quote_counts=rejected,
                     unverified_research_candidates=matches)
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as exc:
        return _hold(str(exc))
