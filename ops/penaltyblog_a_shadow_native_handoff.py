"""Strict optional adapter from *actual original A shadow output* to Penaltyblog.

Uses ONLY same-response typed OpenLigaDB IDs from the A producer, never team
names or post-hoc outcome/alias maps. All source timestamps remain untrusted.
Its output is an unsigned local research HOLD, not a certified prospective
forecast, legal data entitlement, or betting advice.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re

from .penaltyblog_a_dual_prematch_capture import (
    A_MODEL, SCHEMA as CAPTURE_SCHEMA, capture, _canonical, _hold, _read_input,
)
from .penaltyblog_research_bridge import _timestamp


SCHEMA = "football-king-shadow-a-native-id-prematch-handoff-v1"
NATIVE_SCHEMA = "football-king-native-fixture-input-observation-v1"
NATIVE_FIELDS = {
    "schema", "status", "provider", "match_id", "home_team_id",
    "away_team_id", "league_id", "league_shortcut", "league_season",
    "source_response_sha256",
    "native_ids_from_same_response_as_gateway_fixture",
    "source_identity_authenticated", "source_capture_authenticated",
    "raw_input_durably_archived", "native_ids_used_as_model_features",
    "eligible_for_model_scoring",
}


def _reject(reason):
    return {**_hold(reason), "shadow_a_native_identity_reused_without_mapping": False}


def _numeric_native(value):
    return type(value) is int and 0 < value <= 2**63 - 1


def _sha(s):
    return type(s) is str and re.fullmatch(r"[0-9a-f]{64}", s) is not None


def link(shadow, history, *, event_id, cutoff_utc, clock=None,
         model_factories=None):
    """Inspect one A-generated native fixture and invoke both real challengers.

    This adapter cannot create missing IDs or timestamps. It merely matches
    existing raw-response hash metadata to source-captured timestamps, and
    transfers explicitly *unattested* values to the offline dual-model gate.
    """
    if (type(shadow) is not dict or type(history) is not list or
            type(event_id) is not str or
            not re.fullmatch(r"openligadb:[1-9][0-9]{0,18}", event_id)
            or type(cutoff_utc) is not str):
        return _reject("INVALID_SHADOW_HANDOFF_INPUT")
    try:
        if (shadow.get("schema") != "football-king-uncalibrated-shadow-1"
                or shadow.get("production_recommendations") != "DISABLED"
                or shadow.get("status") != "SHADOW_ONLY"
                or shadow.get("independently_verified_results") is not False
                or shadow.get("market_odds_available") is not False
                or shadow.get("model_calibrated") is not False
                or type(shadow.get("predictions")) is not list
                or type(shadow.get("sources")) is not list
                or type(shadow.get("predictions_count")) is not int
                or shadow["predictions_count"] != len(shadow["predictions"])
                or len(shadow["predictions"]) > 1000
                or len(shadow["sources"]) > 50):
            raise ValueError("INVALID_OR_UNTRUSTED_SHADOW_REPORT")
        generation = shadow.get("generation_clock")
        if (type(generation) is not dict
                or generation.get("mode") != "ACTUAL_BATCH_COMPUTATION_COMPLETION_UTC"
                or generation.get("sampled_clock_order_and_hk_day_valid") is not True
                or generation.get("reason") is not None
                or generation.get("source_capture_or_actual_kickoff_authenticated") is not False):
            raise ValueError("REPLAY_OR_UNVERIFIED_GENERATION_CLOCK")
        started = _timestamp(generation["started_utc"])
        completed = _timestamp(generation["completed_utc"])
        if started > completed or _timestamp(shadow["as_of_utc"]) != completed:
            raise ValueError("SHADOW_BATCH_CLOCK_CONTRADICTION")
        matches = [row for row in shadow["predictions"]
                   if type(row) is dict and row.get("event_id") == event_id]
        if len(matches) != 1:
            raise ValueError("MISSING_OR_AMBIGUOUS_A_FORECAST")
        p = matches[0]
        if (p.get("league") != "bundesliga"
                or p.get("model") != A_MODEL
                or p.get("production_recommendations") != "DISABLED"
                or p.get("calibrated") is not False
                or p.get("verified_market_odds") is not False
                or not all(type(p.get(k)) in (int, float) and
                           math.isfinite(p[k]) and 0 <= p[k] <= 1
                           for k in ("p_home", "p_draw", "p_away"))
                or abs(p["p_home"] + p["p_draw"] + p["p_away"] - 1) > 1e-6
                or _timestamp(p["prediction_utc"]) != completed):
            raise ValueError("INVALID_OR_MISSING_A_FORECAST_FIELDS")
        native = p.get("native_fixture_input")
        if type(native) is not dict or set(native) != NATIVE_FIELDS:
            raise ValueError("MISSING_TYPED_NATIVE_SOURCE_ID")
        if (native["schema"] != NATIVE_SCHEMA
                or native["status"] != "UNAUTHENTICATED"
                or native["provider"] != "OpenLigaDB"
                or native["league_shortcut"] != "bl1"
                or any(not _numeric_native(native[k]) for k in (
                    "match_id", "home_team_id", "away_team_id", "league_id",
                    "league_season"))
                or native["home_team_id"] == native["away_team_id"]
                or event_id != "openligadb:" + str(native["match_id"])
                or native["native_ids_from_same_response_as_gateway_fixture"] is not True
                or any(native[f] is not False for f in (
                    "source_identity_authenticated", "source_capture_authenticated",
                    "raw_input_durably_archived", "native_ids_used_as_model_features",
                    "eligible_for_model_scoring"))
                or not _sha(native["source_response_sha256"])):
            raise ValueError("INVALID_OR_SELF_CERTIFIED_NATIVE_EVIDENCE")
        season = shadow.get("season")
        if (type(season) is not str or
                not re.fullmatch(r"20[0-9]{2}-[0-9]{2}", season)
                or int(season[:4]) != native["league_season"]):
            raise ValueError("NATIVE_LEAGUE_SEASON_MISMATCH")
        if not p.get("kickoff_utc"):
            raise ValueError("MISSING_A_KICKOFF")
        kickoff = _timestamp(p["kickoff_utc"])
        sources = [s for s in shadow["sources"] if type(s) is dict and
                   s.get("league") == "bundesliga"]
        if len(sources) != 1:
            raise ValueError("AMBIGUOUS_A_SOURCE_REPORT")
        src = sources[0]
        if (src.get("source") != "OpenLigaDB" or
                src.get("status") != "READY_RESEARCH" or
                src.get("season") != season or
                src.get("training_and_candidate_source_unverified") is not True
                or src.get("source_response_sha256") != native["source_response_sha256"]):
            raise ValueError("SOURCE_RESPONSE_OR_LEAGUE_MISMATCH")
        captured = _timestamp(src["captured_utc"])
        if not started <= captured <= completed:
            raise ValueError("SOURCE_CAPTURE_NOT_WITHIN_A_GENERATION")
        # Compare input claims with already-present source observation ONLY.
        # Do not fabricate an external capture time from today's local clock.
        if not _sha(p.get("training_observations_sha256")):
            raise ValueError("UNPINNED_A_TRAINING_OBSERVATIONS")
        cutoff = _timestamp(cutoff_utc)
        if not completed <= cutoff < kickoff:
            raise ValueError("INVALID_LATER_DECISION_CUTOFF")
        original = {
            "source_namespace": "openligadb",
            "event_id": event_id,
            "league_id": str(native["league_id"]),
            "home_team_id": str(native["home_team_id"]),
            "away_team_id": str(native["away_team_id"]),
            "kickoff_utc": kickoff.isoformat(),
            "produced_utc": completed.isoformat(),
            "max_input_received_utc": captured.isoformat(),
            "model_id": A_MODEL,
            "probabilities": [p["p_home"], p["p_draw"], p["p_away"]],
            "source_authenticity_verified": False,
            "independently_timestamped": False,
            "production_recommendations": "DISABLED",
        }
        request = {
            "schema": CAPTURE_SCHEMA,
            "production_recommendations": "DISABLED",
            "decision_cutoff_utc": cutoff.isoformat(),
            "original_a": original,
            "historical_matches": history,
        }
        result = capture(request, clock=clock, model_factories=model_factories)
        if "unverified_triple_capture" not in result:
            return {**result, "shadow_a_native_identity_reused_without_mapping": False}
        return {
            **result,
            "shadow_a_native_identity_reused_without_mapping": True,
            "shadow_a_source_response_sha256_unattested": native["source_response_sha256"],
            "shadow_a_training_observations_sha256_unattested":
                p["training_observations_sha256"],
            "shadow_source_response_bytes_durably_archived": False,
            "shadow_source_time_independently_attested": False,
            "shadow_producer_source_authenticated": False,
        }
    except (ValueError, KeyError, TypeError, OverflowError, AttributeError) as exc:
        reason = str(exc)
        return _reject(reason if len(reason) <= 100 else "INVALID_SHADOW_NATIVE_HANDOFF")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shadow", required=True)
    parser.add_argument("--history", required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--decision-cutoff-utc", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        output = Path(args.output)
        if output.absolute() in (Path(args.shadow).absolute(),
                                 Path(args.history).absolute()):
            raise ValueError("OUTPUT_ALIASES_INPUT")
        shadow = _read_input(args.shadow)
        history = _read_input(args.history)
        result = link(shadow, history, event_id=args.event_id,
                      cutoff_utc=args.decision_cutoff_utc)
        if "unverified_triple_capture" not in result:
            print(json.dumps({"status": "HOLD", "reason": result["reason"],
                              "production_recommendations": "DISABLED"}))
            return 1
        if any(path.is_symlink() for path in (output, *output.parents)):
            raise ValueError("UNSAFE_OUTPUT_SYMLINK")
        encoded = _canonical(result) + b"\n"
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps({"status": "HOLD",
                          "private_unattested_three_model_capture_written": True,
                          "production_recommendations": "DISABLED"}))
        return 0
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)[:100],
                          "production_recommendations": "DISABLED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
