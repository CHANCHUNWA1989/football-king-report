"""Fail-closed worldwide football league directory and discovery.

Separates technical catalogue coverage from qualified forecast coverage.
OpenFootball git-tree metadata is for discovery only; it is not a live source
of verified kickoff timestamps, market quotes or historical forecast evidence.
"""
import argparse
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from wide_sources import NOW_LEAGUES, HISTORY_LEAGUES, GERMAN_LEAGUES

SCHEMA = "football-king-global-league-catalog-v1"
TREE_URL = "https://api.github.com/repos/openfootball/football.json/git/trees/master?recursive=1"
MAX_TREE_BYTES = 3_000_000
MAX_TREE_ENTRIES = 12000
MAX_CATALOGUE = 400
MAX_AGE_HOURS = 36
SIX = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")
FILES = tuple(NOW_LEAGUES) + tuple(HISTORY_LEAGUES)
KNOWN = {path: (ident, zh) for ident, zh, path in FILES}
# Lower divisions may have a current-season file even when our original
# audited snapshot deliberately used an older archive.
KNOWN_STEMS = {path.split("/", 1)[-1]: (ident, zh)
               for ident, zh, path in FILES}
SAFE_FILE = re.compile(r"^[a-z][a-z0-9]{1,11}(?:[._-][a-z0-9]{1,15}){0,3}\.json$")
SAFE_SEASON = re.compile(r"^20[0-9]{2}(?:-[0-9]{2})?$")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("UNTRUSTED_CATALOG_REDIRECT")


def stamp(v):
    if not isinstance(v, str):
        raise ValueError("MISSING_SNAPSHOT_TIME")
    value = datetime.fromisoformat(v.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("UNZONED_SNAPSHOT")
    return value.astimezone(timezone.utc)


def is_fresh(value, now):
    try:
        gap = now - stamp(value)
        return timedelta(minutes=-5) <= gap <= timedelta(hours=MAX_AGE_HOURS)
    except (ValueError, TypeError, OverflowError):
        return False


def discover_tree(doc, *, now):
    """Parse a fixed, bounded upstream tree without inferring fixture quality."""
    if not isinstance(doc, dict) or doc.get("truncated") is not False:
        return []
    files = doc.get("tree")
    if not isinstance(files, list) or len(files) > MAX_TREE_ENTRIES:
        return []
    season = f"{now.year if now.month >= 7 else now.year - 1}-" + (
        f"{(now.year + 1) % 100:02d}" if now.month >= 7 else f"{now.year % 100:02d}")
    year = str(now.year)
    found = []
    for node in files:
        if not isinstance(node, dict) or node.get("type") != "blob":
            continue
        path = node.get("path")
        if not isinstance(path, str) or len(path) > 100 or path.count("/") != 1:
            continue
        period, filename = path.split("/")
        if period not in (season, year) or not SAFE_SEASON.fullmatch(period):
            continue
        if not SAFE_FILE.fullmatch(filename):
            continue
        # Folder existence/metadata can never imply that matches are fresh.
        ident, label = KNOWN.get(path, KNOWN_STEMS.get(filename, (
            "openfootball_" + re.sub(r"[^a-z0-9]+", "_", filename[:-5])[:34],
            "OpenFootball " + filename[:-5].upper())))
        found.append({"id": ident, "name": label, "path": path,
                      "discovery": "PUBLIC_SOURCE_FILENAME_ONLY"})
    return found[:MAX_CATALOGUE]


def fetch_tree(opener=None):
    req = Request(TREE_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "FootballKingGlobalLeagueCatalog/1.0"})
    client = opener or build_opener(NoRedirect()).open
    with client(req, timeout=12) as response:
        data = response.read(MAX_TREE_BYTES + 1)
    if len(data) > MAX_TREE_BYTES:
        raise ValueError("CATALOG_RESPONSE_TOO_LARGE")
    return json.loads(data.decode("utf-8"))


def build(wide, shadow, pairing, *, now=None, discovered=None, worldwide=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    wide_ok = (
        isinstance(wide, dict)
        and wide.get("schema") == "football-king-global-free-league-site-v1"
        and wide.get("status") == "RESEARCH_ONLY"
        and wide.get("production_recommendations") == "DISABLED"
        and wide.get("provider_market_odds_available") is False
        and is_fresh(wide.get("generated_utc"), now)
        and is_fresh(wide.get("source_as_of_utc"), now)
        and isinstance(wide.get("league_cards"), list)
    )
    shadow_ok = (
        isinstance(shadow, dict)
        and shadow.get("schema") == "football-king-uncalibrated-shadow-1"
        and shadow.get("status") == "SHADOW_ONLY"
        and shadow.get("production_recommendations") == "DISABLED"
        and is_fresh(shadow.get("as_of_utc"), now)
        and isinstance(shadow.get("predictions"), list)
    )
    market_ok = (
        isinstance(pairing, dict)
        and pairing.get("production_recommendations") == "DISABLED"
        and pairing.get("status") in ("RESEARCH_ONLY", "HOLD")
        and isinstance(pairing.get("comparisons"), list)
    )
    cards = {}
    for league, label, path in FILES:
        cards.setdefault(league, {"id": league, "name": label,
                                   "source_files": [], "source_statuses": [],
                                   "season_scopes": [], "records": 0,
                                   "current_source_confirmed": False})
    for league, label, key in GERMAN_LEAGUES:
        cards.setdefault(league, {"id": league, "name": label,
                                   "source_files": [], "source_statuses": [],
                                   "season_scopes": [], "records": 0,
                                   "current_source_confirmed": False})
    if wide_ok:
        for info in wide["league_cards"][:MAX_CATALOGUE]:
            if not isinstance(info, dict):
                continue
            key = info.get("id")
            if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9_]{2,48}", key):
                continue
            record = cards.setdefault(key, {
                "id": key, "name": info.get("name") or key,
                "source_files": [], "source_statuses": [],
                "season_scopes": [], "records": 0, "current_source_confirmed": False})
            state = info.get("access_status", "UNKNOWN")
            scope = info.get("season_scope", "UNKNOWN")
            if type(info.get("records")) is int and 0 <= info["records"] <= 3000:
                record["records"] += info["records"]
            record["source_statuses"].append(state)
            record["season_scopes"].append(scope)
            record["current_source_confirmed"] |= (
                state == "FETCHED" and scope == "CURRENT_SEASON_FILE")
    new_files = 0
    if isinstance(discovered, list):
        for item in discovered[:MAX_CATALOGUE]:
            if not isinstance(item, dict) or item.get("discovery") != "PUBLIC_SOURCE_FILENAME_ONLY":
                continue
            path = item.get("path")
            ident = item.get("id")
            if (not isinstance(path, str) or len(path) > 100
                    or not isinstance(ident, str)
                    or not re.fullmatch(r"[a-z0-9_]{2,48}", ident)
                    or not SAFE_FILE.fullmatch(path.split("/")[-1])):
                continue
            card = cards.setdefault(ident, {
                "id": ident, "name": str(item.get("name") or ident)[:70],
                "source_files": [], "source_statuses": [],
                "season_scopes": [], "records": 0, "current_source_confirmed": False})
            if path not in card["source_files"]:
                card["source_files"].append(path)
                new_files += 1
            # Metadata discovery alone must NEVER set current_source_confirmed.
    # A separate, source-checked worldwide Shadow sidecar may add leagues.
    # Never count file discovery as a prediction or double count core six.
    world_ok = (
        isinstance(worldwide, dict)
        and worldwide.get("schema") == "football-king-worldwide-uncalibrated-shadow-v1"
        and worldwide.get("status") == "SHADOW_ONLY"
        and worldwide.get("production_recommendations") == "DISABLED"
        and worldwide.get("model_calibrated") is False
        and worldwide.get("positive_ev_verified") is False
        and is_fresh(worldwide.get("as_of_utc"), now)
        and isinstance(worldwide.get("predictions"), list)
    )
    world_forecasts = Counter()
    if world_ok:
        for row in worldwide["predictions"][:2500]:
            if not isinstance(row, dict):
                continue
            league = row.get("league")
            if (not isinstance(league, str)
                    or not re.fullmatch(r"[a-z][a-z0-9_]{1,47}", league)
                    or league in SIX
                    or row.get("production_recommendations") != "DISABLED"
                    or row.get("worldwide_two_distinct_schedule_feeds") is not True):
                continue
            cards.setdefault(league, {"id": league, "name": league,
                                       "source_files": [], "source_statuses": [],
                                       "season_scopes": [], "records": 0,
                                       "current_source_confirmed": False})
            world_forecasts[league] += 1
    forecasts = Counter()
    if shadow_ok:
        for row in shadow["predictions"][:2500]:
            if isinstance(row, dict) and row.get("league") in cards:
                forecasts[row["league"]] += 1
    pairs = Counter()
    if market_ok:
        for row in pairing["comparisons"][:2500]:
            if isinstance(row, dict) and row.get("league") in cards:
                pairs[row["league"]] += 1
    for key, card in cards.items():
        n = forecasts[key] + world_forecasts[key]
        sources = card["source_statuses"]
        card["shadow_predictions"] = n
        card["worldwide_shadow_predictions"] = world_forecasts[key]
        card["paired_research_cases"] = pairs[key]
        card["coverage_state"] = (
            "UNCALIBRATED_SHADOW" if n
            else "CURRENT_SOURCE_NO_FORECAST" if card["current_source_confirmed"]
            else "ARCHIVE_ONLY" if "FETCHED" in sources
            else "DISCOVERED_UNVERIFIED" if card["source_files"]
            else "NO_VERIFIED_SOURCE"
        )
        card["forecast_validated"] = False
        card["executable_odds"] = False
        card["production_recommendations"] = "DISABLED"
    order = ("UNCALIBRATED_SHADOW", "CURRENT_SOURCE_NO_FORECAST",
             "ARCHIVE_ONLY", "DISCOVERED_UNVERIFIED", "NO_VERIFIED_SOURCE")
    result = sorted(cards.values(), key=lambda x: (order.index(x["coverage_state"]), x["id"]))
    result = result[:MAX_CATALOGUE]
    coverage = Counter(row["coverage_state"] for row in result)
    return {
        "schema": SCHEMA, "as_of_utc": now.isoformat(),
        "status": "RESEARCH_ONLY" if (wide_ok or shadow_ok) else "HOLD",
        "catalogued_leagues": len(result),
        "leagues_with_shadow": coverage["UNCALIBRATED_SHADOW"],
        "leagues_with_current_files_but_no_shadow": coverage["CURRENT_SOURCE_NO_FORECAST"],
        "leagues_archived_only": coverage["ARCHIVE_ONLY"],
        "leagues_discovered_unverified": coverage["DISCOVERED_UNVERIFIED"],
        "new_file_paths_discovered": new_files,
        "source_metadata_discovery_does_not_verify_live_coverage": True,
        "all_world_leagues_complete": False,
        "training_or_market_coverage_is_not_implied": True,
        "production_recommendations": "DISABLED",
        "executable_odds_confirmed": False,
        "cards": result,
    }


def publish(site, *, discover=True):
    site = Path(site)
    def load(name):
        try:
            val = json.loads((site / name).read_text(encoding="utf-8"))
            return val if isinstance(val, dict) else None
        except (OSError, UnicodeError, ValueError):
            return None
    now = datetime.now(timezone.utc)
    discovered = []
    if discover:
        try:
            discovered = discover_tree(fetch_tree(), now=now)
        except (OSError, ValueError, UnicodeError, TimeoutError):
            pass
    result = build(load("wide_leagues.json"), load("shadow.json"),
                   load("market_comparison.json"), now=now, discovered=discovered,
                   worldwide=load("worldwide_shadow.json"))
    (site / "global_league_catalog.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"], "catalogued_leagues": result["catalogued_leagues"],
        "leagues_with_shadow": result["leagues_with_shadow"],
        "source_paths_discovered": result["new_file_paths_discovered"],
        "production_recommendations": "DISABLED"}, ensure_ascii=False))
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--site", default="app/site")
    cli.add_argument("--no-discover", action="store_true")
    args = cli.parse_args()
    publish(args.site, discover=not args.no_discover)
