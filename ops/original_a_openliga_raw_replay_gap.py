"""Conservative, OFFLINE original-A/controlled OpenLigaDB byte replay.

This RECONCILES two *separately* archived gzip files. Git object equality,
tar replay and a matching response SHA are not signature verification.
Never infer that two independently captured responses are the same one.
Signature identity and Rekor time require fresh original-main `gh
attestation verify` through the existing separate provenance auditors.
No network, no betting, no forecast creation, no source certification.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re

from ops.openliga_capture_pack import (
    _members, _json as _raw_json, _read_regular, validate_capture,
)
from ops.penaltyblog_a_shadow_native_handoff import (
    A_MODEL, NATIVE_FIELDS, NATIVE_SCHEMA,
)

SCHEMA = "football-king-openliga-to-shadow-byte-reconcile-v1"
MANIFEST_SCHEMA = "football-king-two-original-archive-git-pins-v1"
MAX_COMPRESSED = 100_000
MAX_CAPTURE_DECODED = 4_000_000
MAX_SHADOW_DECODED = 8_000_000


def _hold(reason, **extra):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED",
        "positive_ev_verified": False,
        "independent_capture_attestation_reverified": False,
        "independent_forecast_attestation_reverified": False,
        "publisher_identity_authenticated": False,
        "source_time_independently_attested": False,
        "eligible_for_model_scoring": False,
        "certified_prospective_samples": 0,
        "source_response_pair_certified": False,
        "models_promoted": False, **extra,
    }


def _unique(pairs):
    out = {}
    for key, val in pairs:
        if key in out:
            raise ValueError("DUPLICATE_ARCHIVE_JSON_KEY")
        out[key] = val
    return out


def _bad_constant(_):
    raise ValueError("NONFINITE_ARCHIVE_JSON")


def _strict_json(raw):
    return json.loads(raw, object_pairs_hook=_unique, parse_constant=_bad_constant)


def _sha_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\x00" + raw).hexdigest()


def _decompress(raw, limit):
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        value = stream.read(limit + 1)
    if not 0 < len(value) <= limit:
        raise ValueError("ARCHIVE_DECOMPRESSED_SIZE_INVALID")
    return value


def _utc(value):
    if type(value) is not str or not 0 < len(value) < 100:
        raise ValueError("INVALID_OR_UNTRUSTED_TIME")
    try:
        val = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if val.tzinfo is None or val.utcoffset() is None:
            raise ValueError("INVALID_OR_UNTRUSTED_TIME")
        return val.astimezone(timezone.utc)
    except (TypeError, OverflowError, ValueError):
        raise ValueError("INVALID_OR_UNTRUSTED_TIME") from None


def _native_id(value):
    return type(value) is int and 0 < value <= 2**63 - 1


def _pins(manifest):
    if (type(manifest) is not dict or
            set(manifest) != {"schema", "production_recommendations",
                              "main_commit", "archive_day",
                              "capture", "shadow"} or
            manifest.get("schema") != MANIFEST_SCHEMA or
            manifest.get("production_recommendations") != "DISABLED" or
            not re.fullmatch(r"[0-9a-f]{40}", manifest.get("main_commit", ""))
            or manifest.get("archive_day") != "2026/11/15"):
        raise ValueError("INVALID_PINNED_RESEARCH_MANIFEST")
    for key in ("capture", "shadow"):
        field = manifest[key]
        if (type(field) is not dict or
                set(field) != {"path", "size", "git_blob_sha1"} or
                type(field["path"]) is not str or
                not re.fullmatch(
                    r"(openliga_capture_provenance|forecast_provenance)/2026/11/15/"
                    r"[1-9][0-9]{6,19}-[1-9][0-9]{0,9}/"
                    r"(openliga-capture\.tar\.gz|shadow\.json\.gz)",
                    field["path"]) or
                ("openliga_capture_provenance/" in field["path"]) != (key == "capture")
                or type(field["size"]) is not int or
                not 0 < field["size"] <= MAX_COMPRESSED or
                type(field["git_blob_sha1"]) is not str or
                not re.fullmatch(r"[0-9a-f]{40}", field["git_blob_sha1"])):
            raise ValueError("INVALID_COMPRESSED_GIT_PIN")


def audit(manifest, capture_gz, shadow_gz, *, now=None):
    """Return descriptive HOLD whether or not the two source bytes match."""
    try:
        _pins(manifest)
        for raw, key in ((capture_gz, "capture"), (shadow_gz, "shadow")):
            info = manifest[key]
            if (type(raw) is not bytes or len(raw) != info["size"] or
                    _sha_blob(raw) != info["git_blob_sha1"]):
                raise ValueError("COMPRESSED_ARCHIVE_GIT_PIN_MISMATCH")

        raw_tar = _decompress(capture_gz, MAX_CAPTURE_DECODED)
        capture = validate_capture(raw_tar, now=(
            datetime.now(timezone.utc) if now is None else now))
        if (capture["status"] != "HOLD" or
                capture["production_recommendations"] != "DISABLED" or
                capture["controlled_capture_content_verified"] is not True or
                capture["publisher_identity_authenticated"] is not False or
                capture["independently_verified"] is not False):
            raise ValueError("UNSAFE_CONTROLLED_CAPTURE_REPLAY")
        raw_bytes = _members(raw_tar)["openligadb.json"]
        raw_digest = hashlib.sha256(raw_bytes).hexdigest()
        if raw_digest != capture["raw_sha256"]:
            raise ValueError("RAW_SOURCE_REPLAY_HASH_MISMATCH")
        raw_rows = _raw_json(raw_bytes)
        if type(raw_rows) is not list or len(raw_rows) > 1300:
            raise ValueError("INVALID_RAW_SOURCE_FIXTURES")

        original = _strict_json(_decompress(shadow_gz, MAX_SHADOW_DECODED))
        if (type(original) is not dict or
                original.get("schema") != "football-king-uncalibrated-shadow-1"
                or original.get("production_recommendations") != "DISABLED"
                or original.get("model_calibrated") is not False
                or original.get("market_odds_available") is not False
                or original.get("independently_verified_results") is not False
                or type(original.get("sources")) is not list
                or type(original.get("predictions")) is not list
                or type(original.get("predictions_count")) is not int
                or original["predictions_count"] != len(original["predictions"])):
            raise ValueError("INVALID_OR_UNTRUSTED_A_FORECAST_ARCHIVE")

        original_at = _utc(original["as_of_utc"])
        capture_end = _utc(capture["capture_latest_utc"])
        if capture_end > original_at:
            # A later independent archive cannot prove source availability
            # at the earlier original A prediction time.
            return _hold("SOURCE_CAPTURE_COMPLETED_AFTER_A_FORECAST",
                         original_a_predictions=len(original["predictions"]),
                         byte_pins_checked=True,
                         controlled_capture_content_replayed=True,
                         matching_source_response_hash_count=0)
        matches = 0
        eligible_candidates = 0
        invalid_candidates = 0
        provider_source_count = 0
        raw_id_map = {}
        for row in raw_rows:
            if type(row) is dict and _native_id(row.get("matchID")):
                raw_id_map.setdefault(row["matchID"], []).append(row)

        for source in original["sources"]:
            if type(source) is not dict or source.get("league") != "bundesliga":
                continue
            if (source.get("status") == "READY_RESEARCH"
                    and source.get("source") == "OpenLigaDB"
                    and source.get("source_response_sha256") == raw_digest):
                provider_source_count += 1
        for row in original["predictions"]:
            if (type(row) is not dict or
                    row.get("league") != "bundesliga" or
                    row.get("model") != A_MODEL or
                    row.get("production_recommendations") != "DISABLED"):
                continue
            native = row.get("native_fixture_input")
            if type(native) is not dict or set(native) != NATIVE_FIELDS:
                continue
            if (native.get("schema") != NATIVE_SCHEMA or
                    native.get("status") != "UNAUTHENTICATED" or
                    native.get("provider") != "OpenLigaDB" or
                    native.get("league_shortcut") != "bl1" or
                    not all(_native_id(native.get(k)) for k in
                            ("match_id", "league_id", "home_team_id",
                             "away_team_id", "league_season")) or
                    native.get("source_identity_authenticated") is not False or
                    native.get("source_capture_authenticated") is not False or
                    native.get("raw_input_durably_archived") is not False or
                    native.get("eligible_for_model_scoring") is not False or
                    native.get("native_ids_from_same_response_as_gateway_fixture") is not True):
                invalid_candidates += 1
                continue
            if (row.get("event_id") != "openligadb:" + str(native["match_id"])
                    or _utc(row["prediction_utc"]) != original_at):
                invalid_candidates += 1
                continue
            if native.get("source_response_sha256") != raw_digest:
                continue
            eligible_candidates += 1
            candidates = raw_id_map.get(native["match_id"], [])
            if len(candidates) != 1:
                invalid_candidates += 1
                continue
            found = candidates[0]
            home, away = found.get("team1"), found.get("team2")
            if (found.get("leagueShortcut") != "bl1" or
                    found.get("leagueId") != native["league_id"] or
                    found.get("leagueSeason") != native["league_season"] or
                    type(home) is not dict or type(away) is not dict or
                    home.get("teamId") != native["home_team_id"] or
                    away.get("teamId") != native["away_team_id"] or
                    _utc(found["matchDateTimeUTC"]) != _utc(row["kickoff_utc"])):
                invalid_candidates += 1
                continue
            matches += 1

        if invalid_candidates:
            return _hold("CONTRADICTORY_OR_UNVERIFIED_NATIVE_IDENTITY",
                         byte_pins_checked=True, controlled_capture_content_replayed=True,
                         invalid_native_identity_candidates=invalid_candidates,
                         matching_source_response_hash_count=0)
        if matches and provider_source_count != 1:
            return _hold("ORIGINAL_A_SOURCE_REPORT_DIGEST_CONFLICT",
                         byte_pins_checked=True,
                         controlled_capture_content_replayed=True,
                         matching_source_response_hash_count=0)
        return _hold(
            "SAME_ORIGINAL_SOURCE_BYTES_REPLAYED_BUT_SIGNER_NOT_REVERIFIED"
            if matches else "NO_IDENTICAL_A_SOURCE_RESPONSE_IN_PINNED_CAPTURE",
            byte_pins_checked=True, controlled_capture_content_replayed=True,
            capture_sha256_local=hashlib.sha256(raw_tar).hexdigest(),
            openliga_raw_sha256_local=raw_digest,
            shadow_sha256_local=hashlib.sha256(
                _decompress(shadow_gz, MAX_SHADOW_DECODED)).hexdigest(),
            original_a_predictions=len(original["predictions"]),
            native_identity_candidates_with_same_response_digest=eligible_candidates,
            local_same_response_id_and_kickoff_matches=matches,
            matching_source_response_hash_count=provider_source_count,
            note=("Even a byte-identity match is not an attestation: "
                  "fresh GitHub CLI verification of BOTH original-main "
                  "signature subjects and the witness chronology is "
                  "required; never use the separately saved audit flags."),
        )
    except (ValueError, TypeError, KeyError, OSError, EOFError, OverflowError,
            UnicodeError, AttributeError) as exc:
        code = str(exc)
        return _hold(code if len(code) <= 110 else "INVALID_ARCHIVED_ORIGINAL_BYTES")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args(argv)
    try:
        root = Path(args.repo_root)
        raw_manifest = _read_regular(Path(args.manifest), 20000)
        manifest = _strict_json(raw_manifest)
        _pins(manifest)
        capture = _read_regular(root / manifest["capture"]["path"], MAX_COMPRESSED)
        shadow = _read_regular(root / manifest["shadow"]["path"], MAX_COMPRESSED)
        result = audit(manifest, capture, shadow)
    except (ValueError, OSError, TypeError) as exc:
        result = _hold(str(exc)[:110])
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0 if result.get("byte_pins_checked") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
