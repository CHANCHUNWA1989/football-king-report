"""Read-only independent final-score verification audit.

Does not alter sealed forecasts, evidence, or production recommendations.
"""
from ops.result_consensus_gate import verify_result

def audit_results(fixtures, observations):
    if not isinstance(fixtures, list) or not isinstance(observations, list):
        raise ValueError("invalid audit input")
    if len(fixtures) > 10000 or len(observations) > 50000:
        raise ValueError("audit limit")
    seen = set()
    rows = []
    for fixture in fixtures:
        if not isinstance(fixture, dict):
            raise ValueError("invalid fixture")
        fid = fixture.get("fixture_id")
        if not isinstance(fid, str) or not fid or fid in seen:
            raise ValueError("duplicate fixture id")
        seen.add(fid)
        sources = [row for row in observations if isinstance(row, dict) and row.get("fixture_id") == fid]
        rows.append(verify_result(fid, fixture.get("kickoff_utc"), sources))
    return {"schema": "football-king-result-audit-v1",
            "production_recommendations": "DISABLED",
            "verified_count": sum(row["status"] == "VERIFIED" for row in rows),
            "results": rows}
