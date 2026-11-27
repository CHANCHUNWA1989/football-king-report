"""Offline postmortem diagnostics. No live feed, calibration or promotion.

Remaining-goal rates and card multipliers are explicitly hypothetical inputs,
not parameters inferred from the Brentford/Everton result. A caller's source
labels are not proof of independent verification.
"""
import math
from datetime import datetime
from ops.asian_handicap_research import grade
from ops.live_market_research import payout

FLAGS = {"status": "HOLD", "production_recommendations": "DISABLED",
         "promotion_allowed": False, "calibrated": False}

def _number(value, lo, hi):
    if type(value) not in (float, int) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError("INVALID_NUMERIC_INPUT")
    return float(value)

def _score(h, a):
    if any(type(v) is not int or not 0 <= v <= 25 for v in (h, a)):
        raise ValueError("INVALID_SCORE")

def _weights(rate):
    p = math.exp(-rate)
    result = [p]
    for i in range(1, 61):
        p *= rate / i
        result.append(p)
    return result

def _distribution(h, a, rh, ra):
    out = [0.0, 0.0, 0.0]
    for i, x in enumerate(_weights(rh)):
        for j, y in enumerate(_weights(ra)):
            margin = h+i-a-j
            out[0 if margin > 0 else 1 if margin == 0 else 2] += x*y
    total = sum(out)
    return [v/total for v in out]

def card_sensitivity(*, home_goals, away_goals, minute, home_remaining,
                     away_remaining, card_side, official_card_side,
                     independent_card_side, official_source, independent_source,
                     disadvantaged_factor, opponent_factor):
    """Same-score counterfactual, NOT a chronological match reconstruction.

    Caller must pass remaining (not full-game) goal rates. Conflicting or
    absent observations fail closed. Labels alone do not attest authenticity.
    """
    _score(home_goals, away_goals)
    minute = _number(minute, 0, 90)
    rh, ra = (_number(x, 0, 8) for x in (home_remaining, away_remaining))
    down = _number(disadvantaged_factor, 0, 1)
    up = _number(opponent_factor, 1, 2)
    out = dict(FLAGS, source_authenticity_verified=False,
               assumptions_only=True, comparison=None)
    if (card_side not in ("HOME", "AWAY") or
            official_card_side != card_side or independent_card_side != card_side or
            not all(isinstance(x, str) and x.strip() for x in
                    (official_source, independent_source)) or
            official_source.strip().casefold() == independent_source.strip().casefold()):
        return dict(out, reason="CARD_EVIDENCE_MISSING_OR_CONFLICTING")
    if minute == 90:
        return dict(out, reason="END_OF_REGULATION")
    post_h, post_a = (rh*down, ra*up) if card_side == "HOME" else (rh*up, ra*down)
    # Only the opponent rate is increased. Reject actual adjusted overflow,
    # not a hypothetical increase applied to the disadvantaged side.
    if max(post_h, post_a) > 8:
        return dict(out, reason="ADJUSTED_RATE_OUT_OF_RANGE")
    return dict(out, reason="HYPOTHETICAL_CARD_SENSITIVITY_ONLY",
                comparison={"same_score_no_card": _distribution(home_goals, away_goals, rh, ra),
                            "same_score_card": _distribution(home_goals, away_goals, post_h, post_a)})

def settlement_consistency(h, a, side, line, decimal_price):
    """Compare the existing grade and payout engines without recommending."""
    category = grade(h, a, side, line)
    value = payout({"kind": "handicap", "side": side.lower(),
                    "line": line, "odds": decimal_price}, h, a)
    expected = {"FULL_WIN": decimal_price-1, "HALF_WIN": (decimal_price-1)/2,
                "PUSH": 0, "HALF_LOSS": -.5, "FULL_LOSS": -1}[category]
    if not math.isclose(value, expected, rel_tol=0, abs_tol=1e-12):
        raise ValueError("SETTLEMENT_ENGINE_DISAGREEMENT")
    return category, value

def _time(s):
    if not isinstance(s, str):
        raise ValueError("INVALID_TIMESTAMP")
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return t

def _probabilities(p):
    if not isinstance(p, (list, tuple)) or len(p) != 3:
        raise ValueError("INVALID_PROBABILITIES")
    q = [_number(x, 0, 1) for x in p]
    if abs(sum(q)-1) > 1e-8:
        raise ValueError("INVALID_PROBABILITY_SUM")
    return q

def paired_diagnostic(rows):
    """Paired Brier comparison, with strict declared chronology.

    Does not authenticate archives or prove out-of-sample status. No
    reconstruction of missing predictions, duplicate fixture IDs or
    tuning on results. A separate sealed cohort audit remains mandatory.
    """
    seen = set()
    deltas = []
    for row in rows:
        fixture = row["fixture_id"]
        if not isinstance(fixture, str) or not fixture.strip() or fixture in seen:
            raise ValueError("DUPLICATE_OR_INVALID_FIXTURE")
        seen.add(fixture)
        cutoff, stamp, observed = (_time(row[k]) for k in
                                   ("training_cutoff", "prediction_time", "result_time"))
        if not cutoff < stamp < observed:
            raise ValueError("TEMPORAL_LEAKAGE")
        y = row["outcome"]
        if type(y) is not int or not 0 <= y <= 2:
            raise ValueError("INVALID_OUTCOME")
        p, q = (_probabilities(row[k]) for k in ("baseline", "challenger"))
        def brier(v):
            return sum((x-(i == y))**2 for i, x in enumerate(v))
        deltas.append(brier(q)-brier(p))
    return dict(FLAGS, n=len(deltas), archives_authenticated=False,
                out_of_sample_proven=False, confidence_interval=None,
                mean_paired_brier_delta=sum(deltas)/len(deltas) if deltas else None)
