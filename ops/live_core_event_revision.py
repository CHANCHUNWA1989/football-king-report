"""Dual-publisher state transition audit. No inferred VAR retraction.

A decreasing score/card count is quarantined, even if both sources agree.
The two sources may share an upstream feed. Never silently overwrite prior
forecasts; corrections require explicit event identity and independent review.
"""
from live_core_real_observations import evidence,digest
from live_snapshot_adapter import valid,hold


def audit(previous,a,b,now):
    try:
        left,lh=evidence(a,now)
        right,rh=evidence(b,now)
        if lh==rh or a["payload_sha256"]==b["payload_sha256"] or left["origin"]==right["origin"]:
            return hold("DUPLICATE_EVIDENCE")
        if abs(left["observed"]-right["observed"])>30:
            return hold("UNSYNCED")
        keys=("fixture_id","phase","minute","home","away","red_home","red_away")
        if any(left[k]!=right[k] for k in keys):
            return hold("PUBLISHER_DISAGREEMENT")
        if not valid(previous) or previous["fixture_id"]!=left["fixture_id"]:
            return hold("PREVIOUS_STATE_INVALID")
        if any(s[k]<previous[k] for s in (left,right) for k in ("observed","received","minute")):
            return hold("CLOCK_ROLLBACK")
        changed={k:[previous[k],left[k]] for k in ("home","away","red_home","red_away") if left[k]!=previous[k]}
        corrections=[k for k,(old,new) in changed.items() if new<old]
        return {**hold("CORRECTION_REVIEW_REQUIRED" if corrections else "MONOTONIC_TRANSITION_CLAIM"),
                "changes":changed,"correction_fields":corrections,
                "review_digest_unattested":digest([previous,a,b,now]),
                "previous_forecast_rewrite_allowed":False,
                "auto_resume_allowed":False if corrections else None}
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError):
        return hold("INVALID_TRANSITION")
