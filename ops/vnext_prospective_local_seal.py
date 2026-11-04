"""VNext PR-06: offline write-once prospective forecast capture and source audit.

Uses a local O_EXCL file and caller-supplied hashes only. A local clock and
filesystem are NOT externally witnessed, tamper-proof, or source-authenticated.
Never publish raw proprietary content or pretend that two URLs are independent.
"""
import hashlib
import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

from vnext_shadow_forward_audit import _clock, _id, _model, _sha
from ops.trusted_result_evidence import _policy

SCHEMA = "football-king-vnext-prospective-local-seal-v1"
MAX_BYTES = 65536
MAX_SOURCE_REFS = 16
SOURCE_FIELDS = frozenset({
    "provider", "source_event_id", "source_group", "source_updated_utc",
    "received_utc", "available_utc", "raw_sha256", "rights_scope",
})
RESULT_SOURCE_FIELDS = frozenset({
    "provider", "fixture_id", "provider_fixture_id", "source_scope",
    "home_goals", "away_goals", "source_updated_utc", "received_utc",
    "raw_sha256",
})
RIGHTS_SCOPE = "DERIVED_METADATA_ONLY_UNVERIFIED"


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _unique(pairs):
    output = {}
    for k, v in pairs:
        if k in output:
            raise ValueError("DUPLICATE_JSON_KEY")
        output[k] = v
    return output


def _reject_constant(value):
    raise ValueError("NONFINITE_JSON_NUMBER")


def _as_bytes(payload):
    raw = _dump(payload)
    if len(raw) > MAX_BYTES:
        raise ValueError("SNAPSHOT_TOO_LARGE")
    return raw


def _directory(root):
    path = Path(root)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("INVALID_LOCAL_ARCHIVE_DIRECTORY")
    mode = path.stat().st_mode
    if mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ValueError("INSECURE_ARCHIVE_DIRECTORY_PERMISSIONS")
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def _input_pair(pair, sources, *, now):
    if type(pair) is not dict or set(pair) != {
        "fixture_id", "kickoff_utc", "as_of_utc", "models"
    }:
        raise ValueError("INVALID_FROZEN_PAIR")
    fid = pair["fixture_id"]
    if not _id(fid):
        raise ValueError("INVALID_FIXTURE_ID")
    kickoff, as_of = _clock(pair["kickoff_utc"]), _clock(pair["as_of_utc"])
    if not as_of <= now <= as_of + timedelta(minutes=2):
        raise ValueError("FORECAST_NOT_CAPTURED_PROMPTLY")
    if not now <= kickoff - timedelta(minutes=10):
        raise ValueError("SNAPSHOT_NOT_PREMATCH")
    models = pair["models"]
    if type(models) is not dict or set(models) != {"baseline", "challenger"}:
        raise ValueError("REQUIRE_TWO_MATCHED_MODELS")
    _model(models["baseline"], kickoff=kickoff, as_of=as_of)
    _model(models["challenger"], kickoff=kickoff, as_of=as_of)
    if models["baseline"]["model_id"] == models["challenger"]["model_id"]:
        raise ValueError("DUPLICATE_MODEL_ID")
    if type(sources) is not list or not 1 <= len(sources) <= MAX_SOURCE_REFS:
        raise ValueError("INVALID_SOURCE_REFERENCE_COLLECTION")
    seen = set()
    for item in sources:
        if type(item) is not dict or set(item) != SOURCE_FIELDS:
            raise ValueError("INVALID_SOURCE_REFERENCE_SCHEMA")
        if (any(not _id(item[k]) for k in ("provider", "source_event_id", "source_group"))
                or not _sha(item["raw_sha256"])
                or item["rights_scope"] != RIGHTS_SCOPE):
            raise ValueError("INVALID_SOURCE_REFERENCE_OR_RIGHTS")
        source, received, available = (
            _clock(item["source_updated_utc"]),
            _clock(item["received_utc"]),
            _clock(item["available_utc"]),
        )
        if not source <= received <= available <= as_of:
            raise ValueError("LATE_SOURCE_OR_INVALID_ORDER")
        key = (item["provider"], item["source_event_id"])
        if key in seen:
            raise ValueError("DUPLICATE_SOURCE_REFERENCE")
        seen.add(key)
    return kickoff, as_of


def seal_forecast_pair(root, pair, source_refs, *, captured_utc=None):
    """Write one new pair using O_EXCL/0600, never update or overwrite.

    captured_utc is an explicit synthetic-test hook; caller can spoof it,
    hence every output permanently says external_clock_attested=False.
    """
    now = (_clock(captured_utc) if captured_utc is not None
           else datetime.now(timezone.utc))
    _input_pair(pair, source_refs, now=now)
    item = {
        "schema": SCHEMA,
        "pair": pair, "source_refs": source_refs,
        "recorded_at_utc": now.isoformat().replace("+00:00", "Z"),
        "source_independence_authenticated": False,
        "external_clock_attested": False,
        "source_rights_independently_verified": False,
        "results_contained": False,
        "production_recommendations": "DISABLED",
    }
    raw = _as_bytes(item)
    digest = _digest(raw)
    name = _digest((pair["fixture_id"] + "|" + pair["as_of_utc"]).encode("utf-8")) + ".json"
    directory_fd = _directory(root)
    try:
        descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory_fd)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return {
        "status": "LOCAL_SEALED_RESEARCH", "file_name": name,
        "content_sha256": digest, "byte_count": len(raw),
        "external_clock_attested": False,
        "independent_source_verification": False,
        "model_eligible_for_promotion": False,
        "production_recommendations": "DISABLED",
    }


def read_forecast_seal(root, file_name, *, expected_sha256):
    """Verify unchanged local bytes against a separately supplied anchor.

    This cannot authenticate the anchor itself; externally pin it separately.
    """
    if (type(file_name) is not str or len(file_name) != 69
            or not file_name.endswith(".json") or not _sha(file_name[:-5])
            or not _sha(expected_sha256)):
        raise ValueError("INVALID_SEAL_REFERENCE")
    directory_fd = _directory(root)
    try:
        fd = os.open(file_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        try:
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_BYTES + 1)
        finally:
            os.close(fd)
    finally:
        os.close(directory_fd)
    if not raw or len(raw) > MAX_BYTES or _digest(raw) != expected_sha256:
        raise ValueError("ARCHIVE_INTEGRITY_OR_SIZE_FAILURE")
    data = json.loads(raw, object_pairs_hook=_unique, parse_constant=_reject_constant)
    if type(data) is not dict or set(data) != {
        "schema", "pair", "source_refs", "recorded_at_utc",
        "source_independence_authenticated", "external_clock_attested",
        "source_rights_independently_verified", "results_contained",
        "production_recommendations"
    }:
        raise ValueError("INVALID_SEALED_RECORD")
    if (data["schema"] != SCHEMA or data["source_independence_authenticated"] is not False
            or data["external_clock_attested"] is not False
            or data["source_rights_independently_verified"] is not False
            or data["results_contained"] is not False
            or data["production_recommendations"] != "DISABLED"):
        raise ValueError("UNSAFE_OR_FALSELY_CERTIFIED_SEAL")
    _input_pair(data["pair"], data["source_refs"], now=_clock(data["recorded_at_utc"]))
    inferred = _digest((data["pair"]["fixture_id"] + "|"
                        + data["pair"]["as_of_utc"]).encode("utf-8")) + ".json"
    if inferred != file_name:
        raise ValueError("SEAL_FILE_IDENTITY_MISMATCH")
    return data


def audit_source_independence(observations, *, fixture_id, decision_utc):
    """Use the existing HASH-PINNED source policy, never caller policy.

    A consistent two-source display can be AGREED_UNVERIFIED. Unknown upstream
    relationship and rights prevent independently confirmed result admission.
    """
    out = {
        "status": "HOLD", "observation_agreement": False,
        "source_independence_authenticated": False,
        "licensed_data_rights_verified": False,
        "independent_result_authentication": False,
        "model_scoring_eligible": False,
        "production_recommendations": "DISABLED",
    }
    try:
        policy = _policy()  # Existing repo SHA-pinned restrictive policy.
        if type(observations) is not list or len(observations) != 2:
            raise ValueError("TWO_RESULT_SOURCE_OBSERVATIONS_REQUIRED")
        if not _id(fixture_id):
            raise ValueError("INVALID_FIXTURE_ID")
        deadline = _clock(decision_utc)
        for row in observations:
            if type(row) is not dict or set(row) != RESULT_SOURCE_FIELDS:
                raise ValueError("INVALID_RESULT_SOURCE_SCHEMA")
            if (row["provider"] not in policy["providers"]
                    or row["fixture_id"] != fixture_id
                    or row["source_scope"] != policy["scope"]
                    or not _id(row["provider_fixture_id"])
                    or not _sha(row["raw_sha256"])
                    or any(type(row[k]) is not int or not 0 <= row[k] <= 30
                           for k in ("home_goals", "away_goals"))):
                raise ValueError("SOURCE_OUTSIDE_FIXED_POLICY_OR_IDENTITY")
            if not (_clock(row["source_updated_utc"])
                    <= _clock(row["received_utc"]) <= deadline):
                raise ValueError("SOURCE_RESULT_NOT_AVAILABLE")
        a, b = observations
        if a["provider"] == b["provider"]:
            raise ValueError("DUPLICATE_PROVIDER")
        if (a["home_goals"], a["away_goals"]) != (b["home_goals"], b["away_goals"]):
            raise ValueError("RESULT_SOURCE_SCORE_CONFLICT")
        return {
            **out, "observation_agreement": True,
            "reason": "AGREED_UNVERIFIED_UPSTREAM_AND_LICENSE_SCOPE",
            "source_policy_id": policy["policy_id"],
            "source_policy_scope": policy["scope"],
            "providers": sorted([a["provider"], b["provider"]]),
        }
    except (TypeError, ValueError, KeyError, OSError, OverflowError) as exc:
        return {**out, "reason": str(exc) or "SOURCE_POLICY_OR_INPUT_REJECTED"}
