"""Offline byte-level *untrusted provider claim* intake for in-play research.

The bytes are caller-supplied normalized claim JSON, NOT proven original
publisher response bytes. Matching two self-declared publishers does not prove
source independence, original web retrieval, official truth, external time,
or authorization to use/redistribute any provider's data. No network or API.
A success is never admitted to a live model, forward cohort, settlement or bet.
"""
import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

SCHEMA="football-king-inplay-two-source-claim-byte-packet-v1"
CLAIM_SCHEMA="football-king-untrusted-inplay-source-claim-v1"
PROVIDERS={
    "fotmob": frozenset(("fotmob.com","www.fotmob.com")),
    "sofascore": frozenset(("sofascore.com","www.sofascore.com")),
    "flashscore": frozenset(("flashscore.com","www.flashscore.com")),
}
MATCH_STATES=("FIRST_HALF","HALF_TIME","SECOND_HALF")
FIXTURE_KEYS={"fixture_id","league_id","home_id","away_id","kickoff_utc",
              "identity_sealed_utc","decision_utc"}
CLAIM_KEYS={"schema","provider","provider_event_id","source_url",
            "fixture_id","league_id","home_id","away_id","kickoff_utc",
            "source_updated_utc","captured_utc","received_utc",
            "match_status","elapsed_regulation_minute",
            "home_goals","away_goals","home_red_cards","away_red_cards",
            "var_review_pending"}
MAX_BYTES=10_000
MAX_AGE=timedelta(seconds=120)
SAFE_ID=re.compile(r"[A-Za-z0-9_.:-]{1,120}\Z")


def _fail(reason):
    raise ValueError(reason)


def _utc(value):
    if type(value) is not str or len(value)>64 or not value:
        _fail("INVALID_CLAIMED_TIME")
    try:
        instant=datetime.fromisoformat(value.replace("Z","+00:00"))
        if instant.tzinfo is None or instant.utcoffset() is None:
            _fail("INVALID_CLAIMED_TIME")
        return instant.astimezone(timezone.utc)
    except (ValueError,TypeError,OverflowError):
        _fail("INVALID_CLAIMED_TIME")


def _id(value):
    return type(value) is str and SAFE_ID.fullmatch(value) is not None


def _object(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            _fail("DUPLICATE_UNTRUSTED_JSON_FIELD")
        result[key]=value
    return result


def _reject_constant(value):
    _fail("NONFINITE_UNTRUSTED_JSON_VALUE")


def _decode(raw):
    if type(raw) is not bytes or not 1<=len(raw)<=MAX_BYTES:
        _fail("INVALID_SOURCE_CLAIM_BYTES")
    try:
        result=json.loads(raw.decode("utf-8"),object_pairs_hook=_object,
                          parse_constant=_reject_constant)
    except (UnicodeError,TypeError,ValueError,OverflowError):
        _fail("INVALID_SOURCE_CLAIM_BYTES")
    if type(result) is not dict or set(result)!=CLAIM_KEYS:
        _fail("INVALID_SOURCE_CLAIM_SCHEMA")
    return result


def _url(provider,value):
    if type(value) is not str or len(value)>700:
        return False
    try:
        parts=urlsplit(value)
        return (parts.scheme=="https" and parts.hostname in PROVIDERS[provider]
                and not parts.username and not parts.password and parts.port is None
                and not parts.fragment and not parts.query and parts.path.startswith("/")
                and len(parts.path)>1)
    except ValueError:
        return False


def _hold(reason):
    return {"schema":SCHEMA,"status":"HOLD","reason":reason,
            "two_distinct_claimed_publishers_agree":False,
            "claimed_publisher_count":0,
            "source_byte_sha256_unattested":[],
            "packet_sha256_unattested":None,
            "provider_identity_authenticated":False,
            "source_independence_verified":False,
            "third_party_timestamp_verified":False,
            "original_provider_response_authenticated":False,
            "eligible_for_model_input":False,
            "eligible_for_model_scoring":False,
            "odds_or_xg_verified":False,
            "positive_ev_verified":False,
            "certified_forward_samples":0,
            "recommendation":None,"roi":None,
            "production_recommendations":"DISABLED"}


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode("utf-8")


def audit(fixture, raw_claims, *, now=None):
    """Validate two asserted source *documents*, never provider authenticity.

    The asserted clocks, sealed identity, URLs, publisher labels, and bytes
    can all be fabricated by the caller. A passing packet is only a stable,
    self-hashed research handoff awaiting real externally authenticated data.
    """
    try:
        if (type(fixture) is not dict or set(fixture)!=FIXTURE_KEYS
                or not all(_id(fixture[k]) for k in
                           ("fixture_id","league_id","home_id","away_id"))
                or fixture["home_id"]==fixture["away_id"]):
            _fail("INVALID_FIXTURE")
        kickoff=_utc(fixture["kickoff_utc"])
        sealed=_utc(fixture["identity_sealed_utc"])
        decision=_utc(fixture["decision_utc"])
        if not sealed<=kickoff-timedelta(minutes=10) or not kickoff<decision:
            _fail("INVALID_CLAIMED_IDENTITY_OR_KICKOFF_ORDER")
        current=datetime.now(timezone.utc) if now is None else now
        if (not isinstance(current,datetime) or current.tzinfo is None
                or current.utcoffset() is None):
            _fail("INVALID_AUDIT_CLOCK")
        current=current.astimezone(timezone.utc)
        if not timedelta(0)<=current-decision<=MAX_AGE:
            _fail("STALE_OR_FUTURE_DECISION")
        if type(raw_claims) is not list or len(raw_claims)!=2:
            _fail("NEED_EXACTLY_TWO_SOURCE_CLAIMS")
        decoded=[_decode(raw) for raw in raw_claims]
        providers=[d["provider"] for d in decoded]
        if any(type(p) is not str or p not in PROVIDERS for p in providers):
            _fail("UNSUPPORTED_CLAIMED_PUBLISHER")
        if len(set(providers))!=2:
            _fail("DUPLICATE_CLAIMED_PUBLISHER")
        for row in decoded:
            provider=row["provider"]
            if (row["schema"]!=CLAIM_SCHEMA
                    or not _id(row["provider_event_id"])
                    or not _url(provider,row["source_url"])):
                _fail("INVALID_SOURCE_PUBLISHER_OR_URL")
            if (any(row.get(k)!=fixture[k] for k in
                    ("fixture_id","league_id","home_id","away_id"))
                    or _utc(row["kickoff_utc"])!=kickoff):
                _fail("CLAIMED_FIXTURE_IDENTITY_MISMATCH")
            update=_utc(row["source_updated_utc"])
            captured=_utc(row["captured_utc"])
            received=_utc(row["received_utc"])
            if (not update<=captured<=received<=decision
                    or decision-update>MAX_AGE or decision-received>MAX_AGE
                    or captured-update>MAX_AGE or received-captured>MAX_AGE):
                _fail("CLAIMED_RECEIPT_OUTSIDE_DECISION_CUT")
            if (row["match_status"] not in MATCH_STATES
                    or type(row["elapsed_regulation_minute"]) is not int
                    or not 0<=row["elapsed_regulation_minute"]<90
                    or any(type(row[k]) is not int or not 0<=row[k]<=30 for k in
                           ("home_goals","away_goals"))
                    or any(type(row[k]) is not int or not 0<=row[k]<=5 for k in
                           ("home_red_cards","away_red_cards"))
                    or type(row["var_review_pending"]) is not bool):
                _fail("INVALID_SOURCE_MATCH_STATE")
        state_fields=("match_status","elapsed_regulation_minute","home_goals",
                      "away_goals","home_red_cards","away_red_cards")
        if any(decoded[0][key]!=decoded[1][key] for key in state_fields):
            _fail("CROSS_SOURCE_STATE_CONFLICT")
        if any(row["var_review_pending"] for row in decoded):
            _fail("UNRESOLVED_VAR_REVIEW")
        state=decoded[0]
        status,minute=state["match_status"],state["elapsed_regulation_minute"]
        if ((status=="FIRST_HALF" and minute>=45)
                or (status=="HALF_TIME" and minute!=45)
                or (status=="SECOND_HALF" and minute<=45)):
            _fail("CLAIMED_PHASE_CLOCK_CONFLICT")
        elapsed=(decision-kickoff).total_seconds()/60
        if not minute-3<=elapsed<=minute+24:
            _fail("IMPOSSIBLE_CLAIMED_MATCH_CLOCK")
        summaries=sorted((
            {"provider_claim":doc["provider"],
             "provider_event_id_claim":doc["provider_event_id"],
             "source_url_sha256_unattested":hashlib.sha256(
                 doc["source_url"].encode("utf-8")).hexdigest(),
             "raw_claim_sha256_unattested":hashlib.sha256(raw).hexdigest(),
             "source_updated_utc_claim":_utc(doc["source_updated_utc"]).isoformat(),
             "captured_utc_claim":_utc(doc["captured_utc"]).isoformat(),
             "received_utc_claim":_utc(doc["received_utc"]).isoformat()}
            for doc,raw in zip(decoded,raw_claims)
        ),key=lambda x:x["provider_claim"])
        packet={
            "fixture_id_claim":fixture["fixture_id"],
            "league_id_claim":fixture["league_id"],
            "home_id_claim":fixture["home_id"],
            "away_id_claim":fixture["away_id"],
            "kickoff_utc_claim":kickoff.isoformat(),
            "identity_sealed_utc_claim":sealed.isoformat(),
            "decision_utc_claim":decision.isoformat(),
            "match_status_claim":status,"minute_claim":minute,
            "score_claim":[state["home_goals"],state["away_goals"]],
            "red_cards_claim":[state["home_red_cards"],state["away_red_cards"]],
            "sources":summaries}
        return {**_hold("TWO_UNAUTHENTICATED_SOURCE_CLAIMS_AGREE"),
                "status":"RESEARCH_ONLY",
                "two_distinct_claimed_publishers_agree":True,
                "claimed_publisher_count":2,
                "source_byte_sha256_unattested":[row["raw_claim_sha256_unattested"]
                                                  for row in summaries],
                "packet_sha256_unattested":hashlib.sha256(_canonical(packet)).hexdigest(),
                "packet_metadata_unattested":packet,
                "original_claim_bytes_archived_by_this_function":False,
                "research_packet_not_forecast_or_witness":True}
    except (ValueError,TypeError,OverflowError,KeyError,AttributeError):
        # Any unknown parser exception stays opaque, no original payload or
        # credential value may appear in an error or report.
        import sys
        exc=sys.exc_info()[1]
        allowed={
            "INVALID_FIXTURE","INVALID_CLAIMED_IDENTITY_OR_KICKOFF_ORDER",
            "INVALID_AUDIT_CLOCK","STALE_OR_FUTURE_DECISION",
            "NEED_EXACTLY_TWO_SOURCE_CLAIMS","INVALID_SOURCE_CLAIM_BYTES",
            "INVALID_SOURCE_CLAIM_SCHEMA","UNSUPPORTED_CLAIMED_PUBLISHER",
            "DUPLICATE_CLAIMED_PUBLISHER","INVALID_SOURCE_PUBLISHER_OR_URL",
            "CLAIMED_FIXTURE_IDENTITY_MISMATCH","CLAIMED_RECEIPT_OUTSIDE_DECISION_CUT",
            "INVALID_SOURCE_MATCH_STATE","CROSS_SOURCE_STATE_CONFLICT",
            "UNRESOLVED_VAR_REVIEW","CLAIMED_PHASE_CLOCK_CONFLICT",
            "IMPOSSIBLE_CLAIMED_MATCH_CLOCK"}
        return _hold(str(exc) if str(exc) in allowed else "INVALID_OR_UNTRUSTED_SOURCE_CLAIM")
