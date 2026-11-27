"""V38: reconcile an explicitly declared batch against V35 deterministic replay.
The caller roster is not proof of complete fixture coverage or independent provenance.
No pricing, training or production permission is granted.
"""
from collections import Counter
from .research_unified_prematch_replay_v35 import verify

MAX_EVENTS = 256

def valid_id(value):
    return (type(value) is str and 0 < len(value) <= 256
            and value == value.strip() and value.isprintable())

def reconcile(expected_ids, records, *, root="."):
    report = {
        "schema": "unified-batch-replay-v38",
        "status": "HOLD", "production_recommendations": "DISABLED",
        "batch_replay_verified": False, "roster_authenticated": False,
        "source_identity_authenticated": False, "external_timestamp_verified": False,
        "training_admission": False, "qualified_for_production": False,
        "verified_executable_ev": False, "verified_event_count": 0,
    }
    if (type(expected_ids) not in (list, tuple) or not 1 <= len(expected_ids) <= MAX_EVENTS
            or any(not valid_id(e) for e in expected_ids)
            or len(set(expected_ids)) != len(expected_ids)):
        return dict(report, reason="INVALID_EXPECTED_ROSTER")
    if type(records) not in (list, tuple) or len(records) > MAX_EVENTS:
        return dict(report, reason="INVALID_RECORD_BATCH")
    expected = set(expected_ids)
    counts = Counter()
    verified = set()
    failed = set()
    malformed = 0
    for record in records:
        if type(record) is not dict or not valid_id(record.get("event_id")):
            malformed += 1
            continue
        event = record["event_id"]
        counts[event] += 1
        if event not in expected:
            continue
        try:
            result = verify(record, root=root)
            if (result.get("replay_verified") is True
                    and result.get("status") == "HOLD"
                    and result.get("production_recommendations") == "DISABLED"
                    and all(result.get(k) is False for k in (
                        "external_timestamp_verified", "source_identity_authenticated",
                        "training_admission", "qualified_for_production"))):
                verified.add(event)
            else:
                failed.add(event)
        except (ValueError, TypeError, KeyError, AttributeError, OSError,
                OverflowError, RecursionError):
            failed.add(event)
    duplicates = {e for e, n in counts.items() if n > 1}
    missing = expected - counts.keys()
    unexpected = counts.keys() - expected
    usable = verified - failed - duplicates
    complete = (not missing and not unexpected and not duplicates and not failed
                and not malformed and usable == expected)
    report.update(expected_count=len(expected), submitted_count=len(records),
                  verified_event_count=len(usable), missing_ids=sorted(missing),
                  unexpected_ids=sorted(unexpected), duplicate_ids=sorted(duplicates),
                  failed_ids=sorted(failed), malformed_record_count=malformed,
                  batch_replay_verified=complete)
    if not complete:
        report["reason"] = "BATCH_RECONCILIATION_FAILED"
    return report
