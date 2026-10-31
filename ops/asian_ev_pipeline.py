"""Research-only orchestration; never emits production betting recommendations."""
from math import isfinite
from ops.asian_ev_quote_gate import assess_quote
from ops.asian_ev_quote_provenance import research_evidence_record
from ops.asian_ev_research import expected_value

PRODUCTION_RECOMMENDATIONS = "DISABLED"


def evaluate_research_quote(quote, *, now_utc, kickoff_utc, probabilities, line):
    """Fail closed unless quote eligibility, evidence and EV computation succeed."""
    result = {"status": "HOLD", "production_recommendations": PRODUCTION_RECOMMENDATIONS}
    gate = assess_quote(quote, now_utc=now_utc, kickoff_utc=kickoff_utc)
    if not gate["eligible_for_research"]:
        return {**result, "reasons": gate["reasons"]}
    if type(line) not in (int, float) or not isfinite(line):
        return {**result, "reasons": ["INVALID_LINE"]}
    try:
        evidence = research_evidence_record(quote)
        ev = expected_value(probabilities, line, quote["decimal_odds"])
        if not isfinite(ev):
            raise ValueError("NONFINITE_EV")
    except (ValueError, TypeError, OverflowError) as exc:
        return {**result, "reasons": ["RESEARCH_INPUT_REJECTED"], "detail": str(exc)}
    return {**result, "status": "RESEARCH_ONLY", "reasons": ["UNVERIFIED_SOURCE_AND_MODEL"],
            "quote_sha256": evidence["sha256"], "research_ev": ev}
