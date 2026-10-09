"""Additional free football research feeds: safe discovery, no paid features.

StatsBomb Open Data: official historical competition/season catalog only.
OpenFootAPI Starter: optional owner's FREE key, fixtures/catalog samples only.

No odds, xG, bookmaker quotes, match-model predictions, lineup or historical
event-level payload is distributed. Underlying source licences must be checked
before using any field in future training/recommendation workflows.
"""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from secondary_sources import NoRedirect, read_json

CATALOG = "https://raw.githubusercontent.com/hudl/open-data/master/data/competitions.json"
OPENFOOT = "https://openfootapi.com"
MAX_COMPETITION_RECORDS = 2500
MAX_MATCHES_PER_RESPONSE = 1000
MAX_OPENFOOT_REQUESTS = 3
DEFAULTS = ("openfootapi", "statsbomb_open_data")


def iso(value):
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMESTAMP_MISSING_OFFSET")
    return dt.astimezone(timezone.utc)


def status(name, *, configured, scope):
    return {
        "provider": name,
        "configured": bool(configured),
        "status": "NOT_CONFIGURED" if not configured else "HOLD",
        "scope": scope,
        "attempted_requests": 0,
        "observed_fixtures": 0,
        "utc_kickoffs": 0,
        "catalogue_entries": 0,
        "issues": [],
        "raw_provider_data_published": False,
        "historical_data_only": name == "statsbomb_open_data",
        "official_attribution_required": name == "statsbomb_open_data",
        "supports_verified_bookmaker_1x2": False,
    }


def parse_statsbomb_competitions(payload):
    if not isinstance(payload, list) or len(payload) > MAX_COMPETITION_RECORDS:
        raise ValueError("INVALID_STATSBOMB_COMPETITION_CATALOG")
    unique = set()
    competitions = set()
    with_update_timestamp = 0
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("INVALID_STATSBOMB_CATALOG_ROW")
        cid, sid, name = (row.get("competition_id"), row.get("season_id"),
                          row.get("competition_name"))
        if type(cid) is not int or type(sid) is not int or not isinstance(name, str):
            raise ValueError("INVALID_STATSBOMB_CATALOG_ID")
        unique.add((cid, sid))
        competitions.add(cid)
        if row.get("match_updated") or row.get("match_available"):
            with_update_timestamp += 1
    if len(unique) != len(payload):
        raise ValueError("DUPLICATE_STATSBOMB_SEASONS")
    return {
        "competition_seasons": len(unique),
        "different_competitions": len(competitions),
        "records_with_provider_update_metadata": with_update_timestamp,
        "up_to_date_2026_league_results_verified": False,
        "public_raw_event_licence_cleared": False,
    }


def parse_openfoot_competitions(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("INVALID_OPENFOOT_CATALOG")
    records = payload["data"]
    if len(records) > 1000:
        raise ValueError("EXCESSIVE_OPENFOOT_COMPETITIONS")
    return len(records)


def parse_openfoot_matches(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("INVALID_OPENFOOT_MATCHES")
    matches = payload["data"]
    if len(matches) > MAX_MATCHES_PER_RESPONSE:
        raise ValueError("EXCESSIVE_OPENFOOT_MATCHES")
    valid_utc = 0
    for record in matches:
        if not isinstance(record, dict):
            raise ValueError("INVALID_OPENFOOT_MATCH")
        kickoff = record.get("kickoffAt")
        try:
            if kickoff and iso(kickoff):
                valid_utc += 1
        except (ValueError, OverflowError, TypeError):
            pass
    return len(matches), valid_utc


def safe_fetch(url, headers, *, opener=None, allow_list=False):
    try:
        # The requester rejects ANY redirect when carrying a GitHub Secret.
        payload = read_json(url, headers, opener=opener or NoRedirect())
        if not isinstance(payload, list if allow_list else dict):
            return None, "INVALID_RESPONSE"
        if isinstance(payload, dict) and payload.get("error"):
            return None, "PROVIDER_ERROR"
        return payload, "OK"
    except HTTPError as exc:
        if exc.code == 401:
            return None, "KEY_REJECTED"
        if exc.code == 403:
            return None, "FREE_PLAN_ACCESS_RESTRICTED"
        if exc.code == 429:
            return None, "FREE_QUOTA_EXCEEDED"
        return None, "HTTP_ERROR"
    except (URLError, TimeoutError, OSError):
        return None, "NETWORK_ERROR"
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return None, "INVALID_RESPONSE"


def collect(*, now=None, keys=None, requester=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    keys = keys if keys is not None else os.environ
    key = keys.get("OPENFOOT_API_KEY", "")
    results = {
        "schema": "football-king-free-research-extensions-v1",
        "started_utc": now.isoformat(),
        "completed_utc": None,
        "status": "RESEARCH_ONLY",
        "providers": [],
        "no_provider_raw_data_redistributed": True,
        "underlying_source_licences_not_overridden": True,
        "current_free_odds_1x2_confirmed": False,
        "new_model_variables_enabled": False,
        "historical_statsbomb_results_are_live": False,
        "production_recommendations": "DISABLED",
    }
    openfoot = status("openfootapi", configured=bool(key), scope="FREE_STARTER_FIXTURE_CATALOG_ONLY")
    if not key:
        openfoot["issues"] = ["ADD_OPENFOOT_API_KEY_TO_GITHUB_SECRETS"]
    else:
        requests = [
            (OPENFOOT + "/v1/competitions", "catalog"),
            (OPENFOOT + "/v1/matches?date=" + now.date().isoformat(), "matches"),
            (OPENFOOT + "/v1/matches?date=" + (now+timedelta(days=1)).date().isoformat(), "matches"),
        ]
        faults = set()
        for url, typ in requests[:MAX_OPENFOOT_REQUESTS]:
            openfoot["attempted_requests"] += 1
            payload, error = safe_fetch(url, {"Authorization": "Bearer " + key},
                                        opener=requester)
            if error != "OK":
                faults.add(error)
                if error in ("KEY_REJECTED", "FREE_PLAN_ACCESS_RESTRICTED",
                             "FREE_QUOTA_EXCEEDED"):
                    break
                continue
            try:
                if typ == "catalog":
                    openfoot["catalogue_entries"] = parse_openfoot_competitions(payload)
                else:
                    n, precise = parse_openfoot_matches(payload)
                    openfoot["observed_fixtures"] += n
                    openfoot["utc_kickoffs"] += precise
            except (ValueError, TypeError, OverflowError):
                faults.add("UNEXPECTED_OPENFOOT_SCHEMA")
        openfoot["issues"] = sorted(faults)
        openfoot["status"] = (
            "PARTIAL" if faults and openfoot["catalogue_entries"] else
            "HOLD" if faults else
            "FREE_STARTER_SAMPLE_ONLY" if openfoot["catalogue_entries"] or
                                              openfoot["observed_fixtures"] else
            "NO_FIXTURES_RETURNED"
        )
    results["providers"].append(openfoot)

    statsbomb = status("statsbomb_open_data", configured=True,
                       scope="HISTORICAL_OPEN_DATA_CATALOGUE_ONLY")
    statsbomb["attempted_requests"] = 1
    payload, error = safe_fetch(CATALOG, {}, opener=requester, allow_list=True)
    if error == "OK":
        try:
            summary = parse_statsbomb_competitions(payload)
            statsbomb.update(summary)
            statsbomb["catalogue_entries"] = summary["competition_seasons"]
            statsbomb["status"] = "HISTORICAL_CATALOG_READY"
        except (TypeError, ValueError):
            statsbomb["issues"] = ["UNEXPECTED_STATSBOMB_SCHEMA"]
    else:
        statsbomb["issues"] = [error]
    results["providers"].append(statsbomb)
    results["completed_utc"] = (datetime.now(timezone.utc) if now.tzinfo else now).isoformat()
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="sources/research_extensions_latest.json")
    args = p.parse_args()
    report = collect()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "providers": [{
            "provider": r["provider"], "status": r["status"],
            "configured": r["configured"],
            "catalogue_entries": r["catalogue_entries"],
            "observed_fixtures": r["observed_fixtures"],
            "attempted_requests": r["attempted_requests"],
            "issues": r["issues"],
        } for r in report["providers"]],
        "production_recommendations": "DISABLED",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
