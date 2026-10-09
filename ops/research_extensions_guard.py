"""Security and freshness gate for two research-only free feeds."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "football-king-free-research-extensions-v1"
PROVIDERS = ("openfootapi", "statsbomb_open_data")
ALLOWED = {
    "provider", "configured", "status", "scope", "attempted_requests",
    "observed_fixtures", "utc_kickoffs", "catalogue_entries", "issues",
    "raw_provider_data_published", "historical_data_only",
    "official_attribution_required", "supports_verified_bookmaker_1x2",
    "competition_seasons", "different_competitions",
    "records_with_provider_update_metadata",
    "up_to_date_2026_league_results_verified",
    "public_raw_event_licence_cleared",
}
STATUSES = {
    "NOT_CONFIGURED", "HOLD", "PARTIAL",
    "FREE_STARTER_SAMPLE_ONLY", "NO_FIXTURES_RETURNED",
    "HISTORICAL_CATALOG_READY"
}


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_EXTENSION_TIME")
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("NAIVE_EXTENSION_TIME")
    return t.astimezone(timezone.utc)


def validate(doc, *, now=None):
    now = now or datetime.now(timezone.utc)
    if (not isinstance(doc, dict) or doc.get("schema") != SCHEMA
            or doc.get("production_recommendations") != "DISABLED"
            or doc.get("current_free_odds_1x2_confirmed") is not False
            or doc.get("new_model_variables_enabled") is not False
            or doc.get("historical_statsbomb_results_are_live") is not False
            or doc.get("no_provider_raw_data_redistributed") is not True
            or doc.get("underlying_source_licences_not_overridden") is not True):
        raise ValueError("INVALID_RESEARCH_EXTENSION_AUTHORIZATION")
    start = parse_time(doc.get("started_utc"))
    finished = parse_time(doc.get("completed_utc"))
    if finished < start or (finished-start).total_seconds() > 20*60:
        raise ValueError("RESEARCH_EXTENSION_CLOCK")
    if finished > now + __import__("datetime").timedelta(minutes=5):
        raise ValueError("RESEARCH_EXTENSION_FROM_FUTURE")
    records = doc.get("providers")
    if (not isinstance(records, list) or len(records) != 2 or
            tuple(r.get("provider") for r in records if isinstance(r, dict)) != PROVIDERS):
        raise ValueError("RESEARCH_EXTENSION_PROVIDER_IDENTITY")
    limits = {"openfootapi": 3, "statsbomb_open_data": 1}
    for r in records:
        if not set(r).issubset(ALLOWED):
            raise ValueError("UNAUTHORISED_RESEARCH_EXTENSION_FIELDS")
        name = r["provider"]
        if (r.get("status") not in STATUSES
                or type(r.get("configured")) is not bool
                or type(r.get("attempted_requests")) is not int
                or not 0 <= r["attempted_requests"] <= limits[name]
                or any(type(r.get(k)) is not int or r[k] < 0
                       for k in ("observed_fixtures", "utc_kickoffs", "catalogue_entries"))
                or r["utc_kickoffs"] > r["observed_fixtures"]
                or r.get("raw_provider_data_published") is not False
                or r.get("supports_verified_bookmaker_1x2") is not False
                or not isinstance(r.get("issues"), list)
                or any(not isinstance(v, str) or len(v)>100 for v in r["issues"])):
            raise ValueError("INVALID_RESEARCH_EXTENSION_PROVIDER")
        if name == "statsbomb_open_data" and (
                r.get("historical_data_only") is not True
                or r.get("official_attribution_required") is not True
                or r.get("public_raw_event_licence_cleared") is True):
            raise ValueError("STATSBOMB_LICENCE_OR_TEMPORAL_MISREPRESENTATION")
        if name == "openfootapi" and (
                r.get("historical_data_only") is not False
                or r.get("official_attribution_required") is not False):
            raise ValueError("OPENFOOT_SCOPE_MISREPRESENTATION")
    # Audit JSON must contain no new fields, no raw responses, bookmaker data,
    # credentials or raw match lists.
    expected_top = {
        "schema", "started_utc", "completed_utc", "status", "providers",
        "no_provider_raw_data_redistributed",
        "underlying_source_licences_not_overridden",
        "current_free_odds_1x2_confirmed", "new_model_variables_enabled",
        "historical_statsbomb_results_are_live", "production_recommendations",
    }
    if set(doc) != expected_top:
        raise ValueError("UNEXPECTED_RESEARCH_EXTENSION_FIELDS")
    return finished


def latest_is_newer(incoming, previous):
    a = validate(incoming)
    if previous is None:
        return True
    b = validate(previous)
    if a == b and incoming != previous:
        raise ValueError("RESEARCH_EXTENSION_SAME_TIME_CONFLICT")
    return a > b


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--input", required=True)
    cli.add_argument("--previous", default="")
    cli.add_argument("--decision", default="")
    args = cli.parse_args()
    new = json.loads(Path(args.input).read_text(encoding="utf-8"))
    old = json.loads(Path(args.previous).read_text(encoding="utf-8")) if args.previous and Path(args.previous).is_file() else None
    safe = latest_is_newer(new, old)
    if args.decision:
        Path(args.decision).write_text(json.dumps({"replace": safe})+"\n", encoding="utf-8")
    print(json.dumps({"sanitized": True, "replace": safe,
                      "providers": [r["provider"] for r in new["providers"]],
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
