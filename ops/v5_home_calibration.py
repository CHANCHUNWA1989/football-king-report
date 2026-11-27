"""V5.0 first challenger: regularized home-logit and temperature calibration.

Research-only. The archived outcomes lack independent authentication and
per-result availability clocks. Chronological replay is NOT prospective validation.
No production promotion, odds, stake or modification of sealed A/B/C forecasts.
"""
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from ops.model_market_bias_audit import audit, _instant, _vector, _score, LEAGUES

MODEL_ID = "v5-home-logit-temperature-grid-v1"
SHIFTS = tuple(i / 10 for i in range(-8, 9))
TEMPERATURES = (0.75, 0.9, 1.0, 1.1, 1.25, 1.5)
MIN_TRAIN = 40
MIN_TEST = 20

def calibrate(p, shift, temperature):
    p = _vector(p)
    if shift not in SHIFTS or temperature not in TEMPERATURES:
        raise ValueError("UNKNOWN_GRID_PARAMETER")
    logits = [(math.log(max(v, 1e-15)) + (shift if i == 0 else 0)) / temperature
              for i, v in enumerate(p)]
    largest = max(logits)
    q = [math.exp(v - largest) for v in logits]
    return [v / sum(q) for v in q]

def fit(rows):
    if len(rows) < MIN_TRAIN:
        raise ValueError("INSUFFICIENT_TRAINING")
    def loss(shift, temp):
        return (sum(_score(calibrate(r["p"], shift, temp), r["y"])[0]
                    for r in rows) / len(rows)
                + .025 * (shift ** 2 + math.log(temp) ** 2))
    shift, temp = min(((s, t) for s in SHIFTS for t in TEMPERATURES),
                      key=lambda st: (loss(*st), abs(st[0]), abs(st[1]-1), st))
    return {"home_logit_shift": shift, "temperature": temp}

def metrics(rows, params=None, market=False):
    if not rows:
        return None
    scores, hits, home_top, home_prob = [], 0, 0, 0.0
    for r in rows:
        p = (_vector(r["m"]) if market else
             calibrate(r["p"], params["home_logit_shift"], params["temperature"])
             if params else _vector(r["p"]))
        scores.append(_score(p, r["y"]))
        pick = max(range(3), key=lambda i: p[i])
        hits += pick == r["y"]
        home_top += pick == 0
        home_prob += p[0]
    n = len(rows)
    return {"n": n, "log_loss": round(sum(x[0] for x in scores)/n, 7),
            "brier": round(sum(x[1] for x in scores)/n, 7),
            "correct": hits, "home_top_count": home_top,
            "mean_home_probability": round(home_prob/n, 7),
            "actual_home_count": sum(r["y"] == 0 for r in rows)}

def build(evidence):
    if (not isinstance(evidence, dict)
            or evidence.get("schema") != "football-king-forward-research-1"
            or evidence.get("production_recommendations") != "DISABLED"
            or not isinstance(evidence.get("samples"), list)
            or type(evidence.get("n")) is not int
            or evidence["n"] != len(evidence["samples"])):
        raise ValueError("INVALID_EVIDENCE")
    cutoff = _instant(evidence.get("checked_utc"))
    rows = evidence["samples"]
    audit(rows, archived_at_utc=evidence["checked_utc"])
    digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":"),
                                      allow_nan=False).encode()).hexdigest()
    result = {"schema": "football-king-v5-calibration-research-v1",
              "model_id": MODEL_ID, "status": "HOLD", "archive_checked_utc": cutoff.isoformat(),
              "archive_sha256": digest, "n": len(rows), "training_model": None,
              "retrospective_split": None, "independently_verified_results": False,
              "point_in_time_training_verified": False, "prospective_validation": False,
              "production_recommendations": "DISABLED", "automatic_promotion": False,
              "betting_ev_verified": False}
    if len(rows) < MIN_TRAIN + MIN_TEST:
        result["reason"] = "INSUFFICIENT_ARCHIVE"
        return result
    # Hold out complete ISO weeks. Never tune on the held-out outcomes.
    weeks = sorted({_instant(r["kickoff_utc"]).strftime("%G-W%V") for r in rows})
    if len(weeks) < 3:
        result["reason"] = "INSUFFICIENT_WEEK_BLOCKS"
        return result
    split = weeks[max(1, min(len(weeks)-1, len(weeks)*2//3))]
    train = [r for r in rows if _instant(r["kickoff_utc"]).strftime("%G-W%V") < split]
    test = [r for r in rows if _instant(r["kickoff_utc"]).strftime("%G-W%V") >= split]
    if len(train) < MIN_TRAIN or len(test) < MIN_TEST:
        result["reason"] = "INSUFFICIENT_SPLIT"
        return result
    parameters = fit(train)
    result["retrospective_split"] = {
        "first_test_week": split, "train_n": len(train), "test_n": len(test),
        "parameters": parameters, "baseline": metrics(test),
        "candidate": metrics(test, parameters), "market": metrics(test, market=True),
        "qualification": "RETROSPECTIVE_ONLY_OUTCOME_AVAILABILITY_UNVERIFIED"}
    # Separate full-archive fit for future observations; no claim of improvement.
    result["training_model"] = fit(rows)
    result["status"] = "RESEARCH_ONLY"
    result["reason"] = "FUTURE_INDEPENDENT_VALIDATION_REQUIRED"
    return result

def forecast(evidence, row, now=None):
    """New forecast only: current runtime, strictly future kickoff, same base model.
    The full archive is revalidated; caller cannot supply self-certified parameters.
    This is an unsealed, unauthenticated research output, not a live recommendation.
    """
    report = build(evidence)
    now = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("INVALID_RUNTIME_CLOCK")
    now = now.astimezone(timezone.utc)
    if report["training_model"] is None:
        raise ValueError("NO_TRAINED_CANDIDATE")
    if (not isinstance(row, dict) or row.get("production_recommendations") != "DISABLED"
            or row.get("model") != "poisson-shrinkage-unvalidated-v4.1"
            or row.get("league") not in LEAGUES
            or not isinstance(row.get("event_id"), str) or not row["event_id"].strip()
            or any(row.get(k) is not None for k in ("y", "score_ft", "result", "historical_outcome"))
            or row.get("status", "SCHEDULED") != "SCHEDULED"):
        raise ValueError("INVALID_BASE_FORECAST")
    source = _instant(row.get("prediction_utc"))
    kickoff = _instant(row.get("kickoff_utc"))
    if not (_instant(report["archive_checked_utc"]) < source <= now < kickoff
            and (now-source).total_seconds() <= 3600
            and (kickoff-now).total_seconds() > 600):
        raise ValueError("UNSAFE_FORECAST_CLOCK")
    p = [row.get(k) for k in ("p_home", "p_draw", "p_away")]
    params = report["training_model"]
    return {"schema": "football-king-v5-calibrated-shadow-v1", "model_id": MODEL_ID,
            "event_id": row["event_id"], "league": row["league"], "kickoff_utc": kickoff.isoformat(),
            "prediction_utc": now.isoformat(), "source_prediction_utc": source.isoformat(),
            "archive_sha256": report["archive_sha256"], "parameters": params,
            "p": calibrate(p, params["home_logit_shift"], params["temperature"]),
            "status": "RESEARCH_ONLY", "independently_verified": False,
            "production_recommendations": "DISABLED"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--base-forecast")
    a = ap.parse_args()
    evidence = json.loads(Path(a.evidence).read_text())
    out = (forecast(evidence, json.loads(Path(a.base_forecast).read_text()))
           if a.base_forecast else build(evidence))
    Path(a.output).write_text(json.dumps(out, indent=2, allow_nan=False)+"\n")
    print(json.dumps(out, allow_nan=False))

if __name__ == "__main__":
    main()
