"""Bridge replayable prematch scenarios to existing live probability-only research.

No new fitted red-card parameters, external authentication or production signals.
The prematch decision clock is local and untrusted; replay cannot prove chronology.
"""
from .research_snapshot_replay_v3 import replay as prematch_replay, _decode
from .research_live_pipeline_v10 import capture as live_capture, replay as live_replay
from .research_unified_live_v2 import utc, digest

def safety():
    return {"schema":"prematch-live-bridge-v4","status":"HOLD",
            "production_recommendations":"DISABLED","authenticated_samples":0,
            "source_authenticity_verified":False,"independent_oos_proven":False,
            "certified_ev":False,"model_promotion_allowed":False,
            "calibrated":False}

def link(*, prematch_raw,prematch_receipt,live_raw_captures,policy,as_of,model_release):
    """Only allow a live prior identical to the locally replayed prematch scenario.

    A missing or conflicting source, clock, prior or fixture blocks the entire link.
    Uses the existing phase-clock, red-card and recent non-penalty xG engine.
    No live market is accepted in this probability-only pathway.
    """
    out=safety()
    try:
        if not prematch_replay(prematch_raw,prematch_receipt)["replay_passed"]:
            raise ValueError("prematch replay failed")
        p=_decode(prematch_raw)
        kickoff=utc(p["kickoff"])
        frozen=utc(p["as_of"])
        now=utc(as_of)
        if not frozen<kickoff<=now:
            raise ValueError("clock mismatch")
        live=live_capture(live_raw_captures,policy,event_id=p["fixture_id"],as_of=as_of,
                          model_release=model_release,probability_only=True,source_bound=True)
        bundle=live_replay(live,live_raw_captures,policy)
        prior=bundle["prior"]
        if (bundle["event_id"]!=p["fixture_id"] or prior["event_id"]!=p["fixture_id"]
            or utc(bundle["snapshot"]["kickoff"])!=kickoff
            or utc(prior["frozen_at"])!=frozen
            or [prior["home_xg"],prior["away_xg"]]!=p["rates"]):
            raise ValueError("prematch and live prior mismatch")
        report=bundle["report"]
        if "hypothetical_ev" in report or bundle["market_evidence"]!="ABSENT":
            raise ValueError("unexpected market evidence")
        if not prematch_replay(prematch_raw,prematch_receipt)["replay_passed"]:
            raise ValueError("prematch source drift")
        h,a,rh,ra,_=report["state"]
        trailing="home" if h<a else "away" if a<h else None
        keys=("home","draw","away","over_2_5")
        result={**out,"structural_link_passed":True,"market_evidence":"ABSENT",
                "prematch_receipt_sha256":prematch_receipt["receipt_sha256"],
                "live_receipt_sha256":live["sha256"],"fixture_id":p["fixture_id"],
                "frozen_prior_kind":"UNCALIBRATED_ASSUMPTION",
                "score":[h,a],"red_cards":[rh,ra],"minute":report["minute"],
                "phase":report["phase"],"horizon_minutes":report["horizon_minutes"],
                "baseline":{k:report["baseline"][k] for k in keys},
                "dynamic":{k:report["dynamic"][k] for k in keys},
                "scenario_ranges":report["scenario_ranges"],
                "trailing_side":trailing,
                "comeback_win_scenario":report["dynamic"][trailing] if trailing else None,
                "comeback_win_range":report["scenario_ranges"][trailing] if trailing else None}
        result["link_sha256"]=digest(result)
        return result
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError,OSError,RecursionError):
        return {**out,"structural_link_passed":False,
                "reason":"INVALID_OR_INCONSISTENT_PREMATCH_LIVE_EVIDENCE"}
