"""One-shot evidence readiness inventory. Research only, never a betting gate.

Consumes safe existing *public summaries* and quarantines every self-reported
independence claim. Only a separately implemented, externally reviewed
admission protocol may credit certified prospective cases; NONE exists here.
No price, probability, bookmaker, fixture identity or private file is read.
"""
import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import os

SCHEMA = "football-king-batch-research-readiness-v1"
MAX_SOURCE_BYTES = 1_000_000
REQUIRED_CERTIFIED = 300


def _stamp(value):
    if type(value) is not str or len(value) > 80:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _natural(value):
    return type(value) is int and 0 <= value <= 10_000_000


def _fail_report(reason):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED",
        "verified_value_bets": 0, "verified_positive_ev_bets": 0,
        "independently_certified_forward_cases": 0,
        "missing_independently_certified_cases": REQUIRED_CERTIFIED,
        "model_promotion_allowed": False, "betting_recommendation_allowed": False,
        "independent_result_admission_available": False,
    }


def evaluate(collection, market_summary, settled, *, now=None):
    """Read-only public evidence overview, not a source of certification."""
    when = datetime.now(timezone.utc) if now is None else now
    if type(when) is not datetime or when.tzinfo is None or when.utcoffset() is None:
        return _fail_report("INVALID_AUDIT_CLOCK")
    when = when.astimezone(timezone.utc)
    if any(type(d) is not dict for d in (collection, market_summary, settled)):
        return _fail_report("INVALID_PUBLIC_SOURCE_SHAPE")
    for doc in (collection, market_summary, settled):
        if doc.get("production_recommendations") != "DISABLED":
            return _fail_report("PUBLIC_SOURCE_RELEASE_POLICY_CONFLICT")
    if (collection.get("schema") != "football-king-free-market-collection-status-v1"
            or market_summary.get("schema") != "football-king-public-artifact-summary-v1"):
        return _fail_report("INVALID_PUBLIC_SOURCE_SCHEMA")
    counts, progress = market_summary.get("counts"), market_summary.get("evidence_progress")
    quota = collection.get("quota")
    if any(type(d) is not dict for d in (counts, progress, quota)):
        return _fail_report("INVALID_PUBLIC_COUNT_SHAPE")
    numeric = {
        "research_observations": counts.get("RESEARCH_ONLY"),
        "market_verified_value_claim": counts.get("VERIFIED_VALUE"),
        "settled_archive_rows": settled.get("n"),
        "market_summary_archive_rows": progress.get("settled_cases_in_archive"),
        "independently_verified_claim": progress.get("independently_verified_result_cases", 0),
        "quota_used": quota.get("used"), "quota_remaining": quota.get("remaining"),
    }
    if any(not _natural(n) for n in numeric.values()):
        return _fail_report("INVALID_PUBLIC_COUNT_VALUE")
    if (settled.get("results_independently_verified") is not False
            or market_summary.get("quotes_are_executable") is not False
            or market_summary.get("raw_prices_or_bookmakers_included") is not False):
        return _fail_report("UNSAFE_PUBLIC_SOURCE_CLAIM")
    stamps = {
        "collection": _stamp(collection.get("as_of_utc")),
        "market_summary": _stamp(market_summary.get("captured_utc")),
        "settled": _stamp(settled.get("checked_utc")),
    }
    fresh = {
        name: time is not None and timedelta(0) <= when-time <= timedelta(hours=24)
        for name, time in stamps.items()
    }
    reason = (
        "PUBLIC_SNAPSHOTS_STALE_OR_UNKNOWN" if not all(fresh.values()) else
        "NO_INDEPENDENT_PROSPECTIVE_ADMISSION_OR_EXECUTABLE_PRICES"
    )
    # A row counted as settled is not an independently admitted original.
    # No input-controlled independent/verified flag may change this zero.
    return {
        **_fail_report(reason),
        "public_snapshots_fresh_24h": fresh,
        "market_collector_status": (
            collection.get("collection_status")
            if collection.get("collection_status") in ("HOLD", "CONNECTED", "RESEARCH_ONLY")
            else "UNVERIFIED"),
        "market_collection_reason": (
            collection.get("collection_reason")
            if collection.get("collection_reason") in (
                "FREE_QUOTA_GUARD", "NOT_CONFIGURED", "PROVIDER_ERROR",
                "QUOTA_GUARD", "NO_ACTIVE_LEAGUES") else "UNVERIFIED"),
        "public_research_quote_observations": numeric["research_observations"],
        "independently_executable_bookmaker_quotes": 0,
        "public_settled_research_rows": numeric["settled_archive_rows"],
        "public_summary_archive_rows_as_of_earlier_snapshot": numeric["market_summary_archive_rows"],
        "public_independence_claims_disregarded": numeric["independently_verified_claim"],
        "market_value_claims_disregarded": numeric["market_verified_value_claim"],
        "free_quota_used": numeric["quota_used"],
        "free_quota_remaining": numeric["quota_remaining"],
        "next_required_evidence": [
            "INDIVIDUALLY_PINNED_ORIGINAL_PREMATCH_FORECAST_AND_QUOTE",
            "INDEPENDENTLY_REVIEWED_TSA_AND_CA_POLICY",
            "VERIFIED_NATIVE_FIXTURE_IDENTITY_CROSS_SOURCE",
            "TWO_UPSTREAM_INDEPENDENT_REGULATION_FT_ORIGINALS",
            "EXECUTABLE_BOOKMAKER_QUOTE_AUTHENTICATION",
            "PAIRED_PROSPECTIVE_OUT_OF_SAMPLE_COMPARISON",
        ],
    }


def _load(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file() or not 0 < p.stat().st_size <= MAX_SOURCE_BYTES:
        raise ValueError("INVALID_PUBLIC_INPUT")
    return json.loads(p.read_text(encoding="utf-8"))


def _summary_text(r):
    safe = {
        "quotes": r.get("public_research_quote_observations", "N/A"),
        "settled": r.get("public_settled_research_rows", "N/A"),
        "certified": r["independently_certified_forward_cases"],
        "required": REQUIRED_CERTIFIED,
        "reason": r["reason"],
    }
    return (
        "## Football King — batch research evidence audit\n\n"
        f"- **Research quote observations:** {safe['quotes']} (not executable)\n"
        f"- **Unverified settled archive rows:** {safe['settled']}\n"
        f"- **Independent certified prospective cases:** {safe['certified']}/{safe['required']}\n"
        f"- **Gate:** HOLD / production DISABLED\n"
        f"- **Reason:** \\x60{safe['reason']}\\x60\n"
        "- No real issuer/source trust, EV advantage or staking is claimed.\n"
    ).replace("\\x60", "`")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--market-summary", required=True)
    parser.add_argument("--settled", required=True)
    args = parser.parse_args(argv)
    try:
        report = evaluate(_load(args.collection), _load(args.market_summary),
                          _load(args.settled))
    except (ValueError, TypeError, OSError, RecursionError):
        report = _fail_report("PUBLIC_READINESS_INPUT_UNAVAILABLE")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    step = os.environ.get("GITHUB_STEP_SUMMARY")
    if step:
        with open(step, "a", encoding="utf-8") as handle:
            handle.write(_summary_text(report))
    # This CLI is an observation tool, never an approving release workflow.
    return 0 if report["reason"] not in (
        "PUBLIC_READINESS_INPUT_UNAVAILABLE", "INVALID_PUBLIC_SOURCE_SHAPE",
        "INVALID_PUBLIC_SOURCE_SCHEMA", "INVALID_PUBLIC_COUNT_VALUE",
        "INVALID_PUBLIC_COUNT_SHAPE", "UNSAFE_PUBLIC_SOURCE_CLAIM",
        "PUBLIC_SOURCE_RELEASE_POLICY_CONFLICT") else 1


if __name__ == "__main__":
    raise SystemExit(main())
