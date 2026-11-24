"""Offline, source-hash pinned StatsBomb -> Socceraction SPADL feasibility test.

NO model training, feature promotion, odds, bets or commercial data license.
Raw provider JSON stays only inside a disposable private directory. Kloppy
3.19.1 -> Socceraction 1.5.3 converter is explicitly NOT used here because
its coordinate-system constructor fails in the observed integration.
"""
from collections import Counter
from importlib import metadata
import argparse
import json
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from ops.kloppy_statsbomb_offline_research import (
    EVENTS_BYTES, EVENTS_SHA256, LINEUPS_BYTES, LINEUPS_SHA256,
    MATCH_ID, PROVIDER_README, UPSTREAM_COMMIT, _read_fixed_file,
)

OUTPUT_SCHEMA = "football-king-socceraction-spadl-feasibility-v1"
REQUIRED_INSTALLED_VERSIONS = {
    "socceraction": "1.5.3",
    "pandera": "0.17.2",
    "multimethod": "1.12",
}
HOME_TEAM = 909
AWAY_TEAM = 914
MAX_ACTIONS = 20000
FIELD_LENGTH = 105.0
FIELD_WIDTH = 68.0


def _ensure_optional_package_versions():
    versions = {}
    for name, required in REQUIRED_INSTALLED_VERSIONS.items():
        try:
            found = metadata.version(name)
        except metadata.PackageNotFoundError:
            raise ValueError("RESEARCH_PACKAGE_NOT_INSTALLED") from None
        if found != required:
            raise ValueError("UNVERIFIED_RESEARCH_PACKAGE_VERSION")
        versions[name] = found
    return versions


def summarize_spadl_rows(rows):
    """Strict fail-closed pure-Python validation of in-memory action rows.

    This is a unit-testable *schema boundary*, not action-value modelling.
    Coordinates must be within the SPADL standardized 105x68 m pitch and
    timestamps nondecreasing within periods. Unknown teams or cross-match
    actions are rejected before returning any descriptive counts.
    """
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ACTIONS:
        raise ValueError("INVALID_SPADL_ACTION_COUNT")
    types = Counter()
    teams = Counter()
    last_clock = None
    last_period = None
    for index, action in enumerate(rows):
        if not isinstance(action, dict):
            raise ValueError("INVALID_SPADL_ACTION_ROW")
        if action.get("game_id") != int(MATCH_ID):
            raise ValueError("CROSS_MATCH_SPADL_ACTION")
        if action.get("action_id") != index:
            raise ValueError("SPADL_ACTION_INDEX_MISMATCH")
        team = action.get("team_id")
        if type(team) is bool or team not in (HOME_TEAM, AWAY_TEAM):
            raise ValueError("UNKNOWN_SPADL_TEAM")
        period = action.get("period_id")
        if type(period) is bool or period not in (1, 2):
            raise ValueError("INVALID_SPADL_PERIOD")
        clock = action.get("time_seconds")
        if type(clock) is bool:
            raise ValueError("INVALID_SPADL_CLOCK")
        try:
            clock = float(clock)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("INVALID_SPADL_CLOCK") from None
        if not math.isfinite(clock) or clock < 0:
            raise ValueError("INVALID_SPADL_CLOCK")
        if (last_period is not None and
                (period < last_period or
                 (period == last_period and clock < last_clock))):
            raise ValueError("SPADL_ACTIONS_OUT_OF_ORDER")
        last_period, last_clock = period, clock

        for axis, upper in (("start_x", FIELD_LENGTH), ("end_x", FIELD_LENGTH),
                            ("start_y", FIELD_WIDTH), ("end_y", FIELD_WIDTH)):
            number = action.get(axis)
            if type(number) is bool:
                raise ValueError("INVALID_SPADL_COORDINATES")
            try:
                number = float(number)
            except (TypeError, ValueError, OverflowError):
                raise ValueError("INVALID_SPADL_COORDINATES") from None
            if not math.isfinite(number) or not 0 <= number <= upper:
                raise ValueError("INVALID_SPADL_COORDINATES")

        action_type = action.get("type_name")
        if (type(action_type) is not str or not action_type
                or len(action_type) > 64 or action_type != action_type.strip()):
            raise ValueError("INVALID_SPADL_ACTION_TYPE")
        types[action_type] += 1
        teams[str(team)] += 1
    if not teams.get(str(HOME_TEAM)) or not teams.get(str(AWAY_TEAM)):
        raise ValueError("BOTH_TEAMS_MUST_HAVE_SPADL_ACTIONS")
    return {"action_count": len(rows), "action_type_counts": dict(sorted(types.items())),
            "team_action_counts": dict(sorted(teams.items()))}


def summarize_verified_historical_spadl(events_path, lineups_path):
    """Convert one exact local official StatsBomb sample without any network.

    The file hashes are from the immutable official public-research commit.
    StatsBombLoader local API expects a local directory with event files.
    Writing verified BytesIO bytes into a newly created temporary directory
    avoids reading changed files after the hash check. No raw files are
    committed or added to the returned report.
    """
    event_bytes = _read_fixed_file(events_path, EVENTS_BYTES, EVENTS_SHA256)
    lineup_bytes = _read_fixed_file(lineups_path, LINEUPS_BYTES, LINEUPS_SHA256)
    versions = _ensure_optional_package_versions()

    # Import *after* source/hash/version checks. These optional packages are
    # never imported by default VNext CI or the production release gate.
    from socceraction import spadl
    from socceraction.data.statsbomb import StatsBombLoader
    from socceraction.spadl.statsbomb import convert_to_actions

    with TemporaryDirectory(prefix="fk-spadl-local-") as workdir:
        root = Path(workdir)
        (root / "events").mkdir()
        (root / "lineups").mkdir()
        (root / "events" / (MATCH_ID + ".json")).write_bytes(event_bytes)
        (root / "lineups" / (MATCH_ID + ".json")).write_bytes(lineup_bytes)
        loader = StatsBombLoader(getter="local", root=str(root))
        native_events = loader.events(int(MATCH_ID))
        if len(native_events) != 3803:
            raise ValueError("OFFICIAL_RAW_EVENT_COUNT_MISMATCH")
        if set(native_events["game_id"].dropna().unique()) != {int(MATCH_ID)}:
            raise ValueError("MISMATCHED_NATIVE_MATCH_ID")
        if set(native_events["team_id"].dropna().unique()) != {HOME_TEAM, AWAY_TEAM}:
            raise ValueError("MISMATCHED_NATIVE_TEAM_IDS")
        actions = convert_to_actions(native_events, home_team_id=HOME_TEAM)
        named_actions = spadl.add_names(actions)
        summary = summarize_spadl_rows(named_actions.to_dict(orient="records"))

    return {
        "schema": OUTPUT_SCHEMA,
        "status": "RESEARCH_ONLY",
        "provider": "StatsBomb Open Data",
        "upstream_commit": UPSTREAM_COMMIT,
        "source_event_id": MATCH_ID,
        "rights_reference_url": PROVIDER_README,
        "source_sha256": {"events": EVENTS_SHA256, "lineups": LINEUPS_SHA256},
        "raw_events": 3803,
        **summary,
        "socceraction_runtime_versions": versions,
        "conversion_path": "socceraction_statsbomb_local_to_spadl",
        "kloppy_to_spadl_converter_verified": False,
        "post_match_description_only": True,
        "historical_sample_not_certified_prospective": True,
        "commercial_data_rights_verified": False,
        "source_capture_independently_verified": False,
        "model_trained": False,
        "xt_model_trained": False,
        "vaep_model_trained": False,
        "predictive_accuracy_improvement_verified": False,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="One-match, offline research-only SPADL conversion")
    parser.add_argument("--events", required=True)
    parser.add_argument("--lineups", required=True)
    args = parser.parse_args(argv)
    try:
        report = summarize_verified_historical_spadl(args.events, args.lineups)
    except (OSError, ValueError, ImportError, KeyError) as exc:
        print("HOLD: " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
