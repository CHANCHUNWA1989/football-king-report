#!/usr/bin/env python3
"""VNext Stage 4: fail-closed *offline* source/receipt evidence intake.

Safe to publish code, but NEVER publish vendor raw odds, xG, credentials, or
private receipts. Matching public results is NOT independent source proof.
No HTTP calls, no bookmaker offers, no EV, no prediction/model promotion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path

SCHEMA = "football-king-stage4-evidence-intake-v1"
MAX_ROWS = 2500
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
KINDS = ("xg", "forecast", "odds")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Explicit names for an offline Serie A cross-check only: never fuzzy merge.
# This translation cannot prove that source fixtures share native IDs.
CURATED_ALIASES = {
    "FC Internazionale Milano": "Internazionale", "AC Milan": "Milan",
    "AC Monza": "Monza", "ACF Fiorentina": "Fiorentina",
    "AS Roma": "Roma", "Atalanta BC": "Atalanta",
    "Bologna FC 1909": "Bologna", "Cagliari Calcio": "Cagliari",
    "Como 1907": "Como", "Frosinone Calcio": "Frosinone",
    "Genoa CFC": "Genoa", "Juventus FC": "Juventus",
    "Parma Calcio 1913": "Parma", "SS Lazio": "Lazio",
    "SSC Napoli": "Napoli", "Torino FC": "Torino",
    "US Lecce": "Lecce", "US Sassuolo Calcio": "Sassuolo",
    "Udinese Calcio": "Udinese", "Venezia FC": "Venezia",
}


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIME")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError("NAIVE_TIME")
        return result.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError("INVALID_TIME") from exc


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\d", value):
        raise ValueError("INVALID_DATE")
    return date.fromisoformat(value)


def _name(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 100 or value != value.strip():
        raise ValueError("INVALID_TEAM")
    return CURATED_ALIASES.get(value, value)


def _hold(blockers, **counts):
    # Never echo raw quotes, xG, bookmaker IDs, team IDs or vendor payloads.
    return {"schema": SCHEMA, "status": "HOLD", "scope": "RESEARCH_ONLY",
            "production_recommendations": "DISABLED", "verified_positive_ev": False,
            "independently_verified_results": 0, "certified_forward_samples": 0,
            "independent_upstreams_proven": False,
            "bookmaker_quote_executable_proven": False, "recommended_stakes": None,
            "blockers": sorted(set(blockers)), **counts}


def _index(rows, cutoff, captured):
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError("INVALID_COHORT_SIZE")
    found = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "date", "home", "away", "home_goals", "away_goals", "period"
        } or row["period"] != "FT90":
            raise ValueError("NOT_REGULATION_FULL_TIME")
        day = _date(row["date"])
        if day >= cutoff.date():
            raise ValueError("NOT_BEFORE_CUTOFF")
        if day > captured.date():
            raise ValueError("RESULT_FUTURE_RELATIVE_TO_CAPTURE")
        home, away = _name(row["home"]), _name(row["away"])
        if home == away:
            raise ValueError("SAME_TEAM")
        hg, ag = row["home_goals"], row["away_goals"]
        if any(type(x) is not int or not 0 <= x <= 15 for x in (hg, ag)):
            raise ValueError("INVALID_SCORE")
        key = (row["date"], home, away)
        if key in found:
            raise ValueError("DUPLICATE_MATCH")
        found[key] = (hg, ag)
    return found


def audit_result_overlap(left, right, *, as_of_utc):
    """Report shared retrospective score rows, but never certify provenance.

    Both feeds may derive from one original publisher, or be edited later.
    'captured_utc' is caller-supplied; it is not an external TSA witness.
    """
    blockers = {"INDEPENDENT_ORIGINATION_NOT_VERIFIED", "ACTUAL_KICKOFF_NOT_VERIFIED",
                "PREMATCH_FORECAST_AND_QUOTES_NOT_CERTIFIED",
                "HUMAN_RELEASE_REVIEW_REQUIRED"}
    counts = dict(left_rows=0, right_rows=0, common_fixtures=0,
                  identical_scores=0, conflicting_scores=0,
                  left_only=0, right_only=0)
    try:
        cutoff = _utc(as_of_utc)
        if not isinstance(left, dict) or not isinstance(right, dict):
            raise ValueError("INVALID_SOURCE_CONTRACT")
        for obj in (left, right):
            if set(obj) != {"source_id", "captured_utc", "rows", "upstream_declared"}:
                raise ValueError("INVALID_SOURCE_CONTRACT")
            if not isinstance(obj["source_id"], str) or not obj["source_id"].strip():
                raise ValueError("INVALID_SOURCE_ID")
            if not isinstance(obj["upstream_declared"], str) or not obj["upstream_declared"].strip():
                raise ValueError("MISSING_UPSTREAM_LINEAGE")
            if _utc(obj["captured_utc"]) > cutoff:
                raise ValueError("SOURCE_CAPTURE_AFTER_CUTOFF")
        if left["source_id"] == right["source_id"]:
            raise ValueError("SAME_SOURCE_ID")
        l, r = (_index(left["rows"], cutoff, _utc(left["captured_utc"])),
                _index(right["rows"], cutoff, _utc(right["captured_utc"])))
        overlap = set(l) & set(r)
        counts.update(left_rows=len(l), right_rows=len(r),
                      common_fixtures=len(overlap),
                      identical_scores=sum(l[k] == r[k] for k in overlap),
                      conflicting_scores=sum(l[k] != r[k] for k in overlap),
                      left_only=len(l) - len(overlap), right_only=len(r) - len(overlap))
        if not overlap:
            blockers.add("NO_OVERLAPPING_RESULTS")
        if counts["conflicting_scores"]:
            blockers.add("CONFLICTING_FT90_RESULTS")
        if left["upstream_declared"] == right["upstream_declared"]:
            blockers.add("SHARED_UPSTREAM_DECLARED")
        # Even two distinct declared upstream labels are not verified independent.
    except (ValueError, TypeError, KeyError) as exc:
        blockers.add("INVALID_OR_UNTRUSTED_RESULT_SOURCE")
        counts = dict.fromkeys(counts, 0)
        counts["validation_error"] = str(exc)
    return _hold(blockers, **counts)


def strict_json_bytes(payload):
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_ARTIFACT_BYTES:
        raise ValueError("INVALID_ARTIFACT_SIZE")
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("DUPLICATE_JSON_MEMBER")
            out[key] = value
        return out
    def no_constant(value):
        raise ValueError("NON_FINITE_JSON_NUMBER")
    return json.loads(payload.decode("utf-8"), object_pairs_hook=unique,
                      parse_constant=no_constant)


def audit_private_bundle(fixture, receipts, payloads):
    """Validate provenance *claims*, not provenance truth; never publish raw.

    Caller must retain immutable originals in private, access-controlled storage.
    This accepts no trusted timestamps just because a receipt says 'verified'.
    """
    blockers = {"LICENSE_AND_CHAIN_OF_CUSTODY_EXTERNAL_REVIEW_REQUIRED",
                "INDEPENDENT_PREMATCH_TIMESTAMP_WITNESS_MISSING",
                "CALIBRATED_OOS_MODEL_NOT_CERTIFIED",
                "MARKET_LEVEL_PRICE_EXECUTION_NOT_PROVEN",
                "INDEPENDENT_FT90_AND_ACTUAL_KO_UNVERIFIED",
                "INDEPENDENT_HUMAN_RELEASE_APPROVAL_MISSING"}
    counts = {"raw_digest_matches": 0, "artifacts_locally_valid": 0,
              "xg_matches_validated": 0, "required_artifacts_present": False}
    try:
        if (not isinstance(fixture, dict) or set(fixture) !=
                {"fixture_id", "kickoff_utc", "league"}):
            raise ValueError("INVALID_FIXTURE")
        if any(not isinstance(fixture[k], str) or not fixture[k].strip()
               for k in ("fixture_id", "league")):
            raise ValueError("INVALID_FIXTURE_ID")
        ko = _utc(fixture["kickoff_utc"])
        if (not isinstance(receipts, dict) or not isinstance(payloads, dict)
                or set(receipts) != set(KINDS) or set(payloads) != set(KINDS)):
            raise ValueError("MISSING_OR_EXTRA_ARTIFACT")
        counts["required_artifacts_present"] = True
        times = {}
        for kind in KINDS:
            meta, payload = receipts[kind], payloads[kind]
            required = {"kind", "fixture_id", "observed_utc", "captured_utc",
                        "source_id", "provider_native_id", "sha256", "license_reference"}
            if not isinstance(meta, dict) or set(meta) != required or meta["kind"] != kind:
                raise ValueError("INVALID_RECEIPT")
            if meta["fixture_id"] != fixture["fixture_id"]:
                raise ValueError("CROSS_ARTIFACT_FIXTURE_MISMATCH")
            if any(not isinstance(meta[k], str) or not meta[k].strip()
                   for k in ("source_id", "provider_native_id", "license_reference")):
                raise ValueError("MISSING_SOURCE_ID_OR_LICENSE_REVIEW_REFERENCE")
            observed, captured = _utc(meta["observed_utc"]), _utc(meta["captured_utc"])
            if not (observed <= captured < ko):
                raise ValueError("POST_KICKOFF_OR_FUTURE_SOURCE")
            if kind == "odds" and (captured - observed).total_seconds() > 120:
                raise ValueError("STALE_MARKET_RECEIPT")
            if (not isinstance(meta["sha256"], str) or
                HEX64.fullmatch(meta["sha256"]) is None):
                raise ValueError("INVALID_DIGEST")
            if hashlib.sha256(payload).hexdigest() != meta["sha256"]:
                raise ValueError("DIGEST_MISMATCH")
            counts["raw_digest_matches"] += 1
            parsed = strict_json_bytes(payload)
            if not isinstance(parsed, (dict, list)):
                raise ValueError("INVALID_VENDOR_JSON_ROOT")
            if kind == "xg":
                if not isinstance(parsed, dict) or set(parsed) != {"provider", "matches"}:
                    raise ValueError("INVALID_XG_FORMAT")
                rows = parsed["matches"]
                if not isinstance(rows, list) or not 1 <= len(rows) <= 2500:
                    raise ValueError("INVALID_XG_ROWS")
                ids = set()
                for row in rows:
                    if not isinstance(row, dict) or set(row) != {
                        "provider_match_id", "kickoff_utc", "published_utc", "home_xg", "away_xg"
                    }:
                        raise ValueError("INVALID_XG_ROW")
                    mid = row["provider_match_id"]
                    if not isinstance(mid, str) or not mid.strip() or mid in ids:
                        raise ValueError("DUPLICATE_OR_INVALID_XG_ID")
                    ids.add(mid)
                    if not (_utc(row["kickoff_utc"]) < _utc(row["published_utc"])
                            <= observed < ko):
                        raise ValueError("UNAVAILABLE_OR_FUTURE_XG_HISTORY")
                    if any(type(row[k]) not in (float, int) or
                           not math.isfinite(row[k]) or not 0 <= row[k] <= 15
                           for k in ("home_xg", "away_xg")):
                        raise ValueError("INVALID_XG")
                counts["xg_matches_validated"] = len(rows)
            times[kind] = captured
            counts["artifacts_locally_valid"] += 1
        if not (times["xg"] <= times["forecast"] <= times["odds"] < ko):
            raise ValueError("LOOKAHEAD_OR_SOURCE_TIMELINE_MISMATCH")
        if (ko - times["odds"]).total_seconds() <= 600:
            raise ValueError("INSUFFICIENT_PREMATCH_LEAD")
        # Vendor payload parsing / odds validation must use repo's existing
        # market_quote_gate + stage3 bridge; do not reimplement or assume passed.
        blockers.add("MARKET_QUOTE_GATE_AND_STAGE3_BRIDGE_NOT_SUPPLIED")
    except (ValueError, TypeError, KeyError, UnicodeDecodeError) as exc:
        blockers.add("PRIVATE_ARTIFACT_VALIDATION_FAILED")
        counts["validation_error"] = str(exc)
    return _hold(blockers, **counts)


def main():
    p = argparse.ArgumentParser(description="Offline private bundle receipts, redacted HOLD")
    p.add_argument("--fixture", required=True)
    p.add_argument("--receipts", required=True)
    p.add_argument("--xg", required=True)
    p.add_argument("--forecast", required=True)
    p.add_argument("--odds", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    # Do not accept arbitrary output trees or public Actions artifacts as safe
    # merely because they pass this CLI; caller controls private permissions.
    report = audit_private_bundle(json.loads(Path(a.fixture).read_text()),
                                  json.loads(Path(a.receipts).read_text()),
                                  {k: Path(getattr(a, k)).read_bytes() for k in KINDS})
    Path(a.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": report["status"],
                      "blockers": report["blockers"],
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()