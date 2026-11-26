"""Offline intake rehearsal: quota -> transport -> declared scoreboard corroboration.

The provider payload and secondary observation are synthetic. Native ID mapping,
observation clocks and publisher independence are NOT authenticated. No model,
network connection, real credential, real market or production authorization.
"""
import json
from vnext_quota_coordinator_contract import reserve_simulated
from vnext_direct_transport_offline import rehearse, unique_object, reject_constant


def result(stage, reason, reserved=False, matched=False):
    return {"stage": stage, "reason": reason, "simulated_reservation": reserved,
            "synthetic_scoreboard_agreement": matched, "source_authenticated": False,
            "actual_xg_verified": False, "actual_live_odds_verified": False,
            "positive_ev_verified": False, "real_requests": 0,
            "real_request_authorized": False, "status": "HOLD",
            "production_recommendations": "DISABLED"}


def scoreboard(row):
    fixture, goals = row["fixture"], row["goals"]
    phase, minute = fixture["status"]["short"], fixture["status"]["elapsed"]
    home, away = goals["home"], goals["away"]
    if type(phase) is not str or phase not in ("1H", "HT", "2H"):
        raise ValueError("PHASE")
    if type(minute) is not int or not (0 <= minute <= 120):
        raise ValueError("MINUTE")
    if not all(type(n) is int and 0 <= n <= 30 for n in (home, away)):
        raise ValueError("SCORE")
    return phase, minute, home, away


def fresh(observed, now):
    return type(observed) is int and 0 <= now-observed <= 60 and observed > 0


def run(store, *, quota, transport, mapping, primary_observed, secondary):
    """Consume one simulated reservation even if downstream validation fails."""
    required = {"epoch","revision_floor","request_id","consumer","now","observed",
                "daily_remaining","minute_remaining"}
    if type(quota) is not dict or set(quota) != required:
        return result("QUOTA", "BAD_INPUT")
    q = reserve_simulated(store, **quota)
    if q["simulated_reservation"] is not True:
        return result("QUOTA", q["reason"])
    try:
        if type(transport) is not dict or set(transport) != {"env","response_url","status","content_type","body"}:
            return result("TRANSPORT", "BAD_INPUT", True)
        t = rehearse(**transport)
        if t["reason"] != "SYNTHETIC_RESPONSE_ONLY":
            return result("TRANSPORT", t["reason"], True)
        # Reparse the exact same immutable byte payload, not a separate claimed score.
        data = json.loads(transport["body"].decode("utf-8"),
                          object_pairs_hook=unique_object, parse_constant=reject_constant)
        if type(mapping) is not dict or set(mapping) != {"primary_id","secondary_id"}:
            return result("EVIDENCE", "BAD_MAPPING", True)
        pid, sid = mapping["primary_id"], mapping["secondary_id"]
        if not all(type(n) is int and n > 0 for n in (pid,sid)):
            return result("EVIDENCE", "BAD_MAPPING", True)
        if type(secondary) is not dict or set(secondary) != {"fixture_id","publisher",
                "observed","phase","minute","home","away"}:
            return result("EVIDENCE", "BAD_SECONDARY", True)
        if type(secondary["fixture_id"]) is not int or secondary["fixture_id"] != sid:
            return result("EVIDENCE", "IDENTITY_MISMATCH", True)
        if secondary["publisher"] != "synthetic_secondary":
            return result("EVIDENCE", "SOURCE_LABEL_REJECTED", True)
        if not (fresh(primary_observed, quota["now"]) and
                fresh(secondary["observed"], quota["now"]) and
                abs(primary_observed-secondary["observed"]) <= 30):
            return result("EVIDENCE", "CLOCK_REJECTED", True)
        rows = [r for r in data["response"] if r["fixture"]["id"] == pid]
        if len(rows) != 1:
            return result("EVIDENCE", "PRIMARY_ID_MISSING", True)
        claimed = scoreboard(rows[0])
        second = scoreboard({"fixture":{"status":{"short":secondary["phase"],
                              "elapsed":secondary["minute"]}},
                             "goals":{"home":secondary["home"],"away":secondary["away"]}})
        if claimed != second:
            return result("EVIDENCE", "STATE_MISMATCH", True)
        return result("COMPLETE", "SYNTHETIC_AGREEMENT_ONLY", True, True)
    except (ValueError, TypeError, KeyError, AttributeError, OSError, OverflowError, RecursionError):
        return result("EVIDENCE", "MALFORMED_INPUT", True)
