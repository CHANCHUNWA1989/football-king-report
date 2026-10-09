"""Cross-publisher UTC kickoff conflict detection for PRE-MATCH research display.

Never rerates historical forecasts using data acquired later. Observations here
can only suspend a currently displayed research selection, never promote odds,
change archived model probabilities, calculate EV, or verify final outcomes.
Providers: independently fetched TheSportsDB/optional fixture APIs and
OpenLigaDB UTC kickoffs from the wide-source catalogue. OpenFootball unzoned
times and historical-only files are deliberately excluded.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from source_publish_guard import verify as verify_secondary
from wide_source_guard import verify as verify_wide
from team_identity import team_id

SOURCE_MAX_AGE_HOURS = 36
NEARBY_DAYS = 7
CONFLICT_MINUTES = 45
LEAGUES = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")


def clock(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_UTC_TIMESTAMP")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return dt.astimezone(timezone.utc)


def identity(game):
    league = game.get("league")
    if league not in LEAGUES:
        return None
    home = team_id(league, game.get("home"))
    away = team_id(league, game.get("away"))
    if not home or not away or home == away:
        return None
    return league, home, away


def candidate_sources(secondary, wide, now):
    observations = []
    statuses = {
        "secondary": "UNAVAILABLE",
        "openligadb": "UNAVAILABLE",
    }
    try:
        stamp = verify_secondary(secondary)
        age = (now - stamp).total_seconds()
        if -300 <= age <= SOURCE_MAX_AGE_HOURS * 3600:
            statuses["secondary"] = "VALID_WINDOW"
            for row in secondary["sampled_fixtures"]:
                if (row.get("provider") in ("thesportsdb", "api_football", "football_data_org")
                        and row.get("status") in ("SCHEDULED", "UNKNOWN")):
                    observations.append(row)
        else:
            statuses["secondary"] = "STALE"
    except (TypeError, KeyError, ValueError, OverflowError, AttributeError):
        pass
    try:
        stamp = verify_wide(wide, clock=now)
        age = (now - stamp).total_seconds()
        if -300 <= age <= SOURCE_MAX_AGE_HOURS * 3600:
            statuses["openligadb"] = "VALID_WINDOW"
            for batch in wide.get("league_coverage", []):
                if not (isinstance(batch, dict)
                        and batch.get("provider") == "openligadb"
                        and batch.get("league") in LEAGUES
                        and batch.get("access_status") == "FETCHED"):
                    continue
                for row in batch.get("sample", [])[:3]:
                    if isinstance(row, dict) and row.get("status") == "SCHEDULED":
                        observations.append(row)
        else:
            statuses["openligadb"] = "STALE"
    except (TypeError, KeyError, ValueError, OverflowError, AttributeError):
        pass
    return observations, statuses


def build(shadow, secondary=None, wide=None, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    report = {
        "schema": "football-king-fixture-integrity-v1",
        "generated_utc": now.isoformat(),
        "status": "HOLD",
        "provider_freshness": {},
        "inspected_shadow_fixtures": 0,
        "independent_kickoff_agreement_observations": 0,
        "conflicting_kickoff_observations": 0,
        "affected_fixtures": 0,
        "disagreements": [],
        "blocked_from_research_recommendations": True,
        "never_used_to_rewrite_frozen_forecasts": True,
        "no_independent_result_verification_claim": True,
        "source_accuracy_not_proven": True,
        "production_recommendations": "DISABLED",
    }
    if (not isinstance(shadow, dict)
            or shadow.get("status") != "SHADOW_ONLY"
            or shadow.get("production_recommendations") != "DISABLED"
            or not isinstance(shadow.get("predictions"), list)):
        return report
    observations, statuses = candidate_sources(secondary, wide, now)
    report["provider_freshness"] = statuses
    report["status"] = "RESEARCH_ONLY" if "VALID_WINDOW" in statuses.values() else "HOLD"
    source_index = {}
    seen_source = set()
    for row in observations:
        if not isinstance(row, dict):
            continue
        key = identity(row)
        if key is None:
            continue
        token = (row.get("provider") or row.get("source"),
                 row.get("provider_event_id"))
        if not all(token) or (key, token) in seen_source:
            continue
        seen_source.add((key, token))
        try:
            kick = clock(row["kickoff_utc"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        source_index.setdefault(key, []).append((token[0], kick))
    affected = set()
    for game in shadow["predictions"]:
        if not isinstance(game, dict):
            continue
        key = identity(game)
        if key is None:
            continue
        try:
            predicted = clock(game["kickoff_utc"])
        except (TypeError, KeyError, ValueError, OverflowError):
            continue
        report["inspected_shadow_fixtures"] += 1
        for provider, from_source in source_index.get(key, []):
            delta = abs((from_source - predicted).total_seconds())
            if delta > NEARBY_DAYS * 86400:
                continue
            if delta <= CONFLICT_MINUTES * 60:
                report["independent_kickoff_agreement_observations"] += 1
                continue
            affected.add((key, predicted.isoformat()))
            report["disagreements"].append({
                "league": key[0],
                "home": str(game.get("home", ""))[:100],
                "away": str(game.get("away", ""))[:100],
                "original_kickoff_utc": predicted.isoformat(),
                "other_kickoff_utc": from_source.isoformat(),
                "provider": provider,
                "difference_minutes": round(delta / 60, 1),
                "action": "SUSPEND_RESEARCH_SELECTION_PENDING_SCHEDULE_REVIEW",
                "production_recommendations": "DISABLED",
            })
    report["disagreements"] = report["disagreements"][:100]
    report["conflicting_kickoff_observations"] = len(report["disagreements"])
    report["affected_fixtures"] = len(affected)
    return report


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None


def publish(site, secondary="sources/latest.json", wide="sources/wide_latest.json"):
    site = Path(site)
    shadow = load(site / "shadow.json")
    result = build(shadow, load(secondary), load(wide))
    (site/"fixture_integrity.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "inspected_shadow_fixtures": result["inspected_shadow_fixtures"],
        "independent_agreements": result["independent_kickoff_agreement_observations"],
        "schedule_conflicts": result["conflicting_kickoff_observations"],
        "affected_fixtures": result["affected_fixtures"],
        "production_recommendations": "DISABLED",
    }, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="app/site")
    parser.add_argument("--secondary", default="sources/latest.json")
    parser.add_argument("--wide", default="sources/wide_latest.json")
    arguments = parser.parse_args()
    publish(arguments.site, arguments.secondary, arguments.wide)
