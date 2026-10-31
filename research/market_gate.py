"""Research-only market gate. Never grants production betting permission."""
from dataclasses import dataclass
from math import isfinite

@dataclass(frozen=True)
class GateResult:
    status: str
    reasons: tuple[str, ...]
    certified_positive_ev: bool = False
    production_recommendations: str = "DISABLED"

def evaluate_research_market(*, reference_price, minimum_price, probability_range,
                             quote_executable=False, quote_timestamp=None,
                             calibrated=False, official_sealed_prediction=False):
    """Fail closed; archived references and uncalibrated models cannot certify EV."""
    reasons = []
    if not official_sealed_prediction:
        reasons.append("NOT_OFFICIAL_SEALED_PREDICTION")
    if reference_price is None or not isinstance(reference_price, (int, float)) or not isfinite(reference_price) or reference_price <= 1:
        reasons.append("NO_VALID_PRICE")
    if minimum_price is not None and (reference_price is None or reference_price < minimum_price):
        reasons.append("BELOW_RECONSIDERATION_THRESHOLD")
    if not quote_executable or not quote_timestamp:
        reasons.append("NO_TIMESTAMPED_EXECUTABLE_QUOTE")
    if not calibrated:
        reasons.append("UNCALIBRATED_PROBABILITIES")
    if (not isinstance(probability_range, (list, tuple)) or len(probability_range) != 2
            or any(not isinstance(p, (int, float)) or not isfinite(p) or p < 0 or p > 100 for p in probability_range)):
        reasons.append("INVALID_PROBABILITY_RANGE")
    elif probability_range[1] < probability_range[0]:
        reasons.append("REVERSED_PROBABILITY_RANGE")
    elif probability_range[1] - probability_range[0] >= 10:
        reasons.append("MODEL_DISAGREEMENT_10PP")
    # This gate never approves a bet; passing preconditions requires separate
    # audited EV and authorization logic which is intentionally not implemented.
    return GateResult("HOLD", tuple(reasons) or ("REQUIRES_INDEPENDENT_EV_CERTIFICATION",))
