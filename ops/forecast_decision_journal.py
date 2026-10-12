"""Append-only *logical* forecast revision chain (research only).

A SHA256 chain can detect accidental edits against a separately pinned copy,
but cannot authenticate historical truth by itself: an attacker can rewrite
and rehash the entire chain. Git commits/external audit anchors are required
for trustworthy time provenance. Do not claim win rate or tradable edge here.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math

SCHEMA = "football-king-forecast-revisions-v1"
MIN_PREMATCH_BUFFER_MINUTES = 10
STATUS = {"RESEARCH", "WAIT_PRICE", "ABSTAIN", "WITHDRAW"}
MARKETS = {"h2h", "spreads", "totals", "team_corners", "match_corners"}
DIRECTIONS = {"HOME", "DRAW", "AWAY", "HOME_SPREAD", "AWAY_SPREAD", "OVER", "UNDER"}
ROOT = "GENESIS"


def _utc(x):
    if not isinstance(x, str):
        raise ValueError("INVALID_TIMESTAMP")
    try:
        d = datetime.fromisoformat(x.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if d.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return d.astimezone(timezone.utc)


def _hash(row):
    encoded = json.dumps(row, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _valid(payload):
    if not isinstance(payload, dict):
        raise ValueError("INVALID_REVISION")
    required = {"fixture_id", "created_utc", "kickoff_utc", "status",
                "market", "direction", "reason", "revision"}
    optional = {"line", "observed_odds", "quote_source", "quote_captured_utc",
                "research_probability"}
    if set(payload) != required | (set(payload) & optional):
        raise ValueError("UNKNOWN_OR_MISSING_REVISION_FIELD")
    for key in ("fixture_id", "reason"):
        value = payload[key]
        if not isinstance(value, str) or not (1 <= len(value.strip()) <= 1000):
            raise ValueError("INVALID_ID_OR_REASON")
    if (type(payload["revision"]) is not int or payload["revision"] < 1
            or payload["status"] not in STATUS
            or payload["market"] not in MARKETS):
        raise ValueError("INVALID_REVISION_ID_STATUS_MARKET")
    direction = payload["direction"]
    if payload["status"] in ("ABSTAIN", "WITHDRAW"):
        if direction is not None:
            raise ValueError("ABSTENTION_MUST_NOT_HAVE_DIRECTION")
    elif direction not in DIRECTIONS:
        raise ValueError("INVALID_DIRECTION")
    if payload["market"] == "h2h":
        if payload.get("line") is not None:
            raise ValueError("H2H_MUST_NOT_HAVE_LINE")
        if direction is not None and direction not in {"HOME", "DRAW", "AWAY"}:
            raise ValueError("INVALID_H2H_DIRECTION")
    else:
        line = payload.get("line")
        if type(line) not in (float, int) or not math.isfinite(line) or abs(line) > 30:
            raise ValueError("INVALID_MARKET_LINE")
        allowed = {"HOME_SPREAD", "AWAY_SPREAD"} if payload["market"] == "spreads" else {"OVER", "UNDER"}
        if direction is not None and direction not in allowed:
            raise ValueError("DIRECTION_MARKET_MISMATCH")
    if "research_probability" in payload:
        p = payload["research_probability"]
        if type(p) not in (float, int) or not math.isfinite(p) or not 0 <= p <= 1:
            raise ValueError("INVALID_RESEARCH_PROBABILITY")
    created = _utc(payload["created_utc"])
    kickoff = _utc(payload["kickoff_utc"])
    if not created <= kickoff - timedelta(minutes=MIN_PREMATCH_BUFFER_MINUTES):
        raise ValueError("NOT_A_FROZEN_PREMATCH_FORECAST")
    price_fields = {"observed_odds", "quote_source", "quote_captured_utc"}
    if price_fields & set(payload):
        if not price_fields <= set(payload):
            raise ValueError("INCOMPLETE_QUOTE_PROVENANCE")
        price = payload["observed_odds"]
        src = payload["quote_source"]
        if (type(price) not in (float, int) or not math.isfinite(price)
                or not 1.01 <= price <= 100
                or not isinstance(src, str) or not src.strip() or len(src) > 400):
            raise ValueError("INVALID_QUOTE")
        if _utc(payload["quote_captured_utc"]) > created:
            raise ValueError("QUOTE_AFTER_FORECAST")
    return created, kickoff


def verify(entries):
    """Verify chain consistency and each fixture's complete ordered versions."""
    if not isinstance(entries, list) or len(entries) > 50000:
        raise ValueError("INVALID_JOURNAL")
    previous = ROOT
    fixtures = {}
    global_time = None
    for row in entries:
        if not isinstance(row, dict) or set(row) < {"payload", "prev_sha256", "sha256"}:
            raise ValueError("INVALID_JOURNAL_ENTRY")
        if set(row) != {"payload", "prev_sha256", "sha256", "schema"}:
            raise ValueError("INVALID_JOURNAL_ENTRY")
        if row["schema"] != SCHEMA or row["prev_sha256"] != previous:
            raise ValueError("BROKEN_JOURNAL_CHAIN")
        payload = row["payload"]
        created, kickoff = _valid(payload)
        expect = _hash({k: row[k] for k in ("schema", "payload", "prev_sha256")})
        if row["sha256"] != expect:
            raise ValueError("JOURNAL_ENTRY_TAMPERED")
        if global_time is not None and created < global_time:
            raise ValueError("OUT_OF_ORDER_JOURNAL_APPEND")
        global_time = created
        fid = payload["fixture_id"]
        before = fixtures.get(fid)
        if before is None:
            if payload["revision"] != 1:
                raise ValueError("MISSING_FIRST_REVISION")
        elif (payload["revision"] != before["revision"] + 1
              or kickoff != before["kickoff"]
              or created <= before["created"]):
            raise ValueError("NONMONOTONIC_OR_CHANGED_FIXTURE")
        fixtures[fid] = {"revision": payload["revision"], "created": created,
                         "kickoff": kickoff, "payload": payload}
        previous = row["sha256"]
    return fixtures


def append_version(entries, payload):
    """Return a newly chained entry; storage/commit is caller's responsibility."""
    state = verify(entries)
    created, kickoff = _valid(payload)
    before = state.get(payload["fixture_id"])
    required_revision = (before["revision"] + 1) if before else 1
    if payload["revision"] != required_revision:
        raise ValueError("REVISION_MUST_APPEND_NOT_REWRITE")
    if before and (kickoff != before["kickoff"] or created <= before["created"]):
        raise ValueError("MUST_BE_NEWER_SAME_FIXTURE")
    if entries and created < _utc(entries[-1]["payload"]["created_utc"]):
        raise ValueError("CAN_NOT_BACKFILL_JOURNAL")
    row = {"schema": SCHEMA, "payload": payload,
           "prev_sha256": entries[-1]["sha256"] if entries else ROOT}
    row["sha256"] = _hash(row)
    return row


def audit(entries):
    """Count decisions and reversals without cherry-picking settled winners."""
    fixtures = verify(entries)
    grouped = {}
    for record in entries:
        p = record["payload"]
        grouped.setdefault(p["fixture_id"], []).append(p)
    summary = []
    changed = 0
    for fid in sorted(grouped):
        versions = grouped[fid]
        initial = versions[0]
        final = versions[-1]
        active_directions = [
            (p["market"], p.get("line"), p["direction"])
            for p in versions if p["status"] in ("RESEARCH", "WAIT_PRICE")]
        reversals = sum(a != b for a, b in zip(active_directions, active_directions[1:]))
        changed += reversals
        summary.append({
            "fixture_id": fid, "revisions": len(versions),
            "initial_status": initial["status"],
            "initial_direction": initial["direction"],
            "last_pre_kickoff_status": final["status"],
            "last_pre_kickoff_direction": final["direction"],
            "direction_reversals": reversals,
            "had_withdrawal": any(p["status"] == "WITHDRAW" for p in versions),
            "had_abstention": any(p["status"] == "ABSTAIN" for p in versions),
            "last_revision_sha256": next(r["sha256"] for r in reversed(entries)
                                        if r["payload"]["fixture_id"] == fid),
            "quote_is_executable_verified": False,
            "settlement_result_authenticated": False,
            "count_as_formal_bet": False,
        })
    return {
        "schema": SCHEMA, "status": "RESEARCH_ONLY" if entries else "HOLD",
        "version_count": len(entries), "unique_fixtures": len(fixtures),
        "direction_reversals": changed, "fixture_history": summary,
        "journal_hash_is_not_independent_timestamp_authentication": True,
        "historical_win_rate_certified": False,
        "settlement_verified": False, "production_recommendations": "DISABLED",
    }
