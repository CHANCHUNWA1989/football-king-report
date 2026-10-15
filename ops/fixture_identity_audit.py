"""Fail-closed validation of archived fixture identity reuse."""
from collections import defaultdict

def conflicting_fixture_ids(rows):
    identities=defaultdict(set)
    for row in rows:
        if not isinstance(row,dict):
            continue
        fid=row.get("fixture_id")
        if not isinstance(fid,str) or not fid:
            continue
        identity=(row.get("kickoff_utc"),row.get("home"),row.get("away"))
        identities[fid].add(identity)
    return sorted(fid for fid,values in identities.items() if len(values)>1)

def identity_audit_report(rows):
    conflicts=conflicting_fixture_ids(rows)
    return {"schema":"football-king-identity-audit-v1",
            "status":"RESEARCH_ONLY",
            "conflicting_fixture_id_count":len(conflicts),
            "conflicting_fixture_ids":conflicts,
            "independently_verified":False,
            "production_recommendations":"DISABLED"}
