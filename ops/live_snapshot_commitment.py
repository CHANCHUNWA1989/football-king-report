"""Research-only integrity envelope. A hash is not source or clock authentication."""
import hashlib
import hmac
import json
from datetime import datetime
from live_snapshot_adapter import check, hold, valid, research_predict

FIELDS = {"a", "b", "model", "decision_epoch", "previous_a", "previous_b"}
MONOTONIC = ("observed", "received", "minute", "home", "away", "red_home", "red_away")


def commitment(envelope):
    if type(envelope) is not dict or set(envelope) != FIELDS:
        raise ValueError("INVALID_ENVELOPE")
    payload = json.dumps(envelope, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    if len(payload) > 65536:
        raise ValueError("ENVELOPE_TOO_LARGE")
    return hashlib.sha256(b"football-king/live-envelope/v1\x00" + payload).hexdigest()


def audit_bound_predict(envelope, expected_sha256, now):
    """Expected digest must come from a separately retained commitment.
    Neither its provenance nor the caller's clock is verified here.
    """
    try:
        actual = commitment(envelope)
        if (type(expected_sha256) is not str or len(expected_sha256) != 64
                or not expected_sha256.isascii()
                or not hmac.compare_digest(actual, expected_sha256)):
            return hold("COMMITMENT_MISMATCH")
        if type(now) is not int or type(envelope["decision_epoch"]) is not int or now != envelope["decision_epoch"]:
            return hold("DECISION_MISMATCH")
        a,b,model = (envelope[k] for k in ("a","b","model"))
        reason = check(a,b,model,now)
        if reason != "CONSISTENT":
            return hold(reason)
        kickoff = datetime.fromisoformat(model["kickoff_utc"].replace("Z","+00:00"))
        if kickoff.tzinfo is None or kickoff.utcoffset() is None:
            return hold("INVALID_KICKOFF")
        ko = kickoff.timestamp()
        if any(s["observed"] < ko for s in (a,b)):
            return hold("PRE_KICKOFF_OBSERVATION")
        pa,pb = envelope["previous_a"],envelope["previous_b"]
        if not valid(pa) or not valid(pb):
            return hold("MISSING_OR_INVALID_HISTORY")
        if any(pa[k] != pb[k] for k in ("fixture_id","minute","home","away","red_home","red_away","phase")):
            return hold("HISTORY_CONFLICT")
        if abs(pa["observed"]-pb["observed"]) > 30:
            return hold("HISTORY_UNSYNCED")
        for current,prior in ((a,pa),(b,pb)):
            if (current["origin"] != prior["origin"] or current["fixture_id"] != prior["fixture_id"]
                    or prior["observed"] < ko
                    or prior["observed"] >= current["observed"]
                    or prior["received"] >= current["received"]
                    or any(current[k] < prior[k] for k in MONOTONIC)):
                return hold("HISTORY_REPLAY_OR_CORRECTION_REVIEW")
        out = research_predict(a,b,model,now)
        if out["status"] == "RESEARCH_ONLY":
            out.update(envelope_sha256_unattested=actual,
                       history_consistency_only=True,
                       external_commitment_authenticated=False)
        return out
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, OSError, RecursionError):
        return hold("INVALID_BOUND_INPUT")
