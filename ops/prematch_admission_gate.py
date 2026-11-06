"""Fail-closed admission report for independently verified prematch evidence.

Caller assertions never constitute independent source or timestamp verification.
"""
from pathlib import Path
from prematch_evidence_chain import verify_evidence_chain


def assess_prematch_admission(directory, *, fixture_id=None, provider_id=None,
                             independent_source_receipt=None,
                             independent_timestamp_receipt=None,
                             heldout_validation=None):
    failures = []
    checks = {}
    def check(name, valid, reason):
        checks[name] = bool(valid)
        if not valid:
            failures.append(reason)
    try:
        chain = verify_evidence_chain(directory)
        check("archive_chain", bool(chain), "EMPTY_EVIDENCE_CHAIN")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        chain = []
        check("archive_chain", False, "INVALID_EVIDENCE_CHAIN")
    check("fixture_id", isinstance(fixture_id, str) and bool(fixture_id.strip()),
          "MISSING_FIXTURE_ID")
    check("provider_id", isinstance(provider_id, str) and bool(provider_id.strip()),
          "MISSING_PROVIDER_ID")
    # Receipts are not considered verified merely because a caller sets a flag.
    # Integration with an independently pinned authority is required.
    check("independent_source", False, "INDEPENDENT_SOURCE_NOT_VERIFIED")
    check("trusted_timestamp", False, "TRUSTED_TIMESTAMP_NOT_VERIFIED")
    check("heldout_performance", False, "HELDOUT_PERFORMANCE_NOT_VERIFIED")
    return {"status": "HOLD", "reason": "PRODUCTION_ADMISSION_DENIED",
            "checks": checks, "rejection_reasons": failures,
            "evidence_entries": len(chain),
            "production_recommendations": "DISABLED"}
