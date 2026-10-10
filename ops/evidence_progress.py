"""Audit missing independent evidence before any Football King recommendation.

Consumes ONLY the already-produced, fail-closed daily research reports. Never
merges 2025 historical replay into genuine prospective 2026 samples. The
public output contains coverage metrics and blockers, not bookmaker quotes.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "football-king-evidence-progress-v1"
TARGET_SAMPLES = 300
TARGET_WEEKS = 12
TARGET_LEAGUES = 4


def nonnegative(value):
    return value if type(value) is int and 0 <= value <= 100000 else 0


def valid(source, schema):
    return (isinstance(source, dict)
            and source.get("schema") == schema
            and source.get("production_recommendations") == "DISABLED")


def measure(center, gate, scores, handicap, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_AUDIT_CLOCK")
    result = {
        "schema": SCHEMA, "checked_utc": now.isoformat(),
        "status": "HOLD", "production_recommendations": "DISABLED",
        "model_ready_for_production": False,
        "positive_ev_betting_confirmed": False,
        "automatic_bets_allowed": False,
        "market_confidence_probabilities_are_not_executable_prices": True,
        "historical_simulation_not_counted_as_forward_validation": True,
        "required_prospective_samples": TARGET_SAMPLES,
        "required_calendar_week_blocks": TARGET_WEEKS,
        "required_leagues_with_40_samples": TARGET_LEAGUES,
        "settled_forward_samples": 0,
        "remaining_forward_samples": TARGET_SAMPLES,
        "independent_week_blocks": 0, "remaining_week_blocks": TARGET_WEEKS,
        "leagues_with_40_forward_samples": 0,
        "independent_exact_score_pairs_on_settled_samples": 0,
        "two_publisher_bundesliga_outcome_correlations_research_only": 0,
        "two_publisher_bundesliga_outcome_conflicts_research_only": 0,
        "two_publisher_correlations_are_not_certified_results": True,
        "asian_actual_verified_spread_quotes": 0,
        "asian_pre_match_paper_settlements": 0,
        "model_market_comparable_cases": 0,
        "missing_evidence": [],
    }
    gate_ok=valid(gate,"football-king-production-qualification-1")
    center_ok=valid(center,"football-king-research-center-1")
    score_ok=valid(scores,"football-king-independent-final-score-audit-v1")
    asian_ok=valid(handicap,"football-king-asian-spread-forward-paper-audit-v1")
    if gate_ok:
        result["settled_forward_samples"]=nonnegative(gate.get("settled_samples"))
        result["remaining_forward_samples"]=max(0,TARGET_SAMPLES-result["settled_forward_samples"])
        result["independent_week_blocks"]=nonnegative(gate.get("week_blocks"))
        result["remaining_week_blocks"]=max(0,TARGET_WEEKS-result["independent_week_blocks"])
        result["leagues_with_40_forward_samples"]=nonnegative(gate.get("qualifying_leagues"))
        result["missing_evidence"]=list(gate.get("failed_conditions", []))[:40]
    else:
        result["missing_evidence"].append("NO_VERIFIED_PRODUCTION_GATE_REPORT")
    if center_ok:
        result["model_market_comparable_cases"]=nonnegative(center.get("total_strict_market_pairs"))
    else:
        result["missing_evidence"].append("NO_TRUSTED_MODEL_MARKET_STATUS")
    if score_ok:
        result["independent_exact_score_pairs_on_settled_samples"]=nonnegative(
            scores.get("two_provider_exact_score_agreements"))
        # A second public publisher agreeing with the outcome is useful
        # *research correlation*, not authenticated 90-minute result proof
        # or a valid additional sealed forecast. Report separately.
        candidates = scores.get("bundesliga_two_publisher_candidate_audit")
        if (isinstance(candidates, dict)
                and candidates.get("status") == "CANDIDATE_CORRELATION_ONLY"
                and candidates.get("results_cryptographically_attested") is False
                and candidates.get("forward_predictions_independently_validated") is False):
            matches = nonnegative(candidates.get("settled_outcomes_correlated"))
            conflicts = nonnegative(candidates.get("settled_outcome_conflicts"))
            if matches + conflicts <= result["settled_forward_samples"]:
                result["two_publisher_bundesliga_outcome_correlations_research_only"] = matches
                result["two_publisher_bundesliga_outcome_conflicts_research_only"] = conflicts
        if result["independent_exact_score_pairs_on_settled_samples"] == 0:
            result["missing_evidence"].append("NO_EXACT_TWO_PUBLISHER_SETTLED_FT_RESULT")
    else:
        result["missing_evidence"].append("NO_TRUSTED_TWO_PUBLISHER_SCORE_AUDIT")
    if asian_ok:
        result["asian_pre_match_paper_settlements"]=nonnegative(
            handicap.get("qualified_pre_match_quote_count"))
        # Paper odds, irrespective of theoretical profit, cannot become a
        # legally authenticated executable bookmaker price.
        if handicap.get("licensed_executable_prices_confirmed") is not False:
            result["missing_evidence"].append("UNSAFE_ASIAN_PROVENANCE_CLAIM")
    else:
        result["missing_evidence"].append("NO_TRUSTED_ASIAN_FORWARD_AUDIT")
    result["missing_evidence"].append("NO_LICENSED_EXECUTABLE_ASIAN_QUOTE_AT_BET_TIME")
    result["missing_evidence"].append("NO_CALIBRATED_JAPAN_1X2_OR_ASIAN_HANDICAP_MODEL")
    result["missing_evidence"]=sorted(set(result["missing_evidence"]))
    result["audit_status"]="RESEARCH_EVIDENCE_GAP_TRACKING_ONLY"
    return result


def publish(site):
    root=Path(site)
    def read(name):
        p=root/name
        try:
            if p.stat().st_size > 2_000_000:
                return None
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return None
    outcome=measure(
        read("research_center.json"), read("production_gate.json"),
        read("independent_results.json"), read("handicap_forward_audit.json"))
    root.mkdir(parents=True, exist_ok=True)
    (root/"evidence_progress.json").write_text(
        json.dumps(outcome,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:outcome[k] for k in (
        "status","settled_forward_samples","remaining_forward_samples",
        "independent_exact_score_pairs_on_settled_samples",
        "asian_pre_match_paper_settlements",
        "production_recommendations")},ensure_ascii=False))
    return outcome


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--site",default="app/site")
    a=p.parse_args()
    publish(a.site)
