"""Optional historical xT method smoke with a date/ID/hash leakage guard.

Single immutable StatsBomb World Cup 2022 research sample: 12 earlier
matches to fit an xT surface, an embargo date, 4 later matches to rate.
This is retrospective *method feasibility*, NOT prospective certification,
not a betting model, and not a grant of commercial provider data rights.

Default VNext CI imports only Python stdlib here; Socceraction + pandas +
numpy are optional and imported only after the entire source preflight.
"""
from datetime import date, time
from hashlib import sha256
from importlib import metadata
import argparse
import json
import math
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

from ops.socceraction_spadl_offline_research import summarize_spadl_rows

SCHEMA = "football-king-xt-chronological-research-smoke-v1"
SOURCE_COMMIT = "4b73468fc5b0f1950f9f66fada70ad3a4f9327cb"
SOURCE_INDEX_SHA256 = "b9d7516dc9919a825f04c204ca85487958c8a2431e84140a48e944934661efc7"
TRAIN_IDS = (3857286, 3857271, 3857285, 3857282, 3857300, 3857254,
             3857265, 3857279, 3857277, 3857284, 3857291, 3857268)
EVAL_IDS = (3857273, 3857301, 3857274, 3857272)
TRAIN_END = date(2022, 11, 23)
EMBARGO = date(2022, 11, 24)
EVAL_BEGIN = date(2022, 11, 25)
VERSIONS = {
    "socceraction": "1.5.3",
    "pandera": "0.17.2",
    "multimethod": "1.12",
    "pandas": "2.3.3",
    "numpy": "1.26.4",
}
GRID_SHAPE = (6, 8)
MAX_SOURCE_BYTES = 8_000_000
MIN_RATED_HELDOUT_ACTIONS = 1
SHA = re.compile(r"^[0-9a-f]{64}$")


def _date(raw):
    if type(raw) is not str:
        raise ValueError("INVALID_MATCH_DATE")
    try:
        result = date.fromisoformat(raw)
    except ValueError:
        raise ValueError("INVALID_MATCH_DATE") from None
    if raw != result.isoformat():
        raise ValueError("INVALID_MATCH_DATE")
    return result


def validate_manifest(manifest):
    """Return exact research split or reject overlap, gaps, IDs and file tags."""
    if type(manifest) is not dict:
        raise ValueError("INVALID_XT_MANIFEST")
    if (manifest.get("source_repo") != "hudl/open-data"
            or manifest.get("source_commit") != SOURCE_COMMIT
            or manifest.get("match_index_sha256") != SOURCE_INDEX_SHA256
            or manifest.get("competition_id") != 43
            or manifest.get("season_id") != 106
            or manifest.get("train_through") != TRAIN_END.isoformat()
            or manifest.get("eval_from") != EVAL_BEGIN.isoformat()
            or manifest.get("eval_through") != EVAL_BEGIN.isoformat()
            or manifest.get("embargo_dates") != [EMBARGO.isoformat()]):
        raise ValueError("SOURCE_OR_TIME_BOUNDARY_MISMATCH")
    train = manifest.get("train")
    holdout = manifest.get("eval")
    if type(train) is not list or type(holdout) is not list:
        raise ValueError("INVALID_SPLIT_GROUPS")
    if ([r.get("match_id") for r in train if isinstance(r, dict)] != list(TRAIN_IDS)
            or [r.get("match_id") for r in holdout if isinstance(r, dict)] != list(EVAL_IDS)
            or len(train) != len(TRAIN_IDS) or len(holdout) != len(EVAL_IDS)):
        raise ValueError("MATCH_ID_SPLIT_CONTAMINATION")
    seen = set()
    for group, entries in (("train", train), ("eval", holdout)):
        last = None
        for entry in entries:
            if type(entry) is not dict:
                raise ValueError("INVALID_MATCH_METADATA")
            match_id = entry["match_id"]
            if type(match_id) is not int or match_id in seen:
                raise ValueError("DUPLICATE_OR_INVALID_MATCH_ID")
            seen.add(match_id)
            on = _date(entry.get("match_date"))
            expected_bounds = (date(2022, 11, 20), TRAIN_END) if group == "train" else (EVAL_BEGIN, EVAL_BEGIN)
            if not expected_bounds[0] <= on <= expected_bounds[1]:
                raise ValueError("CHRONOLOGICAL_LEAKAGE")
            kickoff = entry.get("kick_off")
            if type(kickoff) is not str:
                raise ValueError("INVALID_MATCH_KICKOFF")
            try:
                kick = time.fromisoformat(kickoff)
            except ValueError:
                raise ValueError("INVALID_MATCH_KICKOFF") from None
            stamp = (on, kick)
            if last is not None and stamp < last:
                raise ValueError("UNSORTED_MATCH_CHRONOLOGY")
            last = stamp
            home, away = entry.get("home_team_id"), entry.get("away_team_id")
            if (type(home) is not int or type(away) is not int
                    or home <= 0 or away <= 0 or home == away):
                raise ValueError("INVALID_MATCH_TEAMS")
            for kind in ("events", "lineups"):
                item = entry.get(kind)
                if type(item) is not dict or not SHA.fullmatch(str(item.get("sha256", ""))):
                    raise ValueError("INVALID_SOURCE_SHA256")
                size, count = item.get("bytes"), item.get("records")
                if (type(size) is not int or not 0 < size <= MAX_SOURCE_BYTES
                        or type(count) is not int or not 0 < count <= 20_000):
                    raise ValueError("INVALID_SOURCE_COUNTS")
    return train, holdout


def _read_source(path, item):
    """Check bytes and hash before any third-party library is imported."""
    file = Path(path)
    if file.is_symlink() or not file.is_file() or file.stat().st_size != item["bytes"]:
        raise ValueError("MISSING_OR_CHANGED_HISTORICAL_SOURCE")
    raw = file.read_bytes()
    if len(raw) != item["bytes"] or sha256(raw).hexdigest() != item["sha256"]:
        raise ValueError("HISTORICAL_SOURCE_SHA256_MISMATCH")
    return raw


def verify_all_historical_sources(root, manifest):
    """Freeze all 32 original bytes before any xT fitting/imports occur."""
    train, holdout = validate_manifest(manifest)
    base = Path(root)
    frozen = {}
    for match in train + holdout:
        match_id = match["match_id"]
        files = {}
        for kind in ("events", "lineups"):
            files[kind] = _read_source(base / kind / (str(match_id) + ".json"), match[kind])
        frozen[match_id] = files
    return frozen


def _versions():
    actual = {}
    for package, required in VERSIONS.items():
        try:
            installed = metadata.version(package)
        except metadata.PackageNotFoundError:
            raise ValueError("OPTIONAL_XT_DEPENDENCY_MISSING") from None
        if installed != required:
            raise ValueError("OPTIONAL_XT_DEPENDENCY_VERSION_MISMATCH")
        actual[package] = installed
    return actual


def _load_one_statsbomb_match(rec, frozen):
    """Local copy of individually verified bytes, destroyed after conversion."""
    from socceraction.data.statsbomb import StatsBombLoader
    from socceraction.spadl.statsbomb import convert_to_actions
    from socceraction import spadl
    with TemporaryDirectory(prefix="fk-xt-historical-") as temporary:
        root = Path(temporary)
        for kind in ("events", "lineups"):
            location = root / kind
            location.mkdir()
            (location / (str(rec["match_id"]) + ".json")).write_bytes(
                frozen[rec["match_id"]][kind])
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            events = StatsBombLoader(getter="local", root=str(root)).events(rec["match_id"])
            if len(events) != rec["events"]["records"]:
                raise ValueError("SOURCE_EVENT_COUNT_MISMATCH")
            if set(events["game_id"].dropna().unique()) != {rec["match_id"]}:
                raise ValueError("CROSS_MATCH_EVENTS")
            actions = convert_to_actions(events, home_team_id=rec["home_team_id"])
        named = spadl.add_names(actions)
        if set(actions["team_id"].dropna().unique()) != {
            rec["home_team_id"], rec["away_team_id"]
        }:
            raise ValueError("CROSS_MATCH_TEAM_IDS")
        summarize_spadl_rows_for_match(named.to_dict(orient="records"), rec)
        return actions


def summarize_spadl_rows_for_match(rows, rec):
    """Reuse strict single-match geometry/clock rules with remapped IDs.

    Reuse the existing shape gate only for the first StatsBomb sample.
    Other match IDs are validated here using a bounded pure-Python contract.
    """
    if type(rows) is not list or not 1 <= len(rows) <= 20_000:
        raise ValueError("INVALID_SPADL_COUNT")
    clock_by_period = {}
    for n, r in enumerate(rows):
        if type(r) is not dict:
            raise ValueError("INVALID_SPADL_ROW")
        if r.get("game_id") != rec["match_id"] or r.get("action_id") != n:
            raise ValueError("CROSS_MATCH_OR_ACTION_ID")
        if r.get("team_id") not in (rec["home_team_id"], rec["away_team_id"]):
            raise ValueError("UNKNOWN_ACTION_TEAM")
        period, clock = r.get("period_id"), r.get("time_seconds")
        if type(period) is not int or period not in (1, 2):
            raise ValueError("INVALID_ACTION_PERIOD")
        if type(clock) is bool or not isinstance(clock, (int, float)) or not math.isfinite(clock) or clock < 0:
            raise ValueError("INVALID_ACTION_CLOCK")
        previous = clock_by_period.get(period)
        if previous is not None and clock < previous:
            raise ValueError("ACTION_TIME_REVERSED")
        clock_by_period[period] = clock
        for axis, max_value in (("start_x", 105), ("end_x", 105),
                                ("start_y", 68), ("end_y", 68)):
            coordinate = r.get(axis)
            if (type(coordinate) is bool or not isinstance(coordinate, (int, float))
                    or not math.isfinite(coordinate) or not 0 <= coordinate <= max_value):
                raise ValueError("INVALID_ACTION_COORDINATES")
        if not isinstance(r.get("type_name"), str) or not r["type_name"]:
            raise ValueError("INVALID_ACTION_CATEGORY")
    if not any(r["team_id"] == rec["home_team_id"] for r in rows):
        raise ValueError("MISSING_HOME_ACTIONS")
    if not any(r["team_id"] == rec["away_team_id"] for r in rows):
        raise ValueError("MISSING_AWAY_ACTIONS")
    return len(rows)


def fit_and_rate_historical_xt(manifest, frozen):
    """ONLY train on the train group; rate eval, never fit eval.

    No quantitative accuracy metric, no cross-validation claim. The data
    itself was recorded after match final; date splitting cannot certify
    pre-match feature timestamps or real historical forward availability.
    """
    train, holdout = validate_manifest(manifest)
    if set(frozen) != {m["match_id"] for m in train + holdout}:
        raise ValueError("UNVERIFIED_MATCH_SOURCE_COVERAGE")
    runtime = _versions()
    import pandas as pd
    import numpy as np
    from socceraction.xthreat import ExpectedThreat

    train_frames = [_load_one_statsbomb_match(rec, frozen) for rec in train]
    holdout_frames = [_load_one_statsbomb_match(rec, frozen) for rec in holdout]
    trained_on = [rec["match_id"] for rec in train]
    rated_on = [rec["match_id"] for rec in holdout]
    if set(trained_on) & set(rated_on):
        raise ValueError("TRAIN_HOLDOUT_ID_CONTAMINATION")
    training = pd.concat(train_frames, ignore_index=True)
    heldout = pd.concat(holdout_frames, ignore_index=True)
    if set(training["game_id"].unique()) != set(trained_on):
        raise ValueError("TRAIN_FRAME_LEAKAGE")
    if set(heldout["game_id"].unique()) != set(rated_on):
        raise ValueError("HOLDOUT_FRAME_LEAKAGE")
    xt = ExpectedThreat(l=GRID_SHAPE[1], w=GRID_SHAPE[0], eps=1e-5)
    import io
    from contextlib import redirect_stdout
    with redirect_stdout(io.StringIO()):
        xt.fit(training)
    if (xt.xT.shape != GRID_SHAPE or not np.isfinite(xt.xT).all()
            or np.any(xt.xT < 0) or np.any(xt.xT > 1)):
        raise ValueError("INVALID_RESEARCH_XT_SURFACE")
    with redirect_stdout(io.StringIO()):
        values = xt.rate(heldout, use_interpolation=False)
    finite = np.isfinite(values)
    if len(values) != len(heldout) or int(finite.sum()) < MIN_RATED_HELDOUT_ACTIONS:
        raise ValueError("INVALID_HOLDOUT_RATING_COVERAGE")
    return {
        "schema": SCHEMA,
        "status": "RESEARCH_ONLY",
        "upstream_repo": "hudl/open-data",
        "upstream_commit": SOURCE_COMMIT,
        "competition_id": 43, "season_id": 106,
        "match_index_sha256": SOURCE_INDEX_SHA256,
        "train_match_ids": trained_on,
        "holdout_match_ids": rated_on,
        "train_through": TRAIN_END.isoformat(),
        "embargo_date": EMBARGO.isoformat(),
        "holdout_from": EVAL_BEGIN.isoformat(),
        "train_match_count": len(train),
        "holdout_match_count": len(holdout),
        "train_action_count": len(training),
        "holdout_action_count": len(heldout),
        "heldout_rated_action_count": int(finite.sum()),
        "xt_surface_shape": list(GRID_SHAPE),
        "xt_surface_sha256": sha256(xt.xT.tobytes()).hexdigest(),
        "runtime_versions": runtime,
        "historical_only_no_prospective_capture": True,
        "train_test_split_not_prospective_certification": True,
        "source_capture_independently_verified": False,
        "commercial_data_rights_verified": False,
        "xt_research_surface_fitted": True,
        "vaep_model_trained": False,
        "predictive_accuracy_improvement_verified": False,
        "positive_ev_verified": False,
        "forward_samples_certified": 0,
        "model_promoted": False,
        "production_recommendations": "DISABLED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline 12+4 historic xT research smoke")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--data-root", required=True)
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        frozen = verify_all_historical_sources(args.data_root, manifest)
        result = fit_and_rate_historical_xt(manifest, frozen)
    except (OSError, ValueError, ImportError, KeyError, TypeError) as exc:
        print("HOLD: " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
