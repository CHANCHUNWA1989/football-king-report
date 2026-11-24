"""REAL upcoming UEFA Nations League match trial, no fabricated outcomes.

Original A's existing predict_league algorithm is REUSED but with genuine
international CSV history, NOT the original club source/league fit. Real
upstream Penaltyblog Poisson/DC fit independently on the same actual records.
The historical CSV is pinned as the 2026-10-31 martj42 repository commit and
has match dates, NOT verifiable result publication timestamps or kickoffs.
Its LAST actual outcome is dated 2026-10-06. This is a stale, incomplete
international training set, not a current UEFA match-score feed.

UEFA public November 15 fixtures are specified from official published
competition calendar. Their names are aligned to exactly spelled CSV source
team labels, with no claim of native official fixture IDs or team IDs.
No odds, money, bets, authentic source-time custody or calibrated models.
"""
import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import stat
from urllib.request import Request, urlopen

from .shadow_forecast import HK, predict_league

DATA_COMMIT = "b0948cb558c927c357db4067eac5b37b96d0e4bb"
DATA_BLOB = "9999a4b380b16189825884a8dab4dc869c847f72"
DATA_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/"
    + DATA_COMMIT + "/results.csv")
DATA_LIMIT = 5_000_000
TRAIN_START = date(2025, 1, 1)
TRAIN_END = date(2026, 10, 6)
MAX_FIT_SECONDS = 600
SCHEMA = "football-king-real-20261115-unl-three-model-trial-v1"
UEFA = frozenset(("Albania", "Andorra", "Armenia", "Austria", "Azerbaijan",
    "Belarus", "Belgium", "Bosnia and Herzegovina", "Bulgaria", "Croatia",
    "Cyprus", "Czech Republic", "Denmark", "England", "Estonia",
    "Faroe Islands", "Finland", "France", "Georgia", "Germany", "Gibraltar",
    "Greece", "Hungary", "Iceland", "Israel", "Italy", "Kazakhstan",
    "Kosovo", "Latvia", "Liechtenstein", "Lithuania", "Luxembourg", "Malta",
    "Moldova", "Montenegro", "Netherlands", "North Macedonia",
    "Northern Ireland", "Norway", "Poland", "Portugal", "Republic of Ireland",
    "Romania", "Russia", "San Marino", "Scotland", "Serbia", "Slovakia",
    "Slovenia", "Spain", "Sweden", "Switzerland", "Turkey", "Ukraine", "Wales"))

# Explicit CSV source name spellings. UTC KO values are from UEFA Nations
# League November 15, 2026 official matchday 6 (20:45 CET for League A).
FIXTURES = (
    ("cyprus-montenegro", "Cyprus", "Montenegro", "2026-11-15T14:00:00+00:00"),
    ("latvia-armenia", "Latvia", "Armenia", "2026-11-15T14:00:00+00:00"),
    ("belarus-albania", "Belarus", "Albania", "2026-11-15T17:00:00+00:00"),
    ("finland-san-marino", "Finland", "San Marino", "2026-11-15T17:00:00+00:00"),
    ("belgium-italy", "Belgium", "Italy", "2026-11-15T19:45:00+00:00"),
    ("france-turkey", "France", "Turkey", "2026-11-15T19:45:00+00:00"),
    ("croatia-czech-republic", "Croatia", "Czech Republic", "2026-11-15T19:45:00+00:00"),
    ("spain-england", "Spain", "England", "2026-11-15T19:45:00+00:00"),
)


def _now():
    return datetime.now(timezone.utc)


def _git_blob_sha(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode()
                        + b"\0" + raw).hexdigest()


def _read_source(*, opener=urlopen):
    request = Request(DATA_URL, headers={
        "User-Agent": "football-king-research-public-international/1.0",
        "Accept": "text/csv",
    })
    with opener(request, timeout=25) as result:
        raw = result.read(DATA_LIMIT + 1)
    if (not 0 < len(raw) <= DATA_LIMIT or
            _git_blob_sha(raw) != DATA_BLOB):
        raise ValueError("PINNED_PUBLIC_CSV_GIT_BLOB_MISMATCH")
    return raw


def _parse(raw):
    data = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(data))
    required = ("date", "home_team", "away_team", "home_score", "away_score",
                "tournament", "city", "country", "neutral")
    if tuple(reader.fieldnames or ()) != required:
        raise ValueError("REAL_PUBLIC_CSV_SCHEMA_CHANGED")
    rows = []
    seen = set()
    last = None
    for line, row in enumerate(reader, start=2):
        if (None in row or type(row) is not dict or
                any(row.get(k) is None for k in required)):
            raise ValueError("MALFORMED_REAL_PUBLIC_CSV")
        try:
            d = date.fromisoformat(row["date"])
        except ValueError:
            raise ValueError("INVALID_MATCH_DATE_IN_PUBLIC_CSV")
        if last is not None and d < last:
            raise ValueError("CHRONOLOGICALLY_UNSORTED_PUBLIC_CSV")
        last = d
        if not TRAIN_START <= d <= TRAIN_END:
            continue
        home, away = row["home_team"], row["away_team"]
        if home not in UEFA or away not in UEFA or home == away:
            continue
        try:
            gh, ga = int(row["home_score"]), int(row["away_score"])
        except ValueError:
            raise ValueError("NONNUMERIC_FINISHED_CSV_RESULT")
        if any(not 0 <= goal <= 20 for goal in (gh, ga)):
            raise ValueError("IMPOSSIBLE_REAL_CSV_SCORE")
        key = (d, home, away, row["tournament"])
        if key in seen:
            raise ValueError("DUPLICATE_PAST_INTERNATIONAL_FIXTURE")
        seen.add(key)
        rows.append({
            "source_csv_row": line,
            "date": d.isoformat(), "home": home, "away": away,
            "status": "FINISHED", "score_ft": [gh, ga],
            "neutral_as_in_source": row["neutral"],
        })
    if not 100 <= len(rows) <= 1200:
        raise ValueError("MISSING_REAL_EUROPEAN_HISTORICAL_SAMPLE")
    return rows, last


def _vector(value):
    p = list(value)
    if (len(p) != 3 or
            any(type(x) not in (int, float) or
                not math.isfinite(x) or not 0 <= x <= 1 for x in p)
            or abs(sum(p)-1) > 1e-5):
        raise ValueError("INVALID_REAL_MODEL_PROBABILITIES")
    return [float(x) for x in p]


def _fit_real(history, home, away, models):
    if home not in {r["home"] for r in history} | {r["away"] for r in history}:
        raise ValueError("UNKNOWN_SOURCE_TEAM")
    for team in (home, away):
        if sum(team in (r["home"], r["away"]) for r in history) < 5:
            raise ValueError("INSUFFICIENT_REAL_TEAM_RESULTS")
    answers = {}
    for model_id, klass in (
        ("poisson", models.PoissonGoalsModel),
        ("dixon_coles", models.DixonColesGoalModel),
    ):
        model = klass(
            [r["score_ft"][0] for r in history],
            [r["score_ft"][1] for r in history],
            [r["home"] for r in history],
            [r["away"] for r in history],
        )
        model.fit()
        predicted = model.predict(home, away, max_goals=15, normalize=True)
        answers[model_id] = _vector(predicted.home_draw_away)
    return answers


def _status(reason, **fields):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "research_only": True,
        "production_recommendations": "DISABLED",
        "genuine_source_authenticity_verified": False,
        "published_result_times_verified": False,
        "certified_prospective_samples": 0,
        "positive_ev_verified": False,
        "bookmaker_odds_verified": False,
        "model_promoted": False, **fields,
    }


def run(*, now=None, opener=urlopen, model_module=None):
    started = _now() if now is None else now
    if (type(started) is not datetime or
            started.tzinfo is None or started.utcoffset() is None):
        return _status("INVALID_EXPERIMENT_CLOCK")
    started = started.astimezone(timezone.utc)
    try:
        # Source content is actual GitHub-public CC0 international results,
        # pinned to its existing 2026-10-31 commit and 3.75MB git blob.
        raw = _read_source(opener=opener)
        fetched = _now()
        if fetched < started:
            raise ValueError("EXPERIMENT_CLOCK_REWOUND")
        past, last_dataset_date = _parse(raw)
        # No invented raw fixture kickoff dates for historical rows; their
        # original file has date-only, so only the raw CSV date is retained.
        now_hk = fetched.astimezone(HK).date()
        pre = []
        upcoming = []
        for fixture_key, home, away, ko in FIXTURES:
            kickoff = datetime.fromisoformat(ko)
            if (fetched >= kickoff - timedelta(minutes=10)
                    or kickoff.astimezone(HK).date() < now_hk):
                continue
            if any(team not in UEFA for team in (home, away)):
                continue
            scheduled = {
                "date": kickoff.astimezone(HK).date().isoformat(),
                "home": home, "away": away,
                "status": "SCHEDULED", "score_ft": None,
                "event_id": "uefa-unl-date-only-source-csv-research:" + fixture_key,
                "kickoff_utc": ko, "schedule_utc_source": "uefa-2026-unl-matchday6",
            }
            upcoming.append((fixture_key, home, away, kickoff))
            pre.append(scheduled)
        if not upcoming:
            raise ValueError("NO_MATCH_REMAINING_BEFORE_KICKOFF")
        asof = _now()
        a_out = predict_league(past+pre, "nations_league", asof)
        by_event = {p["event_id"]:p for p in a_out}
        from penaltyblog import models
        # Source rows were made available by fetched. No history result
        # obtained after the prediction cutoff.
        observations = []
        for fixture_key, home, away, kickoff in upcoming:
            event_id = "uefa-unl-date-only-source-csv-research:" + fixture_key
            pred = by_event.get(event_id)
            if pred is None:
                observations.append({
                    "fixture":fixture_key,"home":home,"away":away,
                    "kickoff_utc":kickoff.isoformat(),
                    "status":"HOLD","reason":"ORIGINAL_A_NO_AVAILABLE_PREDICTION",
                })
                continue
            fit_start = _now()
            if fit_start >= kickoff - timedelta(minutes=10):
                observations.append({
                    "fixture":fixture_key,"home":home,"away":away,
                    "kickoff_utc":kickoff.isoformat(),
                    "status":"HOLD","reason":"PREMATCH_CUTOFF_CROSSED",
                })
                continue
            try:
                challengers = _fit_real(past, home, away,
                                        models if model_module is None else model_module)
            except Exception as exc:
                observations.append({
                    "fixture":fixture_key,"home":home,"away":away,
                    "kickoff_utc":kickoff.isoformat(),
                    "status":"HOLD","reason":"ACTUAL_UPSTREAM_FIT_FAILED",
                    "error_type":type(exc).__name__,
                })
                continue
            fit_end = _now()
            if (not fit_start <= fit_end < kickoff - timedelta(minutes=10)
                    or (fit_end-fit_start).total_seconds() > MAX_FIT_SECONDS):
                observations.append({
                    "fixture":fixture_key,"home":home,"away":away,
                    "kickoff_utc":kickoff.isoformat(),
                    "status":"HOLD","reason":"PREMATCH_TIME_WINDOW_VIOLATED",
                })
                continue
            observations.append({
                "fixture":fixture_key,"home":home,"away":away,
                "kickoff_utc":kickoff.isoformat(),
                "status":"UNVERIFIED_PREMATCH_PROBABILITIES",
                "original_a_algorithm_1x2":_vector([
                    pred["p_home"],pred["p_draw"],pred["p_away"]]),
                "real_penaltyblog_poisson_1x2":challengers["poisson"],
                "real_penaltyblog_dixon_coles_1x2":challengers["dixon_coles"],
                "a_computed_utc_unattested":asof.isoformat(),
                "models_completed_utc_unattested":fit_end.isoformat(),
                "no_uefa_native_event_id_claimed":True,
            })
        completed = sum(r["status"]=="UNVERIFIED_PREMATCH_PROBABILITIES" for r in observations)
        return _status(
            "REAL_UNL_MATCH_TRIAL_UNVERIFIED_WITH_STALE_RESULT_HISTORY"
            if completed else "NO_REAL_UNL_THREE_MODEL_FITS_COMPLETED",
            dataset_url=DATA_URL,
            dataset_commit=DATA_COMMIT,
            dataset_git_blob_sha1=DATA_BLOB,
            dataset_sha256=hashlib.sha256(raw).hexdigest(),
            dataset_fetched_utc=fetched.isoformat(),
            dataset_max_result_date=last_dataset_date.isoformat(),
            training_date_min=TRAIN_START.isoformat(),
            training_date_max=TRAIN_END.isoformat(),
            qualifying_real_uefa_history_rows=len(past),
            result_lag_since_2026_10_06_acknowledged=True,
            original_a_is_adapted_club_algorithm_not_native_uefa_producer=True,
            original_csv_lacks_official_native_team_match_ids=True,
            kickoff_reference="UEFA official 2026/27 Nations League matchday 6",
            upcoming_true_matches_eligible=len(upcoming),
            three_model_results_from_real_scores=completed,
            observations=observations,
        )
    except Exception as exc:
        return _status("REAL_MATCH_INPUT_OR_MODEL_TRIAL_FAILED",
                       error_type=type(exc).__name__,
                       error_description=(str(exc)[:100] if type(exc) is ValueError
                                          else "NO_PUBLIC_DIAGNOSTIC"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        result = run()
        dest = Path(args.output)
        if dest.is_symlink() or dest.exists():
            raise ValueError("OUTPUT_EXISTS_OR_SYMLINK")
        raw = (json.dumps(result, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)+"\n").encode()
        fd = os.open(dest, os.O_WRONLY|os.O_CREAT|os.O_EXCL
                     |getattr(os, "O_NOFOLLOW",0), 0o600)
        with os.fdopen(fd,"wb") as writer:
            writer.write(raw)
            writer.flush()
            os.fsync(writer.fileno())
        print("LIVE_UNL_RESEARCH_RESULT",raw.decode().strip())
        return 0 if result.get("three_model_results_from_real_scores",0)>=1 else 1
    except Exception as exc:
        print(json.dumps({"status":"HOLD",
                          "reason":type(exc).__name__[:60],
                          "production_recommendations":"DISABLED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
