"""Fail-closed, read-only independent full-time score audit.

Only explicitly identified independent upstream feeds can corroborate a result.
No sealed evidence or production recommendations are changed.
"""
from collections import defaultdict
from ops.result_consensus_gate import verify_result

def audit_results(fixtures, observations):
    if not isinstance(fixtures, list) or not isinstance(observations, list):
        raise ValueError("invalid audit input")
    if len(fixtures) > 10000 or len(observations) > 50000:
        raise ValueError("audit limit")
    grouped = defaultdict(list)
    for row in observations:
        if not isinstance(row, dict):
            continue
        fixture_id = row.get("fixture_id")
        group_id = row.get("independent_group_id")
        if not isinstance(fixture_id, str) or not isinstance(group_id, str) or not group_id.strip():
            continue
        grouped[fixture_id].append(row)
    seen = set()
    rows = []
    verified_count = 0
    for fixture in fixtures:
        if not isinstance(fixture, dict):
            raise ValueError("invalid fixture")
        fid = fixture.get("fixture_id")
        if not isinstance(fid, str) or not fid or fid in seen:
            raise ValueError("duplicate fixture id")
        seen.add(fid)
        verdict = verify_result(fid, fixture.get("kickoff_utc"), grouped.get(fid, []))
        rows.append(verdict)
        verified_count += verdict["status"] == "VERIFIED"
    return {"schema": "football-king-result-audit-v1",
            "production_recommendations": "DISABLED",
            "verified_count": verified_count,
            "results": rows}
