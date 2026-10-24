"""An explicit, fail-closed qualification checklist for real betting advice.

This gate can evaluate research readiness, but can NEVER silently authorize
production recommendations or create executable bets. External executable
prices, verifiable result provenance and independent review are unavailable.
"""
import argparse
import json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from evidence_merge import validate as validate_evidence

MIN_SAMPLES=300
MIN_WEEKS=12
MIN_LEAGUES=4


def gate(center,evidence,validation):
    if not all(isinstance(x,dict) for x in (center,evidence,validation)):
        raise ValueError("INVALID_GATE_INPUT")
    if (center.get("production_recommendations")!="DISABLED"
            or evidence.get("production_recommendations")!="DISABLED"
            or validation.get("production_recommendations")!="DISABLED"):
        raise ValueError("UNSAFE_SOURCE_FOR_GATE")
    rows=evidence.get("samples")
    if not isinstance(rows,list):
        raise ValueError("INVALID_SETTLED_SAMPLES")
    if evidence.get("n")!=len(rows):
        raise ValueError("SETTLED_SAMPLE_MISMATCH")
    if rows:
        validate_evidence(evidence)  # do not count forged or malformed settlement rows
    weeks=set()
    leaguecounts=Counter()
    for r in rows:
        try:
            if r.get("production_recommendations")!="DISABLED":
                raise ValueError("UNSAFE_SETTLED_ROW")
            t=datetime.fromisoformat(str(r["kickoff_utc"]).replace("Z","+00:00"))
            if t.tzinfo is None:raise ValueError("NAIVE_KICKOFF")
            weeks.add(t.isocalendar()[:2])
            leaguecounts[r["league"]]+=1
        except (KeyError,TypeError,ValueError,OverflowError):
            raise ValueError("INVALID_SETTLED_ROW") from None
    measures=validation.get("measurements") or {}
    ci=measures.get("difference_block_bootstrap_95pct_ci")
    positive_ci=(isinstance(ci,list) and len(ci)==2 and
                 all(type(x) in (int,float) for x in ci) and ci[0]>0)
    stable_leagues=sum(n>=40 for n in leaguecounts.values())
    # Structural research-ledger validation is not authenticated outcome
    # admission. No source-proof admission route exists in this pipeline yet.
    # Keep archive coverage visible without satisfying formal qualifications.
    qualification_counts = {
        "legacy_counts_are_unverified_research": True,
        "recorded_research_samples": len(rows),
        "recorded_research_week_blocks": len(weeks),
        "recorded_research_leagues_with_40": stable_leagues,
        "authenticated_forward_samples": 0,
        "authenticated_week_blocks": 0,
        "authenticated_leagues_with_40": 0,
        "remaining_authenticated_samples": MIN_SAMPLES,
        "remaining_authenticated_weeks": MIN_WEEKS,
        "remaining_authenticated_leagues": MIN_LEAGUES,
        "authenticated_forward_admission_implemented": False,
        "qualification_counts_authenticated": False,
    }
    conditions={
        "at_least_300_settled_point_in_time_samples":False,
        "at_least_12_independent_week_blocks":False,
        "at_least_four_leagues_with_40_completed_samples":False,
        "positive_week_block_bootstrap_lower_ci_against_market":bool(positive_ci),
        "independent_six_league_result_verification":
            center.get("six_league_result_verification_complete") is True,
        "independently_attested_original_forecast_archive":
            validation.get("immutable_forecast_evidence_verified") is True,
        "market_quotes_are_legally_executable_at_recommendation_time":
            center.get("market_odds_are_executable") is True,
        # There is no such thing as a guaranteed future betting ROI.
        # Never equate a self-reported guarantee to independently audited,
        # timestamped paper ROI/CLV evidence.
        "positive_risk_adjusted_roi_and_clv_independently_tested":
            (center.get("risk_adjusted_roi_and_clv_independently_verified") is True
             and center.get("guaranteed_positive_roi") is not True),
        "independent_manual_research_approval":False,
    }
    failures=[name for name,ok in conditions.items() if not ok]
    return {
        "schema":"football-king-production-qualification-1",
        **qualification_counts,
        "status":"HOLD",
        "reason":failures[0] if failures else "REQUIRES_MANUAL_RISK_REVIEW",
        "conditions":conditions,
        "failed_conditions":failures,
        "blockers":["AUTHENTICATED_FORWARD_ADMISSION_NOT_IMPLEMENTED"],
        # Legacy fields describe the unverified archive, not qualification.
        "settled_samples":len(rows),
        "week_blocks":len(weeks),
        "qualifying_leagues":stable_leagues,
        "validation_progress": {
            **qualification_counts,
            # These legacy *validation* fields now express formal eligibility.
            # Research coverage is preserved in recorded_research_* above.
            "settled_samples": 0,
            "minimum_required": MIN_SAMPLES,
            "additional_samples_needed": MIN_SAMPLES,
            "independent_week_blocks": 0,
            "minimum_week_blocks": MIN_WEEKS,
            "additional_week_blocks_needed": MIN_WEEKS,
            "leagues_with_at_least_40": 0,
            "required_leagues_with_at_least_40": MIN_LEAGUES,
            "per_league_settled": {league: leaguecounts.get(league, 0) for league in
                                   ("epl","championship","bundesliga","laliga","seriea","ligue1")},
            "result_rows_marked_independently_verified": sum(
                row.get("fixture_result_source_independently_verified") is True
                for row in rows),
            "independently_verified_result_count": 0,
            "sample_numbers_cannot_certify_profitability": True,
        },
        "ready_for_independent_review":False,
        "guaranteed_future_roi_is_not_a_qualifying_claim":True,
        "model_promoted":False,
        "automated_release_supported":False,
        "production_recommendations":"DISABLED",
        "warning":"Passing technical tests or observing paper performance never turns on betting picks.",
    }


def publish(site,evidence):
    site=Path(site)
    center=json.loads((site/"research_center.json").read_text(encoding="utf-8"))
    validation=json.loads((site/"validation.json").read_text(encoding="utf-8"))
    payload=json.loads(Path(evidence).read_text(encoding="utf-8"))
    result=gate(center,payload,validation)
    (site/"production_gate.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--site",default="app/site")
    parser.add_argument("--evidence",default="settled-next.json")
    args=parser.parse_args()
    gate_result=publish(args.site,args.evidence)
    print(json.dumps({"status":gate_result["status"],
        "reason":gate_result["reason"],"settled_samples":gate_result["settled_samples"],
        "failed_conditions":gate_result["failed_conditions"],
        "production_recommendations":"DISABLED"},ensure_ascii=False))
