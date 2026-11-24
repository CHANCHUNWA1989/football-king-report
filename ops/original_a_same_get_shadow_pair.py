"""Offline, private, same-original-GET raw response <-> A forecast byte handoff.

Binds an *existing* private original-source tar to the *exact* original A
shadow file by raw-body SHA, source clocks, native IDs, team orientation and
kickoff. Produces a distinct immutable local shadow+link bundle referring to
the raw tar; no new HTTP requests. This NEVER certifies provider, time, model
performance, data rights, OOS or executable odds. All outputs stay HOLD.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import tarfile
import tempfile

from .original_a_same_get_private_seal import (
    _private_directory, _bundle as original_bundle, check_private_bundle,
)
from .penaltyblog_a_shadow_native_handoff import A_MODEL, NATIVE_FIELDS, NATIVE_SCHEMA

SCHEMA = "football-king-private-same-get-a-shadow-link-v1"
MAX_SHADOW = 2_000_000
MAX_LINK = 100_000
MAX_PAIR = 2_200_000
NAMES = ("shadow.json", "link.json")


def _hold(reason, **extra):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED",
        "positive_ev_verified": False, "certified_prospective_samples": 0,
        "eligible_for_model_scoring": False, "source_publisher_authenticated": False,
        "source_timestamp_attested": False,
        "forecast_timestamp_attested": False, "model_promoted": False,
        **extra,
    }


def _unique(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("DUPLICATE_JSON_KEY")
        out[k] = v
    return out


def _bad_constant(_):
    raise ValueError("NONFINITE_JSON")


def _json(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _read_json(raw):
    return json.loads(raw, object_pairs_hook=_unique, parse_constant=_bad_constant)


def _sha(value):
    return type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None


def _time(value):
    if type(value) is not str or not 15 < len(value) <= 80:
        raise ValueError("INVALID_TIME")
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if d.tzinfo is None or d.utcoffset() is None:
            raise ValueError("INVALID_TIME")
        return d.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("INVALID_TIME") from None


def _nid(value):
    return type(value) is int and 0 < value <= 2**63 - 1


def _read_regular(path, *, limit):
    path = Path(path)
    if path.is_symlink() or any(x.is_symlink() for x in path.parents):
        raise ValueError("UNSAFE_PRIVATE_SOURCE_PATH")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_NONBLOCK", 0))
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.getuid()
                or before.st_mode & 0o077 or not 0 < before.st_size <= limit):
            raise ValueError("UNSAFE_PRIVATE_SOURCE_FILE")
        raw = b""
        while len(raw) <= limit:
            part = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not part:
                break
            raw += part
        after = os.fstat(fd)
        if (len(raw) != before.st_size
                or (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns,
                    before.st_size) !=
                   (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns,
                    after.st_size)):
            raise ValueError("PRIVATE_FILE_CHANGED_WHILE_READING")
        return raw
    finally:
        os.close(fd)


def _raw_subject(raw_tar, expect_raw):
    with tarfile.open(fileobj=io.BytesIO(raw_tar), mode="r:") as tar:
        files = tar.getmembers()
        if [f.name for f in files] != ["manifest.json", "openligadb.json"]:
            raise ValueError("UNEXPECTED_ORIGINAL_SOURCE_MEMBERS")
        meta_raw = tar.extractfile(files[0]).read(8193)
        body = tar.extractfile(files[1]).read(8_000_001)
    if len(body) != files[1].size or len(meta_raw) != files[0].size:
        raise ValueError("TRUNCATED_ORIGINAL_RAW")
    metadata = _read_json(meta_raw)
    if (original_bundle(metadata, body) != raw_tar
            or hashlib.sha256(body).hexdigest() != expect_raw):
        raise ValueError("ORIGINAL_SOURCE_BYTES_CHANGED")
    return metadata, body


def _source_and_shadow(raw_dir, private_sha, shadow_raw):
    _private_directory(raw_dir)
    if not _sha(private_sha):
        raise ValueError("INVALID_ORIGINAL_SOURCE_BUNDLE_SHA")
    if type(shadow_raw) is not bytes or not 0 < len(shadow_raw) <= MAX_SHADOW:
        raise ValueError("INVALID_SHADOW_BYTES")
    shadow = _read_json(shadow_raw)
    if (type(shadow) is not dict or
            shadow.get("schema") != "football-king-uncalibrated-shadow-1"
            or shadow.get("status") != "SHADOW_ONLY"
            or shadow.get("production_recommendations") != "DISABLED"
            or shadow.get("model_calibrated") is not False
            or shadow.get("market_odds_available") is not False
            or shadow.get("independently_verified_results") is not False
            or type(shadow.get("predictions")) is not list
            or type(shadow.get("sources")) is not list
            or type(shadow.get("predictions_count")) is not int
            or shadow["predictions_count"] != len(shadow["predictions"])
            or len(shadow["predictions"]) > 1000
            or len(shadow["sources"]) > 50):
        raise ValueError("INVALID_OR_UNSAFE_A_SHADOW")
    clock = shadow.get("generation_clock")
    if (type(clock) is not dict or
            clock.get("mode") != "ACTUAL_BATCH_COMPUTATION_COMPLETION_UTC"
            or clock.get("reason") is not None
            or clock.get("sampled_clock_order_and_hk_day_valid") is not True
            or clock.get("source_capture_or_actual_kickoff_authenticated") is not False):
        raise ValueError("REPLAY_OR_UNTRUSTED_ORIGINAL_A_CLOCK")
    started = _time(clock["started_utc"])
    completed = _time(clock["completed_utc"])
    if not started <= completed or _time(shadow["as_of_utc"]) != completed:
        raise ValueError("ORIGINAL_A_CLOCK_MISMATCH")
    sources = [s for s in shadow["sources"] if type(s) is dict
               and s.get("league") == "bundesliga"]
    if len(sources) != 1:
        raise ValueError("MISSING_OR_AMBIGUOUS_BUNDESLIGA_SOURCE")
    src = sources[0]
    if (src.get("source") != "OpenLigaDB"
            or src.get("status") != "READY_RESEARCH"
            or src.get("season") != shadow.get("season")
            or not _sha(src.get("source_response_sha256"))
            or not _sha(src.get("private_same_get_raw_sha256_unattested"))
            or not _sha(src.get("private_same_get_bundle_sha256_unattested"))
            or src.get("private_source_capture_independently_attested") is not False
            or src["private_same_get_raw_sha256_unattested"] !=
               src["source_response_sha256"]
            or src["private_same_get_bundle_sha256_unattested"] != private_sha):
        raise ValueError("A_SHADOW_SOURCE_NOT_SAME_GET_OR_NOT_PRIVATE")
    digest = src["source_response_sha256"]
    source_time = _time(src["captured_utc"])
    if not started <= source_time <= completed:
        raise ValueError("SOURCE_RECEIVED_OUTSIDE_A_RUN")
    private_file = Path(raw_dir) / (private_sha + ".openliga-private.tar")
    checked = check_private_bundle(private_file,
                                    expected_bundle_sha256=private_sha,
                                    expected_raw_sha256=digest)
    if checked.get("exact_same_get_bytes_locally_replayed") is not True:
        raise ValueError("ORIGINAL_SOURCE_REPLAY_FAILED")
    original_raw = _read_regular(private_file, limit=8_100_000)
    metadata, body = _raw_subject(original_raw, digest)
    if (metadata.get("gateway_capture_utc_unattested") is None or
            _time(metadata["gateway_capture_utc_unattested"]) != source_time
            or _time(metadata["local_sealed_utc_unattested"]) > completed
            or metadata.get("season") != shadow.get("season")
            or metadata.get("league") != "bundesliga"):
        raise ValueError("ORIGINAL_SOURCE_CLAIM_DOES_NOT_MATCH_A")
    original_rows = _read_json(body)
    if type(original_rows) is not list or len(original_rows) > 1300:
        raise ValueError("INVALID_ORIGINAL_SOURCE_ROWS")
    by_id = {}
    for row in original_rows:
        if type(row) is dict and _nid(row.get("matchID")):
            by_id.setdefault(row["matchID"], []).append(row)
    binding = []
    seen = set()
    for pred in shadow["predictions"]:
        if type(pred) is not dict:
            raise ValueError("MALFORMED_A_PREDICTION")
        if pred.get("league") != "bundesliga":
            continue
        native = pred.get("native_fixture_input")
        if (type(native) is not dict or set(native) != NATIVE_FIELDS
                or native.get("schema") != NATIVE_SCHEMA
                or native.get("status") != "UNAUTHENTICATED"
                or native.get("provider") != "OpenLigaDB"
                or native.get("league_shortcut") != "bl1"
                or any(not _nid(native.get(k)) for k in (
                    "match_id", "home_team_id", "away_team_id",
                    "league_id", "league_season"))
                or native["home_team_id"] == native["away_team_id"]
                or native.get("native_ids_from_same_response_as_gateway_fixture") is not True
                or any(native.get(k) is not False for k in (
                    "source_identity_authenticated", "source_capture_authenticated",
                    "raw_input_durably_archived", "native_ids_used_as_model_features",
                    "eligible_for_model_scoring"))
                or native.get("source_response_sha256") != digest
                or pred.get("model") != A_MODEL
                or pred.get("production_recommendations") != "DISABLED"
                or pred.get("calibrated") is not False
                or pred.get("verified_market_odds") is not False
                or _time(pred["prediction_utc"]) != completed):
            raise ValueError("INVALID_BUNDESLIGA_NATIVE_A_PREDICTION")
        prob = [pred.get(k) for k in ("p_home", "p_draw", "p_away")]
        if (any(type(p) not in (int, float) or not math.isfinite(p)
                or not 0 <= p <= 1 for p in prob)
                or abs(sum(prob) - 1) > 1e-6
                or not _sha(pred.get("training_observations_sha256"))):
            raise ValueError("INVALID_OR_UNPINNED_A_PROBABILITIES")
        if (pred.get("event_id") != "openligadb:" + str(native["match_id"])
                or native["match_id"] in seen):
            raise ValueError("DUPLICATE_OR_MISMATCHED_NATIVE_A_EVENT")
        seen.add(native["match_id"])
        rows = by_id.get(native["match_id"], [])
        if len(rows) != 1:
            raise ValueError("MISSING_OR_DUPLICATE_ORIGINAL_FIXTURE")
        row = rows[0]
        home, away = row.get("team1"), row.get("team2")
        if (row.get("leagueId") != native["league_id"]
                or row.get("leagueShortcut") != "bl1"
                or row.get("leagueSeason") != native["league_season"]
                or type(home) is not dict or type(away) is not dict
                or home.get("teamId") != native["home_team_id"]
                or away.get("teamId") != native["away_team_id"]
                or not isinstance(home.get("teamName"), str)
                or not isinstance(away.get("teamName"), str)
                or pred.get("home") != home["teamName"].strip()
                or pred.get("away") != away["teamName"].strip()
                or _time(row["matchDateTimeUTC"]) != _time(pred["kickoff_utc"])
                or _time(pred["kickoff_utc"]) <= completed + timedelta(minutes=10)):
            raise ValueError("ORIGINAL_RAW_A_ID_OR_KICKOFF_CONTRADICTION")
        binding.append({
            "event_id": pred["event_id"],
            "league_id": str(native["league_id"]),
            "home_team_id": str(native["home_team_id"]),
            "away_team_id": str(native["away_team_id"]),
            "kickoff_utc": _time(pred["kickoff_utc"]).isoformat(),
            "as_of_utc_unattested": completed.isoformat(),
            "source_raw_sha256_unattested": digest,
            "a_training_observations_sha256_unattested":
                pred["training_observations_sha256"],
            "a_probabilities": prob,
        })
    if not binding:
        raise ValueError("NO_SAME_GET_A_PREDICTIONS")
    binding.sort(key=lambda x: x["event_id"])
    link = {
        "schema": SCHEMA, "status": "HOLD",
        "production_recommendations": "DISABLED",
        "source_bundle_sha256_unattested": private_sha,
        "original_a_shadow_sha256_unattested": hashlib.sha256(shadow_raw).hexdigest(),
        "source_raw_sha256_unattested": digest,
        "source_capture_utc_claimed": source_time.isoformat(),
        "a_batch_completed_utc_claimed": completed.isoformat(),
        "matched_native_fixture_count": len(binding),
        "fixtures": binding,
        "source_publisher_authenticated": False,
        "source_timestamp_attested": False, "forecast_timestamp_attested": False,
        "eligible_for_model_scoring": False,
        "certified_prospective_samples": 0,
        "positive_ev_verified": False,
    }
    return link


def _bundle(shadow, link):
    sources = {"shadow.json": shadow, "link.json": _json(link)}
    if len(sources["link.json"]) > MAX_LINK:
        raise ValueError("OVERSIZED_PRIVATE_LINK")
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name in NAMES:
            raw = sources[name]
            info = tarfile.TarInfo(name)
            info.mode, info.mtime, info.uid, info.gid = 0o600, 0, 0, 0
            info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))
    data = out.getvalue()
    if len(data) > MAX_PAIR:
        raise ValueError("OVERSIZED_PRIVATE_PAIR")
    return data


def create(shadow_file, *, original_dir, pair_dir, source_bundle_sha256):
    """Publish complete A-to-original GET link with atomic no-replace."""
    raw_dir = _private_directory(original_dir)
    outdir = _private_directory(pair_dir)
    if raw_dir == outdir:
        raise ValueError("SOURCE_AND_LINK_DIRECTORIES_MUST_BE_SEPARATE")
    shadow_bytes = _read_regular(shadow_file, limit=MAX_SHADOW)
    link = _source_and_shadow(raw_dir, source_bundle_sha256, shadow_bytes)
    bundle = _bundle(shadow_bytes, link)
    sha = hashlib.sha256(bundle).hexdigest()
    target = outdir / (sha + ".a-source-link-private.tar")
    stage = None
    try:
        fd, stage = tempfile.mkstemp(prefix=".a-source-link-stage-", dir=outdir)
        with os.fdopen(fd, "wb") as dest:
            dest.write(bundle)
            dest.flush()
            os.fsync(dest.fileno())
        _private_directory(outdir)
        os.link(stage, target, follow_symlinks=False)
    finally:
        if stage is not None:
            os.unlink(stage)
    return _hold("LOCAL_SAME_GET_A_LINK_UNATTESTED",
                 matched_native_fixture_count=len(link["fixtures"]),
                 local_private_link_created=True,
                 private_link_sha256_unattested=sha,
                 original_source_bundle_sha256_unattested=source_bundle_sha256,
                 locally_replayable_byte_identity=True)


def replay(pair_file, *, original_dir, source_bundle_sha256, expected_pair_sha256):
    """Re-read complete private linkage and re-check original source at time of use."""
    _private_directory(original_dir)
    if not _sha(expected_pair_sha256) or not _sha(source_bundle_sha256):
        raise ValueError("INVALID_PRIVATE_LINK_REFERENCE")
    value = Path(pair_file)
    _private_directory(value.parent)
    if value.name != expected_pair_sha256 + ".a-source-link-private.tar":
        raise ValueError("INVALID_PRIVATE_LINK_FILENAME")
    raw = _read_regular(value, limit=MAX_PAIR)
    if hashlib.sha256(raw).hexdigest() != expected_pair_sha256:
        raise ValueError("PRIVATE_LINK_HASH_MISMATCH")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as tar:
        members = tar.getmembers()
        if ([m.name for m in members] != list(NAMES)
                or any(m.type != tarfile.REGTYPE or m.mode != 0o600
                       or m.mtime != 0 or m.uid != 0 or m.gid != 0
                       or m.pax_headers or m.linkname for m in members)):
            raise ValueError("INVALID_PRIVATE_LINK_TAR")
        shadow = tar.extractfile(members[0]).read(MAX_SHADOW + 1)
        link_raw = tar.extractfile(members[1]).read(MAX_LINK + 1)
        if len(shadow) != members[0].size or len(link_raw) != members[1].size:
            raise ValueError("INVALID_PRIVATE_LINK_TAR_LENGTH")
    claimed = _read_json(link_raw)
    verified = _source_and_shadow(original_dir, source_bundle_sha256, shadow)
    if (claimed != verified or
            claimed.get("source_bundle_sha256_unattested") != source_bundle_sha256
            or _bundle(shadow, claimed) != raw):
        raise ValueError("PRIVATE_LINK_ORIGINAL_SOURCE_REPLAY_MISMATCH")
    return _hold("LOCAL_SAME_GET_A_LINK_REPLAYED_UNATTESTED",
                 matched_native_fixture_count=len(verified["fixtures"]),
                 locally_replayable_byte_identity=True,
                 original_source_bundle_sha256_unattested=source_bundle_sha256)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shadow", required=True)
    parser.add_argument("--original-dir", required=True)
    parser.add_argument("--pair-dir", required=True)
    parser.add_argument("--source-bundle-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = create(args.shadow, original_dir=args.original_dir,
                        pair_dir=args.pair_dir,
                        source_bundle_sha256=args.source_bundle_sha256)
    except (ValueError, OSError, TypeError, KeyError, OverflowError,
            UnicodeError, tarfile.TarError) as exc:
        result = _hold(str(exc)[:110])
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("local_private_link_created") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
