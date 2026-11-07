"""Generate research-only Poisson/DC forecasts for current private odds fixtures.

Requires independently supplied historical scored fixtures. Never substitute
bookmaker consensus for a model, and never persist raw odds in output.
"""
from datetime import datetime, timezone
from ops.private_h2h_evidence import FEED_SCHEMA, verify_bound_quotes
from ops.penaltyblog_walkforward_refit import refit_walkforward
from ops.private_refit_forecast_adapter import adapt

SCHEMA = "football-king-private-live-refit-v1"


def build(feed, history, *, now=None, model="poisson", model_factory=None):
    now = now or datetime.now(timezone.utc)
    if (not isinstance(feed, dict) or feed.get("schema") != FEED_SCHEMA
            or feed.get("production_recommendations") != "DISABLED"
            or not isinstance(history, list) or not isinstance(now, datetime)
            or now.tzinfo is None or model not in ("poisson", "dixon_coles")):
        return {"status": "HOLD", "reason": "INVALID_INPUT", "forecasts": []}
    accepted, _ = verify_bound_quotes(feed.get("quotes"), now=now)
    if not accepted:
        return {"status": "HOLD", "reason": "NO_CURRENT_VERIFIED_BOUND_QUOTES", "forecasts": []}
    fixtures = {}
    for q in accepted:
        key = (q["league"], q["fixture_id"])
        identity = (q["sport_key"], q["home"], q["away"], q["kickoff_utc"])
        if key in fixtures and fixtures[key] != identity:
            return {"status": "HOLD", "reason": "CONFLICTING_FIXTURE_IDENTITY", "forecasts": []}
        fixtures[key] = identity
    if len(fixtures) > 250:
        return {"status": "HOLD", "reason": "TOO_MANY_TARGETS", "forecasts": []}
    targets = []
    for (league, fixture_id), (sport, home, away, kickoff) in fixtures.items():
        targets.append({"source_namespace": "the_odds_api_v4",
                        "event_id": fixture_id, "league_id": league,
                        "home_team_id": home, "away_team_id": away,
                        "kickoff_utc": kickoff, "as_of_utc": now.isoformat()})
    targets.sort(key=lambda x: (x["kickoff_utc"], x["event_id"]))
    report = refit_walkforward({
        "schema": "football-king-penaltyblog-walkforward-v1",
        "production_recommendations": "DISABLED", "model": model,
        "historical_matches": history, "targets": targets, "min_training": 30
    }, model_factory=model_factory)
    if report.get("reason") != "PROSPECTIVE_SOURCE_AND_RESULT_ATTESTATION_MISSING":
        return {"status": "HOLD", "reason": report.get("reason", "REFIT_BLOCKED"),
                "forecasts": []}
    try:
        forecasts = adapt(report, now=now)
    except (ValueError, KeyError, TypeError):
        return {"status": "HOLD", "reason": "REFIT_FORECAST_ADAPTATION_FAILED", "forecasts": []}
    return {"status": "RESEARCH_ONLY", "reason": "UNVERIFIED_HISTORY_AND_PROVENANCE",
            "forecasts": forecasts, "production_recommendations": "DISABLED"}
