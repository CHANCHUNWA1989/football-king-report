"""KPL V22: offline RFC3161 proof-of-existence for V20 shadow records.

Accepted inputs: *exact* locally saved manifest/decision bytes, the original
RFC3161 request (with unique nonce), and a response token signed by a pinned
TSA certificate. This never contacts a TSA, acquires external trust roots, or
authenticates match data. External authorization and revocation are NOT
implicitly granted by caller-supplied certificates/CRL.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path

from research import kpl_v20_shadow_trial as _shadow
from research.kpl_v11_forecast_archive import _time
from research.kpl_v15_rfc3161_offline import (
    MAX_TOKEN, _pin_trust, _run, _verify_token,
)

KIND_MANIFEST = "MANIFEST"
KIND_DECISION = "DECISION"
MAX_LOCAL_RECORD = 150_000
MAX_REQUEST = 8192
MAX_RECEIPTS = 1401
RECEIPT_KEYS = frozenset({
    "object_kind", "series_id", "game_number", "request_b64", "token_b64"})
HEX_NONCE = re.compile(r"(?m)^Nonce:\s*(0x[0-9a-fA-F]+)\s*$")


def _hold(reasons, *, entries=None, total=0, good=0, verified_crl=0):
    return {
        "status": "HOLD",
        "reasons": list(dict.fromkeys(reasons)),
        "expected_record_count": total,
        "cryptographically_consistent_record_count": good,
        "locally_checked_revocation_record_count": verified_crl,
        "all_manifest_and_recorded_decisions_timestamp_bound": bool(
            total and good == total),
        "record_evidence": entries or [],
        "independent_tsa_identity_verified": False,
        "trusted_root_independently_authenticated": False,
        "external_time_source_independently_verified": False,
        "revocation_status_completely_authenticated": False,
        "registered_kpl_fixture_independently_verified": False,
        "official_game_results_independently_verified": False,
        "license_or_usage_rights_verified": False,
        "real_kpl_accuracy_verified": False,
        "positive_ev_verified": False,
        "research_only": True,
        "live_execution_allowed": False,
        "production_recommendations": "DISABLED",
    }


def _unique_pairs(pairs):
    found = {}
    for key, value in pairs:
        if key in found:
            raise ValueError("duplicate key")
        found[key] = value
    return found


def _read_local(path, size):
    """One descriptor, one bounded read: reject symlinks and special files."""
    path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        meta = os.fstat(descriptor)
        if not stat.S_ISREG(meta.st_mode) or not 0 < meta.st_size <= size:
            raise ValueError("not a bounded regular file")
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            raw = stream.read(size + 1)
        if not raw.endswith(b"\n") or not 0 < len(raw) <= size:
            raise ValueError("malformed local artifact")
        obj = json.loads(
            raw, object_pairs_hook=_unique_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("nonfinite JSON")))
        if not isinstance(obj, dict):
            raise ValueError("invalid local artifact")
        return obj, raw
    finally:
        os.close(descriptor)


def _load_manifest_bytes(trial_dir):
    obj, raw = _read_local(Path(trial_dir) / "manifest.json", MAX_LOCAL_RECORD)
    _shadow._check_manifest(obj)
    return obj, raw, hashlib.sha256(raw).hexdigest()


def _read_decision_bytes(path, manifest, manifest_hash):
    packet, raw = _read_local(path, 6000)
    if (set(packet) != {"manifest_sha256", "recorded_at", "decision"}
            or packet["manifest_sha256"] != manifest_hash):
        raise ValueError("manifest hash mismatch")
    record = packet["decision"]
    if not isinstance(record, dict):
        raise ValueError("invalid decision")
    series = next((s for s in manifest["series"] if
                   s["series_id"] == record.get("series_id")), None)
    if series is None:
        raise ValueError("unknown series")
    seen_at = _time(packet["recorded_at"])
    if seen_at < _time(manifest["registration_at"]):
        raise ValueError("decision predates registration")
    _shadow._validate_decision(record, series, now=seen_at)
    key = (record["series_id"], record["game_number"])
    if Path(path).name != f"{key[0]}-g{key[1]}.json":
        raise ValueError("renamed or misleading decision file")
    return record, packet, raw, series


def _all_records(trial_dir):
    manifest, manifest_raw, sha = _load_manifest_bytes(trial_dir)
    earliest = min(_time(s["first_game_start_at"]) for s in manifest["series"])
    reg = _time(manifest["registration_at"])
    registry = {
        (KIND_MANIFEST, None, None): (manifest_raw, reg, earliest),
    }
    directory = Path(trial_dir) / "decisions"
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("missing or unsafe decisions directory")
    series_prefixes = {}
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            raise ValueError("unexpected or unsafe shadow record")
        record, packet, raw, series = _read_decision_bytes(path, manifest, sha)
        key = (KIND_DECISION, record["series_id"], record["game_number"])
        if key in registry:
            raise ValueError("duplicate shadow slot")
        deadline = _time(record["game_start_at"])
        if record["game_number"] == 1:
            deadline = min(deadline, _time(series["first_game_start_at"]))
        registry[key] = (
            raw, _time(packet["recorded_at"]), deadline,
        )
        series_prefixes.setdefault(key[1], []).append((key[2], deadline))
    # A later G3/G4 record with missing G2 cannot be promoted as "fully
    # witnessed" simply because its G2 file and receipt were both deleted.
    # Earlier V20 requires previous-map decisions at write time; repeat this
    # structural verification when reading potentially tampered files.
    for series_id, recorded in series_prefixes.items():
        ordered = sorted(recorded)
        numbers = [game for game, _ in ordered]
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError("missing prior BO7 map decision in local history")
        if any(later <= earlier for (_, earlier), (_, later)
               in zip(ordered, ordered[1:])):
            raise ValueError("nonchronological BO7 decision deadlines")
    return registry


def _decode_b64(value, limit):
    if not isinstance(value, str) or len(value) > (limit * 4 // 3 + 8):
        raise ValueError("invalid encoded data")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("malformed base64") from exc
    if not raw or len(raw) > limit:
        raise ValueError("invalid data size")
    return raw


def _make_request(raw):
    """Return RFC3161 request with OpenSSL-generated random nonce, no IO."""
    with tempfile.TemporaryDirectory(prefix="kpl22-request-") as folder:
        target = Path(folder) / "record.bin"
        request = Path(folder) / "request.tsq"
        target.write_bytes(raw)
        res = _run([
            "openssl", "ts", "-query", "-data", str(target), "-sha256",
            "-cert", "-out", str(request),
        ])
        if res.returncode:
            raise RuntimeError("TSA_REQUEST_GENERATION_FAILED")
        tsq = request.read_bytes()
        if not 0 < len(tsq) <= MAX_REQUEST:
            raise ValueError("invalid RFC3161 request size")
        return tsq


def prepare_shadow_timestamp_request(trial_dir, *, object_kind,
                                     series_id=None, game_number=None):
    """Prepare byte-bound random-nonce .tsq; caller must send to external TSA.

    No request is sent and no external timestamp claim is made.
    """
    try:
        registry = _all_records(trial_dir)
        key = (object_kind, series_id, game_number)
        if key not in registry:
            return _hold(["UNKNOWN_OR_UNREGISTERED_SHADOW_RECORD"])
        raw, earliest, deadline = registry[key]
        if _shadow._utcnow() >= deadline:
            return _hold(["RECORD_ALREADY_SCHEDULED_TO_START"])
        request = _make_request(raw)
        return {
            **_hold(["SEND_REQUEST_TO_INDEPENDENT_TSA_OUT_OF_BAND"]),
            "record_sha256": hashlib.sha256(raw).hexdigest(),
            "request_b64": base64.b64encode(request).decode("ascii"),
            "request_sha256": hashlib.sha256(request).hexdigest(),
            "object_kind": object_kind,
            "series_id": series_id,
            "game_number": game_number,
            "sent_to_tsa": False,
        }
    except (OSError, TypeError, ValueError, KeyError, RuntimeError):
        return _hold(["INVALID_LOCAL_SHADOW_RECORD_OR_OPENSSL"])


def _verify_req_token(req, token, raw, trust, crl, lower, deadline):
    """Require query nonce in TST, exact imprint, signer/path and time bounds."""
    checked, token_ok, chain_ok, revocation_ok, parsed = _verify_token(
        token, raw, trust, crl_pem=crl)
    if not parsed or isinstance(checked, str):
        return ("BAD_RFC3161_TOKEN_OR_SIGNER", False, False)
    stamped_at = checked
    if not lower <= stamped_at < deadline:
        return ("TOKEN_GENERATED_OUTSIDE_PRE_GAME_WINDOW", False, revocation_ok)
    with tempfile.TemporaryDirectory(prefix="kpl22-nonce-") as folder:
        directory = Path(folder)
        qfile, tokenfile = directory / "request.tsq", directory / "token.der"
        rootfile, signerfile = directory / "root.pem", directory / "tsa.pem"
        qfile.write_bytes(req)
        tokenfile.write_bytes(token)
        rootfile.write_text(trust["root_ca_pem"], encoding="ascii")
        signerfile.write_text(trust["tsa_cert_pem"], encoding="ascii")
        view = _run(["openssl", "ts", "-query", "-in", str(qfile), "-text"])
        if view.returncode:
            return ("INVALID_OR_UNREADABLE_TSA_REQUEST", False, revocation_ok)
        content = view.stdout.decode("utf-8", errors="replace")
        nonces = HEX_NONCE.findall(content)
        if (len(nonces) != 1 or
                not re.search(r"(?mi)^Hash Algorithm:\s*sha256\s*$", content)
                or not re.search(r"(?mi)^Certificate required:\s*yes\s*$",
                                 content)):
            return ("TSA_REQUEST_NONCE_OR_DIGEST_MISSING", False, revocation_ok)
        # OpenSSL verifies query imprint and nonce against token's signed
        # TSTInfo, in addition to existing _verify_token(data=raw) check.
        matched = _run([
            "openssl", "ts", "-verify",
            "-in", str(tokenfile), "-token_in",
            "-queryfile", str(qfile),
            "-CAfile", str(rootfile), "-untrusted", str(signerfile),
            "-purpose", "timestampsign", "-attime",
            str(int(stamped_at.timestamp())),
        ])
        if matched.returncode:
            return ("TSA_NONCE_OR_REQUEST_IMPRINT_MISMATCH", False, revocation_ok)
    return (None, True, revocation_ok)


def audit_shadow_timestamp_bundle(trial_dir, receipts, tsa_trust, *,
                                  revocation_crl_pem=None):
    """Cross-check a TSA request+token for EVERY recorded shadow artifact.

    This audit does NOT verify whether the caller's certificate pin is truly
    controlled by an independent TSA or whether rights/fixtures are real.
    """
    try:
        registry = _all_records(trial_dir)
    except (OSError, ValueError, TypeError, KeyError):
        return _hold(["INVALID_LOCAL_SHADOW_RECORDS"])
    total = len(registry)
    if total == 1:
        return _hold(["NO_PREMAP_DECISIONS_REGISTERED"], total=total)
    pin_error = _pin_trust(tsa_trust)
    if pin_error:
        return _hold([pin_error], total=total)
    if (not isinstance(receipts, list) or len(receipts) != total
            or len(receipts) > MAX_RECEIPTS):
        return _hold(["INCOMPLETE_TIMESTAMP_RECEIPT_COVERAGE"], total=total)
    by_slot = {}
    for item in receipts:
        if not isinstance(item, dict) or set(item) != RECEIPT_KEYS:
            return _hold(["INVALID_TIMESTAMP_RECEIPT_SCHEMA"], total=total)
        kind, sid, game = (item["object_kind"], item["series_id"],
                           item["game_number"])
        if (kind not in (KIND_MANIFEST, KIND_DECISION)
                or (sid is not None and not _shadow._id(sid))
                or (game is not None and type(game) is not int)):
            return _hold(["INVALID_TIMESTAMP_RECEIPT_IDENTITY"], total=total)
        key = (kind, sid, game)
        if key not in registry or key in by_slot:
            return _hold(["UNKNOWN_DUPLICATE_OR_CROSS_GAME_RECEIPT"], total=total)
        by_slot[key] = item
    if set(by_slot) != set(registry):
        return _hold(["INCOMPLETE_TIMESTAMP_RECEIPT_COVERAGE"], total=total)
    results = []
    good = checked_crl = 0
    reasons = []
    for key, (raw, low, deadline) in registry.items():
        item = by_slot[key]
        try:
            req = _decode_b64(item["request_b64"], MAX_REQUEST)
            token = _decode_b64(item["token_b64"], MAX_TOKEN)
            problem, verified, revoked_checked = _verify_req_token(
                req, token, raw, tsa_trust, revocation_crl_pem, low, deadline)
        except (ValueError, TypeError, RuntimeError, OSError, OverflowError):
            problem, verified, revoked_checked = (
                "INVALID_OR_UNVERIFIABLE_TIMESTAMP_RECEIPT", False, False)
        if problem:
            reasons.append(problem)
        if verified:
            good += 1
        if revoked_checked:
            checked_crl += 1
        results.append({
            "object_kind": key[0], "series_id": key[1], "game_number": key[2],
            "record_sha256": hashlib.sha256(raw).hexdigest(),
            "imprint_nonce_signer_and_deadline_consistent": verified,
            "revocation_locally_checked": revoked_checked,
        })
    if checked_crl != total:
        reasons.append("REVOCATION_EVIDENCE_MISSING_OR_UNVERIFIED")
    reasons.extend([
        "PINNED_TSA_AUTHORITY_NOT_INDEPENDENTLY_AUTHENTICATED",
        "LOCAL_TRIAL_AND_KPL_SOURCE_NOT_EXTERNALLY_AUTHENTICATED",
        "NO_REAL_KPL_CALIBRATION_OR_POSITIVE_EV_PROOF",
    ])
    return _hold(reasons, entries=results, total=total, good=good,
                 verified_crl=checked_crl)
