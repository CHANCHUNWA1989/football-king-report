"""Integrate optional free provider audit into the iPhone research site.

Secondary API results NEVER replace the validated historical model, never
invent a bookmaker market or retroactively become pre-match information.
Use independently identified club names and matching UTC kickoffs only for
disclosed schedule-agreement counts. Any disagreement remains for review.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from team_identity import team_id
from source_publish_guard import verify

LIMIT_HOURS = 36
LEAGUES = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")
PROVIDERS = ("thesportsdb", "api_football", "football_data_org", "sportmonks")


def clock(value):
    t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("NAIVE")
    return t.astimezone(timezone.utc)


def build(shadow, audit=None, *, now=None):
    now = now or datetime.now(timezone.utc)
    output = {
        "schema": "football-king-source-overlay-v1", "generated_utc": now.isoformat(),
        "status": "HOLD", "reason": "NO_VALID_SECONDARY_SOURCE_SNAPSHOT",
        "source_checked_utc": None,
        "snapshot_age_hours": None, "providers": [], "matched_kickoff_agreements": 0,
        "kickoff_disagreements_needing_review": 0,
        "source_samples_used_as_forecast_training": False,
        "independently_verified_six_league_results": False,
        "can_replace_market_1x2": False,
        "production_recommendations": "DISABLED",
    }
    for key in PROVIDERS:
        output["providers"].append({
            "provider": key, "status": "NOT_YET_COLLECTED",
            "sampled_fixture_count": 0, "configured": False,
            "scope": "AWAITING_FIRST_AUDIT",
        })
    if (not isinstance(shadow, dict)
            or shadow.get("production_recommendations") != "DISABLED"
            or not isinstance(shadow.get("predictions"), list)
            or not isinstance(audit, dict)):
        return output
    try:
        then = verify(audit)
        age = (now - then).total_seconds()/3600
        if not -5/60 <= age <= LIMIT_HOURS:
            output["reason"] = "EXTERNAL_SOURCE_SNAPSHOT_STALE_OR_FUTURE"
            return output
    except (KeyError, ValueError, TypeError, OverflowError):
        return output
    output["source_checked_utc"] = then.isoformat()
    output["snapshot_age_hours"] = round(age, 2)
    output["status"] = "RESEARCH_ONLY"
    output["reason"] = "SECONDARY_SCHEDULE_COVERAGE_ONLY"
    output["providers"] = []
    for item in audit["providers"]:
        output["providers"].append({
            "provider": item["provider"], "status": item["status"],
            "sampled_fixture_count": item["sampled_fixture_count"],
            "configured": item["configured"],
            "scope": item["source_scope"], "warnings": item["warnings"][:6],
            "counts_by_league": item["counts_by_league"]
        })
    indices = {}
    for pred in shadow["predictions"]:
        if not isinstance(pred, dict) or pred.get("league") not in LEAGUES:
            continue
        try:
            match = (pred["league"], team_id(pred["league"], pred["home"]),
                     team_id(pred["league"], pred["away"]))
            ko = clock(pred["kickoff_utc"])
            if match[1] and match[2]:
                indices.setdefault(match, []).append(ko)
        except (ValueError, KeyError, TypeError, OverflowError):
            continue
    seen = set()
    for observed in audit["sampled_fixtures"]:
        if observed.get("status") == "FINISHED":
            continue
        key = (observed["league"],
               team_id(observed["league"], observed["home"]),
               team_id(observed["league"], observed["away"]))
        other = indices.get(key, [])
        if len(other) != 1 or not all(key):
            continue
        try:
            source_ko = clock(observed["kickoff_utc"])
        except (ValueError, TypeError, OverflowError):
            continue
        delta = abs((source_ko - other[0]).total_seconds())
        unique = (observed["provider"],) + key
        if unique in seen:
            continue
        seen.add(unique)
        if delta <= 45*60:
            output["matched_kickoff_agreements"] += 1
        elif delta <= 7*86400:
            output["kickoff_disagreements_needing_review"] += 1
    return output


def publish(site, source_file="sources/latest.json"):
    site = Path(site)
    shadow = json.loads((site/"shadow.json").read_text(encoding="utf-8"))
    external = None
    path = Path(source_file)
    if path.is_file():
        try:
            external = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError, OSError):
            external = None
    report = build(shadow, external)
    (site/"extra_sources.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "providers": {p["provider"]: p["status"] for p in report["providers"]},
        "schedule_agreements": report["matched_kickoff_agreements"],
        "warnings": report["kickoff_disagreements_needing_review"],
        "production_recommendations": "DISABLED"
    }, ensure_ascii=False))
    return report


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--site", default="app/site")
    cli.add_argument("--input", default="sources/latest.json")
    a = cli.parse_args()
    publish(a.site, a.input)
