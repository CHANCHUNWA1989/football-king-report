"""Public metadata-only crosswalk of TWO historical FT evidence candidates.

This code cannot decrypt originals, authenticate source identity, discover
official actual kickoff, validate native source IDs against archived fixtures,
prove an independent upstream, or certify model calibration and EV.

Only fixed public display reference claims are compared with existing ledger
records. Matching names / kickoff / outcome is NOT identity or FT proof.
No API calls, key reads, ciphertext decryptions, model scoring or file writes.
"""
import json
import math
import re
from datetime import datetime, timedelta, timezone

MAX_ROWS = 1000
PRODUCTION_RECOMMENDATIONS = "DISABLED"

CANDIDATES = {
    "2508371": {
        "key": '["bundesliga", "borussiadortmund", "svwerderbremen", "2026-10-09T18:30:00+00:00"]',
        "score_ft_public_claim": [2, 2],
        "y": 1,
        "official_public_url": "https://www.bundesliga.com/en/bundesliga/matchday/2026-2027/5/borussia-dortmund-vs-sv-werder-bremen/liveticker/",
        "second_public_url": "https://www.sportschau.de/live-und-ergebnisse/die-finals/deutschland-bundesliga/ma12194071/borussia-dortmund_werder-bremen/liveticker",
    },
    "2508372": {
        "key": '["bundesliga", "tsghoffenheim", "hamburgersv", "2026-10-10T13:30:00+00:00"]',
        "score_ft_public_claim": [2, 3],
        "y": 2,
        "official_public_url": "https://www.bundesliga.com/en/bundesliga/matchday/2026-2027/5/tsg-hoffenheim-vs-hamburger-sv/liveticker",
        "second_public_url": "https://www.sportschau.de/live-und-ergebnisse/die-finals/deutschland-bundesliga/ma12194095/tsg-hoffenheim_hamburger-sv/liveticker",
    },
}
RECEIPT_KEYS = frozenset({
    "actual_kickoff_authenticated", "ciphertext_bytes", "ciphertext_sha256",
    "encryption", "event_id", "independently_verified", "original_sha256",
    "production_recommendations", "raw_sha256", "recipient_sha256",
    "schema", "status", "upstream_independence_authenticated",
})


def _utc(value):
    if not isinstance(value, str) or len(value) > 60:
        raise ValueError("INVALID_TIMESTAMP")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        raise ValueError("INVALID_TIMESTAMP") from None
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("INVALID_TIMESTAMP")
    return stamp.astimezone(timezone.utc)


def _receipt_safe(event_id, obj):
    if not isinstance(obj, dict) or set(obj) != RECEIPT_KEYS:
        return False
    if (obj.get("event_id") != event_id
            or obj.get("schema") != "football-king-sportsdb-age-ciphertext-v1"
            or obj.get("status") != "HOLD"
            or obj.get("encryption") != "age-v1.3.2-native-pq"
            or obj.get("independently_verified") is not False
            or obj.get("actual_kickoff_authenticated") is not False
            or obj.get("upstream_independence_authenticated") is not False
            or obj.get("production_recommendations") != "DISABLED"
            or type(obj.get("ciphertext_bytes")) is not int
            or not 1 <= obj["ciphertext_bytes"] <= 600_000):
        return False
    for field in ("ciphertext_sha256", "original_sha256",
                  "raw_sha256", "recipient_sha256"):
        value = obj.get(field)
        if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
            return False
    # This is merely a syntactic receipt screen. Cryptographic original-byte
    # verification must happen separately via sportsdb_public_cipher_audit.
    return True


def _row_safe(item, candidate):
    if (not isinstance(item, dict)
            or item.get("key") != candidate["key"]
            or item.get("production_recommendations") != "DISABLED"
            or item.get("fixture_result_source_independently_verified") is not False
            or type(item.get("y")) is not int or item["y"] != candidate["y"]
            or item.get("league") != "bundesliga"):
        return False
    try:
        kickoff = _utc(item["kickoff_utc"])
        market = _utc(item["market_utc"])
        forecast = _utc(item["forecast_utc"])
        identity = json.loads(candidate["key"])
        if (len(identity) != 4 or _utc(identity[3]) != kickoff
                or not market <= forecast <= kickoff - timedelta(minutes=10)
                or forecast - market > timedelta(minutes=750)):
            return False
        for field in ("p", "m"):
            probabilities = item[field]
            if (not isinstance(probabilities, list)
                    or len(probabilities) != 3
                    or any(type(x) not in (int, float) or not math.isfinite(x)
                           or not 0 <= x <= 1 for x in probabilities)
                    or abs(sum(probabilities) - 1) > .002):
                return False
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError):
        return False
    return True


def audit(archived_samples, public_receipts):
    """Record two name/time/score matches and ALWAYS refuse certification."""
    if (not isinstance(archived_samples, list)
            or not archived_samples or len(archived_samples) > MAX_ROWS):
        raise ValueError("INVALID_ARCHIVE_SIZE")
    if (not isinstance(public_receipts, dict)
            or set(public_receipts) != set(CANDIDATES)):
        raise ValueError("INVALID_RECEIPT_SET")
    # A duplicate archive key quarantines the entire candidate, rather
    # than silently using the first or most favorable row.
    indexed = {case["key"]: [] for case in CANDIDATES.values()}
    for item in archived_samples:
        if isinstance(item, dict):
            key = item.get("key")
            if isinstance(key, str) and key in indexed:
                indexed[key].append(item)
    matches, quarantined = [], []
    for event, candidate in CANDIDATES.items():
        rows = indexed[candidate["key"]]
        if len(rows) != 1 or not _row_safe(rows[0], candidate) or not _receipt_safe(
                event, public_receipts[event]):
            quarantined.append(event)
            continue
        matches.append({
            "event_id": event,
            "archived_fixture_key": candidate["key"],
            "score_ft_public_claim": candidate["score_ft_public_claim"],
            "official_public_url": candidate["official_public_url"],
            "second_public_url": candidate["second_public_url"],
            "source_match_quality": "CLAIMED_NAME_TIME_SCORE_ONLY",
            "native_fixture_id_authenticated": False,
            "encrypted_original_plaintext_verified": False,
            "second_upstream_independence_verified": False,
            "official_actual_kickoff_verified": False,
            "forward_forecast_bytes_authenticated": False,
            "positive_ev_verified": False,
            "eligible_for_model_scoring": False,
        })
    return {
        "schema": "football-king-first-two-ft-public-candidate-join-v1",
        "status": "HOLD",
        "candidate_count": len(matches),
        "candidate_matches": matches,
        "quarantined_event_ids": quarantined,
        "certified_case_count": 0,
        "independently_verified": False,
        "eligible_for_model_scoring": False,
        "public_source_content_authenticated_by_ci": False,
        "public_receipt_integrity_cryptographically_verified_here": False,
        "production_recommendations": PRODUCTION_RECOMMENDATIONS,
    }
