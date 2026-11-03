"""KPL V18 offline admission: source bytes, license claims and sealed forecasts.

An internally consistent packet is NOT externally authenticated data. Neither
the rights document metadata nor a caller-provided public key establishes
actual licensing or independent pregame timestamping. Always HOLD/DISABLED.
"""
from __future__ import annotations

import hashlib
import json
from urllib.parse import urlsplit

from research.kpl_v11_forecast_archive import _time
from research.kpl_v13_archive_snapshot import read_verified_archive_snapshot
from research.kpl_v14_signed_anchor import audit_signed_anchor_batch
from research.kpl_v17_elo_replay import _validate_rows, replay_elo_shadow

SOURCE_FIELDS = frozenset({
    "series_id", "game_number", "team_a", "team_b", "winner_team_id",
    "game_start_at", "result_observed_at"})
PACKET_FIELDS = frozenset({
    "series_id", "game_number", "source_id", "source_url", "published_at",
    "captured_at", "raw_record_json"})
GRANT_FIELDS = frozenset({
    "provider_id", "source_hostname", "license_reference", "grant_document_sha256",
    "granted_use", "grant_expires_at", "grant_observed_at"})
HEX = frozenset("0123456789abcdef")


def _digest(v):
    return isinstance(v, str) and len(v) == 64 and all(c in HEX for c in v)


def _id(v):
    return isinstance(v, str) and 0 < len(v) <= 256 and v.strip() == v


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate raw source JSON key")
        result[key] = value
    return result


def _hold(reasons, *, grade=None, series_count=0, map_count=0,
          source_ok=False, archive_ok=False, signature_ok=False,
          replay_ok=False, documentary_ok=False, synthetic_metrics=None):
    return {
        "status": "HOLD", "reasons": list(dict.fromkeys(reasons)),
        "source_class": grade, "series_count": series_count, "map_count": map_count,
        "source_packet_integrity_passed": source_ok,
        "forecast_archive_linkage_passed": archive_ok,
        "pinned_signed_receipt_coverage_passed": signature_ok,
        "archived_elo_probabilities_match_prequential_replay": replay_ok,
        "rights_documentary_claim_fields_complete": documentary_ok,
        "technical_preflight_passed": bool(
            source_ok and archive_ok and signature_ok and replay_ok and documentary_ok),
        "synthetic_diagnostic_metrics_only": synthetic_metrics,
        "source_identity_independently_authenticated": False,
        "source_publication_time_independently_authenticated": False,
        "licence_independently_verified": False,
        "witness_key_independently_authenticated": False,
        "independent_pregame_existence_verified": False,
        "real_kpl_accuracy_verified": False, "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
        "live_execution_allowed": False, "research_only": True,
        "eligible_for_real_kpl_performance_claims": False,
    }


def _documentary_claim_valid(claim, first_forecast):
    if not isinstance(claim, dict) or set(claim) != GRANT_FIELDS:
        return False
    try:
        host = claim["source_hostname"]
        scopes = claim["granted_use"]
        parsed = urlsplit("https://" + host)
        return bool(
            _id(claim["provider_id"]) and _id(claim["license_reference"])
            and _digest(claim["grant_document_sha256"])
            and isinstance(host, str) and parsed.hostname == host
            and parsed.port is None and "." in host and host == host.lower()
            and isinstance(scopes, list) and 1 <= len(scopes) <= 12
            and all(_id(s) for s in scopes)
            and len(set(scopes)) == len(scopes)
            and "RESEARCH_BACKTEST" in scopes
            and _time(claim["grant_observed_at"]) <= first_forecast
            and _time(claim["grant_expires_at"]) >= first_forecast)
    except (TypeError, ValueError, AttributeError):
        return False


def _packet_integrity(rows, packets, host):
    if not isinstance(packets, list) or len(packets) != len(rows):
        return "MISSING_OR_EXTRA_RAW_SOURCE_PACKETS"
    lookup = {(r["series_id"], r["game_number"]): r for r in rows}
    seen = set()
    for packet in packets:
        if not isinstance(packet, dict) or set(packet) != PACKET_FIELDS:
            return "INVALID_PACKET_SCHEMA"
        slot = (packet["series_id"], packet["game_number"])
        if slot not in lookup or slot in seen:
            return "DUPLICATE_OR_UNKNOWN_SOURCE_GAME"
        seen.add(slot)
        row = lookup[slot]
        raw = packet["raw_record_json"]
        if not isinstance(raw, str):
            return "RAW_SOURCE_MISSING_OR_OVERSIZED"
        raw_bytes = raw.encode("utf-8")
        if not 0 < len(raw_bytes) <= 131072:
            return "RAW_SOURCE_MISSING_OR_OVERSIZED"
        if hashlib.sha256(raw_bytes).hexdigest() != row["source_record_sha256"]:
            return "SOURCE_BYTES_HASH_MISMATCH"
        try:
            decoded = json.loads(raw, object_pairs_hook=_unique_object,
                                 parse_constant=lambda _: (_ for _ in ()).throw(
                                     ValueError("nonfinite JSON")))
        except (ValueError, TypeError):
            return "INVALID_OR_AMBIGUOUS_SOURCE_JSON"
        if (not isinstance(decoded, dict) or set(decoded) != SOURCE_FIELDS
                or decoded != {key: row[key] for key in SOURCE_FIELDS}):
            return "SOURCE_MATCH_GAME_RESULT_MISMATCH"
        try:
            url = urlsplit(packet["source_url"])
            if (url.scheme != "https" or url.hostname != host
                    or url.username or url.password or url.port is not None
                    or url.fragment or not _id(packet["source_id"])
                    or packet["source_id"] != row["source_id"]):
                return "SOURCE_ID_OR_HOST_MISMATCH"
            published = _time(packet["published_at"])
            captured = _time(packet["captured_at"])
            recorded = _time(row["result_observed_at"])
            if not _time(row["game_start_at"]) < published <= recorded <= captured:
                return "SOURCE_POST_EVENT_TIME_MISMATCH"
        except (TypeError, ValueError, AttributeError):
            return "INVALID_SOURCE_PUBLICATION_CLOCK"
    return None


def audit_history_intake(rows, packets, forecast_archive_path, signed_envelopes,
                         trusted_keys, rights_claim, *, model_frozen_at,
                         expected_model_version, registered_series_ids, universe_registered_at,
                         train_fraction=0.5, min_test_series=1,
                         min_test_maps=4):
    """Check exact offline evidence, never promote source/legal claims to truth."""
    try:
        series, grade = _validate_rows(rows)
    except (TypeError, KeyError, ValueError, AttributeError, OverflowError):
        return _hold(["INVALID_OR_INCOMPLETE_BO7_INPUT"])
    reasons = []
    if not _id(expected_model_version):
        reasons.append("MISSING_FROZEN_MODEL_VERSION")
    count = len(rows)
    first = min(s[0] for s in series)
    try:
        if (not isinstance(registered_series_ids, list)
                or registered_series_ids != [s[1] for s in series]
                or _time(universe_registered_at) > first):
            reasons.append("UNREGISTERED_OR_CHANGED_SERIES_UNIVERSE")
    except (ValueError, TypeError):
        reasons.append("UNREGISTERED_OR_CHANGED_SERIES_UNIVERSE")
    doc_ok = _documentary_claim_valid(rights_claim, first)
    if not doc_ok:
        reasons.append("NO_COMPLETE_PRE_FORECAST_RIGHTS_DOCUMENTARY_CLAIM")
    host = rights_claim.get("source_hostname") if isinstance(rights_claim, dict) else None
    packet_problem = _packet_integrity(rows, packets, host)
    packet_ok = packet_problem is None
    if packet_problem:
        reasons.append(packet_problem)

    archive_ok = signature_ok = replay_ok = False
    diagnostics = None
    archive = {}
    try:
        snapshot = read_verified_archive_snapshot(forecast_archive_path)
        archive = {(r["series_id"],r["game_number"]):r for r in snapshot["records"]}
        original = {(r["series_id"],r["game_number"]):r for r in rows}
        archive_ok = (
            len(archive) == count and set(archive) == set(original)
            and all(
                archive[slot]["team_ids"] == [row["team_a"],row["team_b"]]
                and archive[slot]["predicted_team_id"] == row["team_a"]
                and archive[slot]["forecast_at"] == row["forecast_at"]
                and archive[slot]["game_start_at"] == row["game_start_at"]
                and archive[slot]["phase"] == "PRE_GAME"
                and archive[slot]["model_version"] == expected_model_version
                and archive[slot]["status"] == "RESEARCH_ONLY"
                for slot,row in original.items()))
    except (OSError, TypeError, ValueError, KeyError, AttributeError):
        pass
    if not archive_ok:
        reasons.append("MISSING_OR_MISMATCHED_PRE_GAME_FORECAST_ARCHIVE")
    else:
        try:
            signatures = audit_signed_anchor_batch(
                forecast_archive_path, signed_envelopes, trusted_keys)
            signature_ok = signatures["signed_receipt_coverage_passed"]
        except (TypeError, ValueError, KeyError, OSError, AttributeError):
            pass
        if not signature_ok:
            reasons.append("INCOMPLETE_OR_INVALID_PINNED_SIGNED_RECEIPTS")
    try:
        report = replay_elo_shadow(
            rows, model_frozen_at=model_frozen_at,
            registered_series_ids=registered_series_ids,
            universe_registered_at=universe_registered_at,
            train_fraction=train_fraction,
            min_test_series=min_test_series, min_test_maps=min_test_maps)
        if "test_forecasts" in report and archive_ok:
            actual = report["test_forecasts"]
            replay_ok = bool(actual) and all(
                abs(archive[(r["series_id"],r["game_number"])]["probability"]
                    - r["probability_a"]) <= 1e-12 for r in actual)
            if not replay_ok:
                reasons.append("SEALED_FORECAST_DISAGREES_WITH_ELO_REPLAY")
        if grade == "SYNTHETIC" and "elo_model" in report:
            diagnostics = {
                "model_brier": report["elo_model"]["brier"],
                "baseline_brier": report["uniform_50_baseline"]["brier"],
                "test_maps": report["test_maps"],
                "test_series": report["test_series"]}
    except (TypeError, ValueError, KeyError, OverflowError, AttributeError):
        reasons.append("TIME_SPLIT_OR_FROZEN_ELO_REPLAY_INVALID")
    if not replay_ok:
        reasons.append("UNPROVEN_PROSPECTIVE_MODEL_OUTPUT")
    if not reasons:
        reasons.append("ALL_EVIDENCE_SELF_ASSERTED_EXTERNAL_AUTHORITY_NOT_PROVEN")
    return _hold(reasons, grade=grade, series_count=len(series), map_count=count,
                 source_ok=packet_ok, archive_ok=archive_ok,
                 signature_ok=signature_ok, replay_ok=replay_ok,
                 documentary_ok=doc_ok, synthetic_metrics=diagnostics)
