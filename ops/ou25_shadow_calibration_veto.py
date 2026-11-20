"""Offline OU2.5 challenger validation (research only, no market/pricing claims).

Validation-period outcomes MAY fit a regularised logit intercept. Held-out
outcomes are used ONLY for scoring, never for model selection, refitting, or
original-model modification. Chronology and metadata are self-reported:
passing structural checks is NOT independent pre-kickoff attestation.
"""
import argparse
from datetime import date
import json
import math
from pathlib import Path
import re

SCHEMA = "football-king-ou25-shadow-veto-v1"
MIN_VALIDATION = 80
MIN_HELDOUT = 80
REGULARIZATION = 25.0


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("INVALID_DATE")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("INVALID_DATE") from exc


def _probability(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value < 1:
        raise ValueError("INVALID_PROBABILITY")
    return float(value)


def _rows(rows, name):
    if not isinstance(rows, list) or not 80 <= len(rows) <= 30000:
        raise ValueError("INVALID_" + name + "_SIZE")
    seen = set()
    out = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("INVALID_SAMPLE")
        league, key = row.get("league"), row.get("fixture_id")
        if (not isinstance(league, str) or not league.strip()
                or not isinstance(key, str) or not key.strip()):
            raise ValueError("INVALID_FIXTURE_ID")
        ident = (league, key)
        if ident in seen:
            raise ValueError("DUPLICATE_FIXTURE_ID")
        seen.add(ident)
        d = _day(row.get("match_date"))
        p = _probability(row.get("original_over25_probability"))
        y = row.get("actual_over25")
        if type(y) is not int or y not in (0, 1):
            raise ValueError("INVALID_ACTUAL_OVER25")
        out.append((ident, d, p, y))
    return out


def _logit(p):
    return math.log(p / (1.0 - p))


def _sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    q = math.exp(z)
    return q / (1.0 + q)


def _fit(validation):
    """Unique, L2-regularised intercept; no access to any held-out label."""
    intercept = 0.0
    for _ in range(50):
        gradient = -REGULARIZATION * intercept
        curvature = REGULARIZATION
        for _, _, probability, actual in validation:
            q = _sigmoid(_logit(probability) + intercept)
            gradient += actual - q
            curvature += q * (1 - q)
        step = gradient / curvature
        intercept += step
        if abs(step) < 1e-12:
            break
    return intercept


def _score(rows, transform):
    brier = logloss = 0.0
    for _, _, p, y in rows:
        q = min(1 - 1e-15, max(1e-15, transform(p)))
        brier += (q - y) ** 2
        logloss -= y * math.log(q) + (1 - y) * math.log(1 - q)
    return {"brier": round(brier / len(rows), 8),
            "logloss": round(logloss / len(rows), 8)}


def audit(validation_rows, heldout_rows, *, baseline, source_revision):
    """Never authorise promotion, even when a descriptive metric improves."""
    if not isinstance(source_revision, str) or not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        raise ValueError("INVALID_SOURCE_REVISION")
    validation = _rows(validation_rows, "VALIDATION")
    heldout = _rows(heldout_rows, "HELDOUT")
    if {x[0] for x in validation} & {x[0] for x in heldout}:
        raise ValueError("OVERLAPPING_FIXTURES")
    if max(x[1] for x in validation) >= min(x[1] for x in heldout):
        raise ValueError("VALIDATION_NOT_STRICTLY_BEFORE_HELDOUT")
    if not isinstance(baseline, dict):
        raise ValueError("MISSING_TRAINING_BASELINE")
    prior = _probability(baseline.get("probability_over25"))
    cutoff = _day(baseline.get("training_end_date"))
    if cutoff >= min(x[1] for x in heldout):
        raise ValueError("BASELINE_NOT_BEFORE_HELDOUT")
    if (type(baseline.get("sample_count")) is not int
            or baseline["sample_count"] < 30
            or not isinstance(baseline.get("source"), str)
            or not baseline["source"].strip()):
        raise ValueError("INVALID_TRAINING_BASELINE_PROVENANCE")

    shift = _fit(validation)
    original = _score(heldout, lambda p: p)
    challenger = _score(heldout, lambda p: _sigmoid(_logit(p) + shift))
    constant = _score(heldout, lambda p: prior)
    improved = challenger["brier"] < original["brier"]
    outperform_baseline = challenger["brier"] < constant["brier"]
    return {
        "schema": SCHEMA,
        "source_revision_self_reported": source_revision,
        "validation_count": len(validation),
        "heldout_count": len(heldout),
        "validation_last_date": str(max(x[1] for x in validation)),
        "heldout_first_date": str(min(x[1] for x in heldout)),
        "baseline_training_end_date": str(cutoff),
        "regularization": REGULARIZATION,
        "fitted_validation_only_logit_shift": round(shift, 8),
        "original": original,
        "challenger": challenger,
        "training_only_constant_baseline": constant,
        "challenger_brier_better_than_original": improved,
        "challenger_brier_better_than_constant_baseline": outperform_baseline,
        "research_veto": ("REJECT_WORSE_THAN_ORIGINAL" if not improved
                          else "HOLD_INDEPENDENT_FORWARD_ATTESTATION_REQUIRED"),
        "historical_date_split_not_signed_prematch": True,
        "source_and_result_independently_authenticated": False,
        "market_odds_available": False,
        "betting_ev_verified": False,
        "original_sealed_forecasts_modified": False,
        "production_recommendations": "DISABLED",
        "status": "HOLD",
        "eligible_for_promotion": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation", required=True)
    parser.add_argument("--heldout", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    def read(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))
    report = audit(read(args.validation), read(args.heldout),
                   baseline=read(args.baseline), source_revision=args.source_revision)
    dest = Path(args.output)
    if dest.exists() or dest.is_symlink():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print("OU25_SHADOW_RESEARCH", report["research_veto"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
