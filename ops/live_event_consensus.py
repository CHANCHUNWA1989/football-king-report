"""Offline two-source goal, red-card and VAR revision consensus.

Research-only assertions, NOT authentication or verified independence.
No live data fetching, model eligibility, betting, positive-EV or settlement.
"""
import hashlib
import json
from collections import defaultdict

from live_score_identity_guard import check as score_check, parse_utc
from point_in_time_store import build_cut

SCHEMA = "football-king-event-consensus-vnext-v1"
TYPES = {"GOAL", "RED_CARD"}
SIDES = {"HOME", "AWAY"}
STATES = {"CONFIRMED", "UNDER_REVIEW", "OVERTURNED"}
NEXT = {
    "CONFIRMED": {"UNDER_REVIEW"},
    "UNDER_REVIEW": {"CONFIRMED", "OVERTURNED"},
    "OVERTURNED": set(),
}
EVENT_FIELDS = {
    "event_key", "type", "side", "minute", "revision", "state",
    "source_updated_utc", "received_utc",
}


def _id(value):
    return (type(value) is str and 1 <= len(value) <= 128
            and value == value.strip() and value.isprintable()
            and not any(ch.isspace() for ch in value))


def _digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _hold(reason):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED",
        "model_scoring_eligible": False,
        "source_authenticated": False, "source_independence_verified": False,
        "event_truth_verified": False, "settlement_certified": False,
        "positive_ev_verified": False,
    }


def _canonical_events(feed, kickoff, decision):
    records = feed.get("event_revisions")
    if type(records) is not list or len(records) > 256:
        raise ValueError("INVALID_EVENT_HISTORY")
    if feed.get("events_complete_since_kickoff") is not True:
        raise ValueError("INCOMPLETE_EVENT_HISTORY")
    upstream = parse_utc(feed["source_updated_utc"])
    received_max = parse_utc(feed["received_utc"])
    groups = defaultdict(list)
    for row in records:
        if type(row) is not dict or set(row) != EVENT_FIELDS:
            raise ValueError("INVALID_EVENT_RECORD")
        key, kind, side, minute, revision, state = (
            row[k] for k in ("event_key", "type", "side", "minute", "revision", "state"))
        if (not _id(key) or kind not in TYPES or side not in SIDES
                or type(minute) is not int or not 0 <= minute <= 150
                or type(revision) is not int or revision < 1 or state not in STATES):
            raise ValueError("INVALID_EVENT_FIELDS")
        updated, received = (
            parse_utc(row["source_updated_utc"]), parse_utc(row["received_utc"]))
        if not kickoff <= updated <= received <= received_max <= decision:
            raise ValueError("EVENT_TIME_NOT_AVAILABLE")
        if updated > upstream:
            raise ValueError("EVENT_AFTER_FEED_UPDATE")
        groups[key].append((revision, kind, side, minute, state, updated, received))
    events = []
    for key in sorted(groups):
        revisions = sorted(groups[key], key=lambda row: row[0])
        first = revisions[0]
        prev_state = prev_updated = prev_received = None
        for expected_revision, (revision, kind, side, minute, state, updated, received) in enumerate(revisions, 1):
            if revision != expected_revision:
                raise ValueError("EVENT_REVISION_GAP_OR_DUPLICATE")
            if (kind, side, minute) != first[1:4]:
                raise ValueError("EVENT_IDENTITY_CHANGED_BY_REVISION")
            if prev_state is not None:
                if state not in NEXT[prev_state]:
                    raise ValueError("INVALID_VAR_TRANSITION")
                if updated < prev_updated or received < prev_received:
                    raise ValueError("EVENT_REVISION_TIME_ROLLBACK")
            prev_state, prev_updated, prev_received = state, updated, received
        events.append((key, first[1], first[2], first[3],
                       tuple(revision[4] for revision in revisions)))
    if any(row[4][-1] == "UNDER_REVIEW" for row in events):
        raise ValueError("VAR_PENDING_NOT_SETTLED")
    goals, reds = {"HOME": 0, "AWAY": 0}, {"HOME": 0, "AWAY": 0}
    for _, kind, side, _, states in events:
        if states[-1] == "CONFIRMED":
            (goals if kind == "GOAL" else reds)[side] += 1
    if (goals["HOME"] != feed.get("score_home")
            or goals["AWAY"] != feed.get("score_away")):
        raise ValueError("SCORE_EVENT_HISTORY_CONFLICT")
    return events, goals, reds


def reconcile(fixture, feeds, *, decision_utc):
    """Fail closed on a conflicting complete event snapshot, including VAR.

    `source_groups_by_provider` is a predeclared assertion, not independent
    evidence of source provenance. Returned research consensus has no
    independent authentication or external wall-clock attestation.
    """
    try:
        if type(feeds) is not list or len(feeds) != 2:
            raise ValueError("REQUIRE_EXACTLY_TWO_FEEDS")
        if type(fixture) is not dict:
            raise ValueError("INVALID_FIXTURE")
        groups, provider_ids = (
            fixture.get("source_groups_by_provider"), fixture.get("provider_event_ids"))
        if (type(groups) is not dict or type(provider_ids) is not dict
                or set(groups) != set(provider_ids)
                or len(set(groups.values())) != len(groups)
                or any(not _id(group) for group in groups.values())):
            raise ValueError("SOURCE_GROUPS_NOT_DISTINCT_OR_PREDECLARED")
        decision = parse_utc(decision_utc)
        kickoff = parse_utc(fixture["kickoff_utc"])
        scores = score_check(fixture, feeds, decision_utc)
        if scores["status"] != "RESEARCH_ONLY":
            raise ValueError("SCORE_GATE:" + scores["reason"])
        evidence = []
        validated = {}
        for feed in feeds:
            provider = feed["provider"]
            if provider in validated:
                raise ValueError("DUPLICATED_PUBLISHER")
            if feed.get("source_group") != groups[provider]:
                raise ValueError("SOURCE_GROUP_MISMATCH")
            if not (parse_utc(feed["source_updated_utc"])
                    <= parse_utc(feed["captured_utc"])
                    <= parse_utc(feed["received_utc"])
                    <= parse_utc(feed["available_utc"]) <= decision):
                raise ValueError("FEED_TIME_ORDER_CONFLICT")
            events, goals, reds = _canonical_events(feed, kickoff, decision)
            validated[provider] = (events, goals, reds)
            evidence.append({
                "evidence_id": provider + ":events",
                "fixture_id": fixture["fixture_id"], "kind": "event",
                "source": provider, "source_group": groups[provider],
                "source_event_id": feed["source_event_id"],
                "source_updated_utc": feed["source_updated_utc"],
                "captured_utc": feed["captured_utc"],
                "received_utc": feed["received_utc"],
                "available_utc": feed["available_utc"],
                "raw_sha256": _digest(feed),
            })
        pit = build_cut(evidence, fixture_id=fixture["fixture_id"],
                        kickoff_utc=fixture["kickoff_utc"], decision_utc=decision_utc,
                        phase="INPLAY")
        first, second = (validated[key] for key in sorted(validated))
        if first[0] != second[0]:
            raise ValueError("CROSS_SOURCE_EVENT_OR_VAR_CONFLICT")
        if first[1] != second[1] or first[2] != second[2]:
            raise ValueError("CROSS_SOURCE_COUNT_CONFLICT")
        return {
            **_hold("RESEARCH_CONSENSUS_NOT_AUTHENTICATED"),
            "status": "RESEARCH_ONLY", "fixture_id": fixture["fixture_id"],
            "decision_utc": pit["decision_utc"], "event_count": len(first[0]),
            "score_home": first[1]["HOME"], "score_away": first[1]["AWAY"],
            "active_red_cards": dict(first[2]),
            "var_overturned_count": sum(row[4][-1] == "OVERTURNED" for row in first[0]),
            "evidence_input_sha256": pit["input_sha256"],
            "providers": sorted(validated),
        }
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as exc:
        return _hold(str(exc) or "INVALID_INPUT")
