"""Offline evidence cut binding. Digests and matching strings are not authentication."""
import hashlib
import hmac
import json
from datetime import datetime
from live_snapshot_commitment import commitment, audit_bound_predict
from live_snapshot_adapter import hold
from live_quote_snapshot_guard import audit_live_snapshot
from vnext_integrated_replay import replay_distributions

def _epoch(value):
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("NAIVE_CLOCK")
    return t.timestamp()

def cut_digest(envelope, snapshot):
    raw = json.dumps([commitment(envelope), snapshot], sort_keys=True,
                     separators=(",", ":"), ensure_ascii=True,
                     allow_nan=False).encode("ascii")
    if len(raw) > 65536:
        raise ValueError("CUT_TOO_LARGE")
    return hashlib.sha256(b"football-king/evidence-cut/v1\\x00" + raw).hexdigest()

def audit_cut(envelope, snapshot, expected_digest, now):
    try:
        if type(now) is not int or type(expected_digest) is not str or not expected_digest.isascii():
            return hold("INVALID_CUT")
        if not hmac.compare_digest(cut_digest(envelope, snapshot), expected_digest):
            return hold("CUT_COMMITMENT_MISMATCH")
        model = audit_bound_predict(envelope, commitment(envelope), now)
        if model.get("status") != "RESEARCH_ONLY":
            return hold("MODEL_CUT_REJECTED")
        quote_result = audit_live_snapshot(snapshot)
        if quote_result.get("status") != "RESEARCH_ONLY":
            return hold("QUOTE_CUT_REJECTED")
        a, b = envelope["a"], envelope["b"]
        score, quote = snapshot["score"], snapshot["quote"]
        if (snapshot["event_id"] != a["fixture_id"]
            or _epoch(snapshot["decision_utc"]) != now
            or _epoch(snapshot["kickoff_utc"]) != _epoch(envelope["model"]["kickoff_utc"])
            or [score["home_goals"], score["away_goals"]] != [a["home"], a["away"]]
            or any(type(score.get(k)) is not int or score[k] != a[k]
                   for k in ("minute", "red_home", "red_away"))
            or score.get("phase") != a["phase"]):
            return hold("CROSS_CUT_STATE_MISMATCH")
        # A score record must match one of the two claimed observation records.
        # This cannot establish that the source really published the data.
        if not any(score["source"] == s["origin"]
                   and _epoch(score["upstream_updated_utc"]) == s["observed"]
                   and _epoch(score["captured_utc"]) == s["received"]
                   for s in (a,b)):
            return hold("SCORE_RECORD_NOT_BOUND")
        material = _epoch(score["last_material_event_utc"])
        # Both claimed observations must occur at or after the material event.
        # Matching state alone cannot establish this when the score record
        # is bound to the later of the two observation clocks.
        if material > min(a["observed"], b["observed"]):
            return hold("EVENT_TIME_CONFLICT")
        if any(any(s[k] != p[k] for k in ("home","away","red_home","red_away"))
               and material <= p["observed"]
               for s,p in ((a,envelope["previous_a"]),(b,envelope["previous_b"]))):
            return hold("EVENT_TIME_CONFLICT")
        if quote.get("scope") != "FULL_MATCH_REGULATION":
            return hold("UNSUPPORTED_QUOTE_SCOPE")
        diagnostics = replay_distributions(model, ({
            "market": quote["market"], "side": quote["selection"].upper(), "line": quote["line"],
        },))
        return {**hold("UNAUTHENTICATED_EVIDENCE_CUT"),
                "cut_status":"STRUCTURAL_RESEARCH_ONLY",
                "cut_sha256_unattested":expected_digest,
                "research_diagnostics": diagnostics,
                "actual_xg":None, "model_edge":None,
                "xg_used_by_model":False, "actual_quote_verified":False,
                "external_commitment_authenticated":False}
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, OSError, RecursionError):
        return hold("INVALID_CUT")
