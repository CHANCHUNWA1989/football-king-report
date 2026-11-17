"""Offline A + genuine optional Penaltyblog Poisson/DC same-cutoff handoff.

This never verifies authorship, model inputs, historical timestamps, legal
rights, model improvement or a third-party clock. The standard-library
snapshot is a non-certified integrity envelope, not a signed forecast.
No network fetch, result settlement, bookmaker odds, EV, promotion or bets.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

from .penaltyblog_research_bridge import (
    SCHEMA as BRIDGE_SCHEMA, PAIRED_MODELS, _validate, _timestamp, _id, evaluate,
)

SCHEMA = "football-king-prekickoff-a-penaltyblog-dual-handoff-v1"
A_MODEL = "poisson-shrinkage-unvalidated-v4.1"
A_FIELDS = {
    "source_namespace", "event_id", "league_id", "home_team_id",
    "away_team_id", "kickoff_utc", "produced_utc",
    "max_input_received_utc", "model_id", "probabilities",
    "source_authenticity_verified", "independently_timestamped",
    "production_recommendations",
}
MAX_AGE = timedelta(minutes=120)
KICKOFF_BUFFER = timedelta(minutes=10)
MAX_INPUT_BYTES = 8_000_000


def _hold(reason, **extras):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED",
        "positive_ev_verified": False, "model_promoted": False,
        "independent_provenance_verified": False,
        "trusted_clock_verified": False,
        "historical_results_independently_verified": False,
        "original_a_source_authenticated": False,
        "certified_prospective_samples": 0,
        "eligible_for_model_scoring": False,
        **extras,
    }


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _p3(value):
    return (type(value) is list and len(value) == 3
            and all(type(v) in (int, float) and math.isfinite(v)
                    and 0 <= v <= 1 for v in value)
            and abs(sum(value) - 1) <= 1e-6)


def _clock_value(clock):
    value = clock()
    if (type(value) is not datetime or value.tzinfo is None
            or value.utcoffset() is None):
        raise ValueError("INVALID_LOCAL_CLOCK")
    return value.astimezone(timezone.utc)


def capture(payload, *, clock=None, model_factories=None):
    """Run the two real optional models against A's *claimed* source/cutoff.

    The model functions are invoked here, not accepted as caller-provided
    predictions. A native-ID mapping and source timestamps must already be
    available in the supplied A input; NEVER fabricate these from team names.
    """
    if (type(payload) is not dict or
            set(payload) != {"schema", "production_recommendations",
                             "decision_cutoff_utc", "original_a",
                             "historical_matches"} or
            payload["schema"] != SCHEMA or
            payload["production_recommendations"] != "DISABLED"):
        return _hold("INVALID_HANDOFF_CONTRACT")
    original = payload["original_a"]
    if type(original) is not dict or set(original) != A_FIELDS:
        return _hold("INVALID_ORIGINAL_A_CONTRACT")
    try:
        if (original["model_id"] != A_MODEL
                or original["production_recommendations"] != "DISABLED"
                or original["source_authenticity_verified"] is not False
                or original["independently_timestamped"] is not False
                or not _p3(original["probabilities"])):
            raise ValueError("INVALID_ORIGINAL_A_UNVERIFIED_SNAPSHOT")
        for key in ("event_id", "league_id", "home_team_id", "away_team_id"):
            _id(original[key])
        _id(original["source_namespace"], namespace=True)
        if original["home_team_id"] == original["away_team_id"]:
            raise ValueError("INVALID_ORIGINAL_A_TEAM_IDENTITY")
        target = {key: original[key] for key in (
            "source_namespace", "event_id", "league_id", "home_team_id",
            "away_team_id", "kickoff_utc")}
        cutoff = _timestamp(payload["decision_cutoff_utc"])
        kickoff = _timestamp(original["kickoff_utc"])
        produced = _timestamp(original["produced_utc"])
        input_received = _timestamp(original["max_input_received_utc"])
        if not input_received <= produced <= cutoff <= kickoff - KICKOFF_BUFFER:
            raise ValueError("ORIGINAL_A_LOOKAHEAD_OR_KICKOFF_BUFFER")
        if cutoff - produced > MAX_AGE:
            raise ValueError("STALE_ORIGINAL_A_SNAPSHOT")
        bridge = {
            "schema": BRIDGE_SCHEMA,
            "production_recommendations": "DISABLED",
            "as_of_utc": payload["decision_cutoff_utc"],
            "model": "poisson",
            "target_fixture": target,
            "historical_matches": payload["historical_matches"],
        }
        # Validate complete history BEFORE any actual model import or fitting.
        _validate(bridge)
        history_digest = hashlib.sha256(_canonical({
            "history": payload["historical_matches"], "target": target,
            "decision_cutoff_utc": payload["decision_cutoff_utc"],
        })).hexdigest()
        original_digest = hashlib.sha256(_canonical(original)).hexdigest()
        timer = clock if clock is not None else lambda: datetime.now(timezone.utc)
        if not callable(timer):
            raise ValueError("INVALID_LOCAL_CLOCK")
        started = _clock_value(timer)
        if (not produced <= started <= cutoff
                or cutoff - started > MAX_AGE
                or not started < kickoff - KICKOFF_BUFFER):
            raise ValueError("NOT_CAPTURED_WITHIN_DECLARED_PREMATCH_WINDOW")
        observations = []
        previous = started
        for name in PAIRED_MODELS:
            params = dict(bridge, model=name)
            factory = None if model_factories is None else model_factories.get(name)
            if model_factories is not None and (type(model_factories) is not dict
                                                or set(model_factories) != set(PAIRED_MODELS)
                                                or not callable(factory)):
                raise ValueError("INVALID_RESEARCH_MODEL_FACTORY")
            outcome = evaluate(params, model_factory=factory)
            if (outcome.get("status") != "RESEARCH_ONLY"
                    or outcome.get("reason") != "RESEARCH_ONLY_UNVERIFIED_INPUT"
                    or outcome.get("production_recommendations") != "DISABLED"
                    or outcome.get("source_authenticity_verified") is not False
                    or outcome.get("prospective_capture_verified") is not False
                    or outcome.get("positive_ev_verified") is not False
                    or outcome.get("model_promoted") is not False
                    or outcome.get("is_sealed_original_forecast") is not False
                    or outcome.get("fixture_id") != target["event_id"]
                    or outcome.get("source_namespace") != target["source_namespace"]
                    or outcome.get("league_id") != target["league_id"]
                    or _timestamp(outcome.get("as_of_utc")) != cutoff
                    or _timestamp(outcome.get("kickoff_utc")) != kickoff
                    or outcome.get("model_id") != "penaltyblog-" + name + "-offline-challenger-v1"
                    or type(outcome.get("training_match_count")) is not int
                    or not _p3([outcome.get("p_home"), outcome.get("p_draw"),
                                outcome.get("p_away")])):
                raise ValueError("MODEL_UNAVAILABLE_OR_UNTRUSTED")
            ended = _clock_value(timer)
            if not previous <= ended <= cutoff or not ended < kickoff - KICKOFF_BUFFER:
                raise ValueError("MODEL_EXECUTION_CROSSED_PREMATCH_WINDOW")
            observations.append({
                "model_id": outcome["model_id"],
                "model": name,
                "local_model_started_utc": previous.isoformat(),
                "local_model_finished_utc": ended.isoformat(),
                "training_match_count": outcome["training_match_count"],
                "probabilities": [outcome["p_home"], outcome["p_draw"],
                                  outcome["p_away"]],
                "source_authenticity_verified": False,
                "independently_timestamped": False,
            })
            previous = ended

        # It is a reproducible content digest, NOT a third-party time witness.
        body = {
            "source_namespace": target["source_namespace"],
            "event_id": target["event_id"],
            "league_id": target["league_id"],
            "home_team_id": target["home_team_id"],
            "away_team_id": target["away_team_id"],
            "kickoff_utc": kickoff.isoformat(),
            "decision_cutoff_utc": cutoff.isoformat(),
            "first_local_capture_observed_utc": started.isoformat(),
            "last_local_capture_observed_utc": previous.isoformat(),
            "original_a_model_id": A_MODEL,
            "original_a_produced_utc_claimed": produced.isoformat(),
            "original_a_last_input_utc_claimed": input_received.isoformat(),
            "original_a_probabilities": list(original["probabilities"]),
            "original_a_input_sha256_unattested": original_digest,
            "historical_training_input_sha256_unattested": history_digest,
            "challenger_observations": observations,
            "forecast_source_authenticity_verified": False,
            "local_clock_is_independent_timestamp_attestation": False,
        }
        digest = hashlib.sha256(_canonical(body)).hexdigest()
        return _hold(
            "LOCAL_A_POISSON_DC_CAPTURE_NOT_EXTERNALLY_ATTESTED",
            unverified_triple_capture=body,
            locally_reproducible_capture_sha256=digest,
            models_completed_before_declared_cutoff_by_local_clock=True,
            note=("A original identity and claimed source times are user/producer "
                  "supplied; actual local model completion does not prove external "
                  "UTC custody, data rights, OOS skill, bookmaker prices or EV."),
        )
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError,
            RecursionError) as exc:
        reason = str(exc)
        return _hold(reason if len(reason) <= 120 else "INVALID_OR_UNTRUSTED_CAPTURE")


def _unique(pairs):
    out = {}
    for name, value in pairs:
        if name in out:
            raise ValueError("DUPLICATE_JSON_KEY")
        out[name] = value
    return out


def _read_input(path):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("UNSAFE_INPUT_SYMLINK")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                         | getattr(os, "O_NONBLOCK", 0))
    try:
        meta = os.fstat(descriptor)
        if (not stat.S_ISREG(meta.st_mode) or not 0 < meta.st_size <= MAX_INPUT_BYTES):
            raise ValueError("INVALID_INPUT_FILE_OR_SIZE")
        raw = b""
        while len(raw) <= MAX_INPUT_BYTES:
            part = os.read(descriptor, min(65536, MAX_INPUT_BYTES + 1 - len(raw)))
            if not part:
                break
            raw += part
        if len(raw) != meta.st_size:
            raise ValueError("INPUT_CHANGED_DURING_READ")
    finally:
        os.close(descriptor)
    return json.loads(raw, object_pairs_hook=_unique, parse_constant=lambda _:
                      (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if Path(args.input).absolute() == Path(args.output).absolute():
            raise ValueError("INPUT_OUTPUT_ALIAS")
        payload = _read_input(args.input)
        report = capture(payload)
        if "unverified_triple_capture" not in report:
            print(json.dumps({"status": "HOLD", "reason": report["reason"],
                              "production_recommendations": "DISABLED"}))
            return 1
        encoded = _canonical(report) + b"\n"
        # No parent mkdir; no overwrite or symlink following; private results.
        if any(p.is_symlink() for p in (Path(args.output), *Path(args.output).parents)):
            raise ValueError("UNSAFE_OUTPUT_SYMLINK")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(args.output, flags, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(encoded)
            out.flush()
            os.fsync(out.fileno())
        print(json.dumps({"status": "HOLD", "reason": report["reason"],
                          "private_unattested_capture_created": True,
                          "production_recommendations": "DISABLED"}))
        return 0
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)[:120],
                          "production_recommendations": "DISABLED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
