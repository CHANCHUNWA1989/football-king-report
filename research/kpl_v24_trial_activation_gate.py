"""V24 prospective KPL trial activation preflight, offline and fail-closed.

No remote fetch, no official feed, no V20 registration, no external TSA
submission, no bets. Real source authority cannot be self-asserted.
A tournament session is NOT the exact first-game start; historic lineups
and BPs may NEVER be recycled for an unrelated November 4 BO7.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research.kpl_v11_forecast_archive import _time
from research.kpl_v20_shadow_trial import _id
from research.kpl_v22_shadow_witness import audit_shadow_timestamp_bundle
from research.kpl_v23_fixture_gate import (
    _source_host, load_fixture_dossier, screen_fixture_dossier,
)

STAGE_KEYS = frozenset({
    "schema", "fixture_key", "team_ids", "scheduled_session_at", "reviewed_at",
    "official_series_id", "verified_first_map_start_at",
    "match_specific_lineups", "match_specific_game_one_bp",
    "model_holdout_evidence", "rights_evidence",
    "independent_tsa_evidence", "v20_trial_registration",
    "previous_match_lineup_context",
})
HISTORY_KEYS = frozenset({
    "team_id", "opponent_id", "match_date", "published_at",
    "source_url", "starting_five", "usable_for_current_match",
})
LINEUP_KEYS = frozenset({
    "fixture_key", "official_series_id", "match_date",
    "team_id", "opponent_id", "published_at", "source_url", "players",
    "source_kind",
})
PLAYER_KEYS = frozenset({"role", "player_id"})
ROLES = frozenset({"CLASH", "JUNGLE", "MID", "FARM", "ROAM"})
BP_KEYS = frozenset({
    "fixture_key", "official_series_id", "game_number", "team_ids",
    "bp_locked_at", "captured_at", "source_url", "source_kind",
    "bans_by_team", "picks_by_team",
})
MODEL_KEYS = frozenset({
    "model_version", "model_frozen_at", "evaluation_phase",
    "independent_bo_series", "out_of_sample_maps", "brier_gain",
    "clustered_gain_lower_bound", "source_id",
})
RIGHTS_KEYS = frozenset({
    "provider_id", "grant_document_sha256", "research_use_allowed",
    "grant_observed_at", "grant_expires_at",
})
MAX_READINESS_BYTES = 64_000
SHANGHAI = timezone(timedelta(hours=8))


def _hold(reasons, *, key=None, session=None, checks=None, witness=None):
    flags = checks or {}
    return {
        "status": "HOLD", "decision": "HOLD", "probability_a": None,
        "fixture_key": key, "scheduled_session_at": session,
        "fixture_source_claims_consistent": flags.get("schedule", False),
        "previous_lineups_excluded_from_current_match": flags.get("history", False),
        "match_lineup_structure_valid": flags.get("lineups", False),
        "first_map_bp_structure_valid": flags.get("bp", False),
        "model_holdout_fields_valid": flags.get("model", False),
        "rights_documentary_fields_valid": flags.get("rights", False),
        "tsa_crypto_locally_consistent": bool(witness and witness.get(
            "all_manifest_and_recorded_decisions_timestamp_bound") is True),
        "locally_witnessed_record_count": (witness or {}).get(
            "cryptographically_consistent_record_count", 0),
        "structural_inputs_complete": all(flags.get(k) is True for k in
            ("schedule", "history", "lineups", "bp", "model", "rights")),
        "official_series_id_independently_authenticated": False,
        "actual_g1_kickoff_independently_authenticated": False,
        "lineups_independently_authenticated": False,
        "g1_bp_independently_authenticated": False,
        "real_kpl_model_calibration_verified": False,
        "actual_usage_rights_independently_verified": False,
        "independent_tsa_authority_verified": False,
        "independent_timestamp_delivery_verified": False,
        "actual_pregame_prediction_exists": False,
        "activation_allowed": False,
        "registration_created_by_gate": False,
        "trial_started_by_gate": False,
        "real_kpl_forecast_count_created": 0,
        "real_kpl_accuracy_verified": False, "positive_ev_verified": False,
        "live_execution_allowed": False,
        "production_recommendations": "DISABLED",
        "research_only": True,
        "reasons": list(dict.fromkeys(reasons)),
    }


def _url(value):
    try:
        _source_host(value)
        return True
    except (TypeError, ValueError, AttributeError):
        return False


def _history_ok(context, fixture, session):
    if not isinstance(context, list) or not 1 <= len(context) <= 24:
        return False
    for item in context:
        if not isinstance(item, dict) or set(item) != HISTORY_KEYS:
            return False
        if (item["team_id"] not in fixture["teams"] or
                not _id(item["opponent_id"]) or
                item["opponent_id"] == item["team_id"] or
                item["usable_for_current_match"] is not False or
                not _url(item["source_url"])):
            return False
        try:
            match_day = datetime.fromisoformat(item["match_date"]).date()
            published = _time(item["published_at"])
        except (TypeError, ValueError, OverflowError):
            return False
        players = item["starting_five"]
        if (match_day >= session.astimezone(SHANGHAI).date()
                or published >= session or
                not isinstance(players, list) or len(players) != 5 or
                any(not _id(p) for p in players) or len(set(players)) != 5):
            return False
    return True


def _lineups_ok(lineups, fixture, series_id, session, now):
    if not _id(series_id) or not isinstance(lineups, list) or len(lineups) != 2:
        return False
    today = session.astimezone(SHANGHAI).date().isoformat()
    teams_seen = set()
    for item in lineups:
        if not isinstance(item, dict) or set(item) != LINEUP_KEYS:
            return False
        team, opponent = item["team_id"], item["opponent_id"]
        if (team not in fixture["teams"] or team in teams_seen
                or opponent not in fixture["teams"] or opponent == team
                or item["fixture_key"] != fixture["fixture_key"]
                or item["official_series_id"] != series_id
                or item["match_date"] != today
                or item["source_kind"] != "MATCH_SPECIFIC_OFFICIAL_LINEUP_CLAIM"
                or not _url(item["source_url"])):
            return False
        try:
            published = _time(item["published_at"])
        except (ValueError, TypeError, OverflowError):
            return False
        if not session-timedelta(days=1) <= published <= now < session:
            return False
        players = item["players"]
        if not isinstance(players, list) or len(players) != 5:
            return False
        if any(not isinstance(p, dict) or set(p) != PLAYER_KEYS or
               p["role"] not in ROLES or not _id(p["player_id"])
               for p in players):
            return False
        if ({p["role"] for p in players} != ROLES
                or len({p["player_id"] for p in players}) != 5):
            return False
        teams_seen.add(team)
    return teams_seen == set(fixture["teams"])


def _bp_ok(bp, fixture, series_id, start, now, lineups):
    if (not isinstance(bp, dict) or set(bp) != BP_KEYS
            or start is None or not _id(series_id)):
        return False
    if (bp["fixture_key"] != fixture["fixture_key"]
            or bp["official_series_id"] != series_id
            or type(bp["game_number"]) is not int or bp["game_number"] != 1
            or bp["team_ids"] != fixture["teams"]
            or bp["source_kind"] != "FIRST_MAP_LOCKED_BP_CLAIM"
            or not _url(bp["source_url"])):
        return False
    try:
        locked = _time(bp["bp_locked_at"])
        captured = _time(bp["captured_at"])
        latest_lineup = max(_time(x["published_at"]) for x in lineups)
    except (ValueError, TypeError, OverflowError):
        return False
    if not latest_lineup <= locked <= captured <= now < start:
        return False
    for key in ("bans_by_team", "picks_by_team"):
        selection = bp[key]
        if not isinstance(selection, dict) or set(selection) != set(fixture["teams"]):
            return False
        for heroes in selection.values():
            if (not isinstance(heroes, list) or len(heroes) != 5
                    or any(not _id(h) for h in heroes)
                    or len(set(heroes)) != 5):
                return False
    picks = [hero for team in fixture["teams"] for hero in bp["picks_by_team"][team]]
    return len(set(picks)) == 10


def _model_ok(model, session):
    if not isinstance(model, dict) or set(model) != MODEL_KEYS:
        return False
    if (not _id(model["model_version"]) or not _id(model["source_id"])
            or model["evaluation_phase"] != "BP_LOCKED"
            or type(model["independent_bo_series"]) is not int
            or model["independent_bo_series"] < 40
            or type(model["out_of_sample_maps"]) is not int
            or model["out_of_sample_maps"] < 120):
        return False
    gain = model["brier_gain"]
    lower = model["clustered_gain_lower_bound"]
    if (type(gain) not in (int,float) or type(lower) not in (int,float)
            or not math.isfinite(gain) or not math.isfinite(lower)
            or gain <= 0 or lower <= 0):
        return False
    try:
        return _time(model["model_frozen_at"]) < session
    except (ValueError, TypeError, OverflowError):
        return False


def _rights_ok(rights, session, now):
    if not isinstance(rights, dict) or set(rights) != RIGHTS_KEYS:
        return False
    digest = rights["grant_document_sha256"]
    if (not _id(rights["provider_id"]) or
            not isinstance(digest, str) or len(digest) != 64
            or any(x not in "0123456789abcdef" for x in digest)
            or rights["research_use_allowed"] is not True):
        return False
    try:
        return (_time(rights["grant_observed_at"]) <= now < session <=
                _time(rights["grant_expires_at"]))
    except (ValueError, TypeError, OverflowError):
        return False


def audit_trial_activation(fixture, readiness, *, now=None,
                           existing_trial_dir=None, timestamp_receipts=None,
                           tsa_trust=None, revocation_crl_pem=None):
    """Read-only admission audit: NEVER calls V20 register_shadow_trial.

    A self-signed TSA, caller-entered source URLs and a locally fabricated
    certificate pin cannot establish independent authority. A possible
    structural pass is diagnostic only. Activation is forbidden without
    a separate authenticated/authorized external authority workflow.
    """
    if not isinstance(readiness, dict) or set(readiness) != STAGE_KEYS:
        return _hold(["INVALID_OR_INCOMPLETE_READINESS_SCHEMA"])
    key = readiness.get("fixture_key")
    session_value = readiness.get("scheduled_session_at")
    try:
        current = _time(now) if now is not None else datetime.now(timezone.utc)
        session = _time(session_value)
        reviewed = _time(readiness["reviewed_at"])
    except (ValueError, TypeError, OverflowError):
        return _hold(["INVALID_READINESS_CLOCK"], key=key, session=session_value)
    if (readiness["schema"] != "KPL_V24_ACTIVATION_READINESS_V1"
            or not isinstance(fixture, dict)
            or key != fixture.get("fixture_key")
            or readiness["team_ids"] != fixture.get("teams")
            or session_value != fixture.get("scheduled_session_at")):
        return _hold(["FIXTURE_IDENTITY_OR_STAGE_SCHEMA_MISMATCH"],
                     key=key, session=session_value)
    if reviewed > current or reviewed >= session or current >= session:
        return _hold(["REVIEW_CLOCK_AFTER_SESSION_OR_IN_FUTURE"],
                     key=key, session=session_value)
    prior = screen_fixture_dossier(fixture, now=current.isoformat())
    flags = {"schedule": prior["technical_schedule_claims_consistent"] is True}
    reasons = []
    if not flags["schedule"]:
        reasons += ["FIXTURE_SOURCE_DOSSIER_NOT_READY"] + prior["reasons"]
    flags["history"] = _history_ok(
        readiness["previous_match_lineup_context"], fixture, session)
    if not flags["history"]:
        reasons.append("PREVIOUS_MATCH_LINEUP_CONTEXT_INVALID_OR_NOT_EXCLUDED")
    series_id = readiness["official_series_id"]
    if not _id(series_id):
        reasons.append("OFFICIAL_MATCH_SPECIFIC_SERIES_ID_MISSING")
    try:
        start = (_time(readiness["verified_first_map_start_at"])
                 if readiness["verified_first_map_start_at"] is not None else None)
    except (TypeError, ValueError, OverflowError):
        start = None
    if (start is None or start <= current or
            not session <= start <= session + timedelta(hours=3)):
        reasons.append("EXACT_FIRST_MAP_KICKOFF_UNVERIFIED")
        start = None
    lineups = readiness["match_specific_lineups"]
    flags["lineups"] = _lineups_ok(lineups, fixture, series_id, session, current)
    if not flags["lineups"]:
        reasons.append("NO_TWO_MATCH_SPECIFIC_OFFICIAL_LINEUP_CLAIMS")
    flags["bp"] = bool(flags["lineups"] and _bp_ok(
        readiness["match_specific_game_one_bp"], fixture, series_id,
        start, current, lineups))
    if not flags["bp"]:
        reasons.append("FIRST_MAP_BP_NOT_LOCKED_FOR_SAME_FIXTURE_AND_TIME")
    flags["model"] = _model_ok(readiness["model_holdout_evidence"], session)
    if not flags["model"]:
        reasons.append("REAL_KPL_SAME_PHASE_HOLDOUT_CALIBRATION_MISSING")
    flags["rights"] = _rights_ok(readiness["rights_evidence"], session, current)
    if not flags["rights"]:
        reasons.append("REAL_DATA_RESEARCH_RIGHTS_NOT_DOCUMENTED")
    if readiness["independent_tsa_evidence"] is not None:
        reasons.append("SELF_ASSERTED_TSA_TRUST_NOT_ACCEPTED")
    if readiness["v20_trial_registration"] is not None:
        reasons.append("SELF_ASSERTED_TRIAL_REGISTRATION_NOT_ACCEPTED")
    witness = None
    if existing_trial_dir is None:
        reasons.append("NO_EXISTING_V20_TRIAL_AND_V22_RAW_TIMESTAMP_EVIDENCE")
    elif timestamp_receipts is None or tsa_trust is None:
        reasons.append("INCOMPLETE_TSA_RAW_EVIDENCE_ARGUMENTS")
    else:
        try:
            witness = audit_shadow_timestamp_bundle(
                existing_trial_dir, timestamp_receipts, tsa_trust,
                revocation_crl_pem=revocation_crl_pem)
        except (OSError, ValueError, TypeError, KeyError):
            reasons.append("INVALID_EXISTING_TRIAL_OR_TIMESTAMP_EVIDENCE")
        if witness is None or not witness.get(
                "all_manifest_and_recorded_decisions_timestamp_bound"):
            reasons.append("V22_TIMESTAMP_CRYPTO_COVERAGE_FAILED")
        if witness and not witness.get(
                "revocation_status_completely_authenticated"):
            reasons.append("TSA_REVOCATION_OR_INDEPENDENT_TRUST_NOT_VERIFIED")
    reasons.extend([
        "EXTERNAL_MATCH_LINEUP_BP_AND_IDENTITY_NOT_AUTHENTICATED",
        "INDEPENDENT_TSA_ROOT_DELIVERY_AND_REVOCATION_NOT_VERIFIED",
        "REAL_KPL_MODEL_DATA_RIGHTS_AND_CALIBRATION_NOT_AUTHENTICATED",
        "READ_ONLY_V24_GATE_CANNOT_REGISTER_OR_ACTIVATE",
    ])
    return _hold(reasons, key=key, session=session_value,
                 checks=flags, witness=witness)


def audit_trial_activation_files(fixture_path, readiness_path, *, now=None):
    try:
        fixture = load_fixture_dossier(fixture_path)
        with Path(readiness_path).open("rb") as stream:
            raw = stream.read(MAX_READINESS_BYTES + 1)
        if not raw or len(raw) > MAX_READINESS_BYTES:
            raise ValueError("invalid/oversized readiness file")
        def unique(pairs):
            result = {}
            for k, v in pairs:
                if k in result:
                    raise ValueError("duplicate JSON key")
                result[k] = v
            return result
        readiness = json.loads(raw, object_pairs_hook=unique,
                               parse_constant=lambda _: (_ for _ in ()).throw(
                                   ValueError("nonfinite JSON number")))
        return audit_trial_activation(fixture, readiness, now=now)
    except (OSError, ValueError, TypeError, UnicodeError):
        return _hold(["INVALID_OR_UNREADABLE_READINESS_FILES"])


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        raise SystemExit(
            "Usage: python -m research.kpl_v24_trial_activation_gate "
            "<fixture.json> <readiness.json>")
    print(json.dumps(audit_trial_activation_files(sys.argv[1], sys.argv[2]),
                     sort_keys=True))
