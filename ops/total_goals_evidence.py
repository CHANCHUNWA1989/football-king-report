"""Conservative pre-match total-goals evidence validation.

A positive Poisson EV is not a validated betting edge. This module emits
research candidates only; no live betting recommendations.
"""
from datetime import datetime, timezone
import math
from over_under_25 import evaluate

def _clock(value):
    if not isinstance(value,str):
        return None
    try:
        dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else None

def assess(rows, *, now_utc, max_quote_age_minutes=10):
    now=_clock(now_utc)
    if now is None or not isinstance(rows,list):
        raise ValueError("INVALID_INPUT")
    reports=[]
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("INVALID_ROW")
        reasons=[]
        kickoff=_clock(row.get("kickoff_utc"))
        quoted=_clock(row.get("odds_updated_utc"))
        if kickoff is None or kickoff<=now:
            reasons.append("NOT_VERIFIED_PREMATCH")
        if quoted is None or not (0<=(now-quoted).total_seconds()<=max_quote_age_minutes*60):
            reasons.append("ODDS_TIMESTAMP_MISSING_OR_STALE")
        if not isinstance(row.get("odds_source"),str) or not row["odds_source"].strip():
            reasons.append("ODDS_SOURCE_MISSING")
        if not isinstance(row.get("model_version"),str) or not row["model_version"].strip():
            reasons.append("MODEL_VERSION_MISSING")
        if row.get("out_of_sample_calibration_verified") is not True:
            reasons.append("MODEL_NOT_INDEPENDENTLY_CALIBRATED")
        if row.get("fixture_identity_verified") is not True:
            reasons.append("FIXTURE_IDENTITY_UNVERIFIED")
        candidate_input={k:row.get(k) for k in ("fixture_id","expected_goals","over_odds","under_odds")}
        candidate_input.update(calibrated=not reasons,fresh_odds=not reasons)
        try:
            result=evaluate([candidate_input])["results"][0]
        except (ValueError,TypeError,OverflowError):
            result={"fixture_id":row.get("fixture_id"),"market":"TOTAL_GOALS_2.5","status":"HOLD",
                    "blockers":["INVALID_MODEL_OR_ODDS_INPUT"]}
        if reasons:
            result["status"]="HOLD"
            result.pop("side",None)
            result["blockers"]=sorted(set(result.get("blockers",[])+reasons))
        result["production_recommendations"]="DISABLED"
        reports.append(result)
    return {"schema":"football-king-ou25-evidence-v1","status":"RESEARCH_ONLY",
            "candidate_count":sum(x["status"]=="RESEARCH_CANDIDATE" for x in reports),
            "production_recommendations":"DISABLED","results":reports}
