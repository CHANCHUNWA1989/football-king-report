"""Real-score, date-only, reproducible multi-league shadow replay.

Uses exact public OpenFootball Git revision and the repository's EXISTING
predict_league() A shadow implementation. Synthetic 23:00 local times adapt
a date-only historical archive to the prediction function. They are NOT
real kickoff timestamps or original sealed pre-match predictions.

No keys, paid APIs, bookmaker quotes, EV, ROI or betting recommendations.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from zoneinfo import ZoneInfo

from .league_goal_blend_shadow import audit
from .shadow_forecast import predict_league

SOURCE_SHA = "e6744429ee395bc86f247348c6184bb08d4eb361"
SOURCE_ROOT = "https://raw.githubusercontent.com/openfootball/football.json/" + SOURCE_SHA
SEASONS = ("2022-23", "2023-24", "2024-25", "2025-26")
LEAGUE_FILES = {
    "epl": ("en.1.json", 20),
    "bundesliga": ("de.1.json", 18),
    "laliga": ("es.1.json", 20),
    "seriea": ("it.1.json", 20),
    "ligue1": ("fr.1.json", None),
}
HK = ZoneInfo("Asia/Hong_Kong")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        raise ValueError("UNEXPECTED_ARCHIVE_REDIRECT")


def _read_archive(season, filename):
    if season not in SEASONS or filename not in {x[0] for x in LEAGUE_FILES.values()}:
        raise ValueError("UNSUPPORTED_PINNED_ARCHIVE")
    request = Request(
        SOURCE_ROOT + "/" + season + "/" + filename,
        headers={"Accept": "application/json",
                 "User-Agent": "FootballKingLeagueBlendResearch/1.0"})
    with build_opener(_NoRedirect()).open(request, timeout=15) as response:
        raw = response.read(800_001)
    if not raw or len(raw) > 800_000:
        raise ValueError("ARCHIVE_SIZE_OUT_OF_BOUNDS")
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("INVALID_ARCHIVE_JSON") from exc
    return obj, hashlib.sha256(raw).hexdigest()


def _rows(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get("matches"), list):
        raise ValueError("INVALID_ARCHIVE_SCHEMA")
    if len(raw["matches"]) > 700:
        raise ValueError("TOO_MANY_ARCHIVE_MATCHES")
    out = []
    for row in raw["matches"]:
        if not isinstance(row, dict):
            raise ValueError("INVALID_ARCHIVE_ROW")
        ghga = row.get("score")
        if isinstance(ghga, dict):
            ghga = ghga.get("ft")
        if (not isinstance(ghga, list) or len(ghga) != 2
                or any(type(v) is not int or not 0 <= v <= 25 for v in ghga)):
            # A partial archived season is rejected by the full-season gate.
            continue
        if (not isinstance(row.get("team1"), str) or not row["team1"]
                or not isinstance(row.get("team2"), str) or not row["team2"]
                or row["team1"] == row["team2"]):
            raise ValueError("INVALID_ARCHIVE_TEAM")
        try:
            day = date.fromisoformat(row["date"])
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("INVALID_ARCHIVE_MATCH_DATE") from exc
        out.append({
            "home": row["team1"], "away": row["team2"],
            "date": day.isoformat(), "home_goals": ghga[0],
            "away_goals": ghga[1],
        })
    return out


def _season_quality(matches, expected_teams):
    teams = {name for x in matches for name in (x["home"], x["away"])}
    n = len(teams)
    if n < 6 or (expected_teams is not None and n != expected_teams):
        return False
    if len(matches) != n * (n - 1):
        return False
    keys = {(x["home"], x["away"]) for x in matches}
    if len(keys) != len(matches):
        return False
    counts_h = Counter(x["home"] for x in matches)
    counts_a = Counter(x["away"] for x in matches)
    return all(counts_h[t] == n-1 and counts_a[t] == n-1 for t in teams)


def _ref(league, season, item):
    # Locally DERIVED replay identity, not a provider-native ID.
    return "|".join((league, season, item["date"], item["home"], item["away"]))


def replay_pair(training, heldout, league, training_season, heldout_season):
    """Recreate actual A shadow rates without ever supplying target scores as model inputs."""
    train_hist = [{
        "date": x["date"], "home": x["home"], "away": x["away"],
        "score_ft": [x["home_goals"], x["away_goals"]],
        "status": "FINISHED",
    } for x in training]
    counts = Counter(name for x in training for name in (x["home"], x["away"]))
    by_day = defaultdict(list)
    for row in heldout:
        if counts[row["home"]] >= 5 and counts[row["away"]] >= 5:
            by_day[row["date"]].append(row)
    result = []
    for date_string in sorted(by_day):
        day = date.fromisoformat(date_string)
        model_clock = datetime.combine(day, time(0, 0), tzinfo=HK).astimezone(timezone.utc)
        # Artificial 23:00 timestamp is used only to satisfy historical replay API.
        pseudo_kickoff = datetime.combine(day, time(23, 0), tzinfo=HK)
        pending = []
        target = {}
        for row in by_day[date_string]:
            rid = _ref(league, heldout_season, row)
            if rid in target:
                raise ValueError("DUPLICATE_REPLAY_ID")
            target[rid] = row
            pending.append({
                "date": date_string, "home": row["home"], "away": row["away"],
                "event_id": rid, "status": "SCHEDULED", "score_ft": None,
                "kickoff_utc": pseudo_kickoff.astimezone(timezone.utc).isoformat(),
            })
        preds = predict_league(train_hist + pending, league, model_clock)
        if len(preds) != len(pending):
            raise ValueError("ORIGINAL_A_REPLAY_INCOMPLETE")
        for p in preds:
            x = target.get(p["event_id"])
            if x is None or p["training_games"] != len(training):
                raise ValueError("ORIGINAL_A_REPLAY_CORRUPTED")
            result.append({
                "league": league, "fixture_id": p["event_id"],
                "match_date": x["date"],
                "home_goals": x["home_goals"], "away_goals": x["away_goals"],
                "expected_home_goals": p["expected_home_goals"],
                "expected_away_goals": p["expected_away_goals"],
            })
    return {
        "league": league,
        "test_season": heldout_season,
        "training": [{
            "league": league, "fixture_id": _ref(league, training_season, x),
            "match_date": x["date"],
            "home_goals": x["home_goals"], "away_goals": x["away_goals"],
        } for x in training],
        "heldout": result,
    }


def run(*, reader=_read_archive):
    parsed = {}
    digests = {}
    exclusions = []
    for league, (filename, expected) in LEAGUE_FILES.items():
        for season in SEASONS:
            raw, sha256 = reader(season, filename)
            matches = _rows(raw)
            n = 20 if league == "ligue1" and season == "2022-23" else expected
            ok = _season_quality(matches, n)
            parsed[(league, season)] = matches if ok else None
            digests[league + "/" + season] = sha256
    folds = []
    for league in LEAGUE_FILES:
        for i in range(1, len(SEASONS)):
            before, target = SEASONS[i-1], SEASONS[i]
            tr, te = parsed[(league, before)], parsed[(league, target)]
            if tr is None or te is None:
                exclusions.append({"league": league, "training": before,
                                   "target": target, "reason": "INCOMPLETE_SEASON"})
                continue
            folds.append(replay_pair(tr, te, league, before, target))
    report = audit(folds, source_revision=SOURCE_SHA)
    report["public_source_revision_pinned"] = SOURCE_SHA
    report["public_source_file_sha256"] = digests
    report["source_url_kind"] = "PINNED_OPENFOOTBALL_CC0_GITHUB_RAW"
    report["missing_league_season_folds"] = exclusions
    report["date_only_synthetic_replay_clock_not_real_kickoff"] = True
    report["provider_native_fixture_identity_verified"] = False
    return report


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    a = p.parse_args(argv)
    report = run()
    dest = Path(a.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    with dest.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print("LEAGUE_REAL_DATE_SPLIT", len(report["folds"]),
          report["pooled"]["OVER25"]["sample_count"],
          report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
