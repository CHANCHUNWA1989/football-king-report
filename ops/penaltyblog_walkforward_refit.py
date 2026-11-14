"""Prospective-style expanding walk-forward refits using optional penaltyblog.

All forecasts are regenerated from historical matches available before each
fixture's cutoff. No network, real source attestation or production picks.
"""
import argparse
import json
from datetime import datetime, timezone
from .penaltyblog_research_bridge import SCHEMA, evaluate, _timestamp, _id


def _hold(reason, **extra):
    return {"status": "HOLD", "reason": reason, "production_recommendations": "DISABLED",
            "positive_ev_verified": False, "model_promoted": False,
            "independent_provenance_verified": False, **extra}


def refit_walkforward(payload, *, model_factory=None):
    if not isinstance(payload, dict) or set(payload) != {
        "schema", "production_recommendations", "model", "historical_matches",
        "targets", "min_training"
    } or payload.get("schema") != "football-king-penaltyblog-walkforward-v1" or payload.get("production_recommendations") != "DISABLED":
        return _hold("INVALID_CONTRACT")
    if payload.get("model") not in ("poisson", "dixon_coles"):
        return _hold("INVALID_MODEL")
    min_training = payload["min_training"]
    if type(min_training) is not int or not 30 <= min_training <= 2500:
        return _hold("INVALID_MIN_TRAINING")
    history, targets = payload["historical_matches"], payload["targets"]
    if not isinstance(history, list) or not isinstance(targets, list) or not 1 <= len(targets) <= 250:
        return _hold("INVALID_COHORT")
    if len(history) > 2500:
        return _hold("HISTORY_TOO_LARGE")
    try:
        keys = set()
        for row in history:
            if not isinstance(row, dict) or set(row) != {
                "source_namespace", "event_id", "league_id", "home_team_id",
                "away_team_id", "kickoff_utc", "result_recorded_utc",
                "home_goals", "away_goals"
            }:
                raise ValueError("INVALID_HISTORY_ROW")
            key = (row["source_namespace"], row["event_id"])
            if key in keys:
                raise ValueError("DUPLICATE_EVENT")
            keys.add(key)
            if not _timestamp(row["kickoff_utc"]) < _timestamp(row["result_recorded_utc"]):
                raise ValueError("INVALID_HISTORY_CHRONOLOGY")
        prior_time = None
        target_keys = set()
        predictions = []
        for target in targets:
            if not isinstance(target, dict) or set(target) != {
                "source_namespace", "event_id", "league_id", "home_team_id",
                "away_team_id", "kickoff_utc", "as_of_utc"
            }:
                raise ValueError("INVALID_TARGET_ROW")
            kickoff, cutoff = _timestamp(target["kickoff_utc"]), _timestamp(target["as_of_utc"])
            if not cutoff < kickoff or (prior_time is not None and kickoff < prior_time):
                raise ValueError("TARGET_ORDER_OR_LOOKAHEAD")
            prior_time = kickoff
            key = (target["source_namespace"], target["event_id"])
            if key in target_keys or key in keys:
                raise ValueError("DUPLICATE_OR_OVERLAPPING_TARGET")
            target_keys.add(key)
            eligible = [row for row in history
                        if row["source_namespace"] == target["source_namespace"]
                        and row["league_id"] == target["league_id"]
                        and _timestamp(row["result_recorded_utc"]) < cutoff]
            eligible.sort(key=lambda row: (_timestamp(row["kickoff_utc"]), row["event_id"]))
            if len(eligible) < min_training:
                return _hold("INSUFFICIENT_AVAILABLE_HISTORY", blocked_target=target["event_id"],
                             available_history=len(eligible))
            if len(eligible) > 2500:
                eligible = eligible[-2500:]
            fit_payload = {
                "schema": SCHEMA, "production_recommendations": "DISABLED",
                "as_of_utc": target["as_of_utc"], "model": payload["model"],
                "target_fixture": {k: target[k] for k in (
                    "source_namespace", "event_id", "league_id", "home_team_id",
                    "away_team_id", "kickoff_utc")},
                "historical_matches": eligible,
            }
            result = evaluate(fit_payload, model_factory=model_factory)
            if result["status"] != "RESEARCH_ONLY":
                return _hold("REFIT_FAILED_OR_INVALID_TRAINING",
                             blocked_target=target["event_id"], model_reason=result.get("reason"))
            predictions.append({
                "fixture_id": target["event_id"], "kickoff_utc": target["kickoff_utc"],
                "as_of_utc": target["as_of_utc"], "model_id": result["model_id"],
                "training_match_count": result["training_match_count"],
                "probabilities": [result["p_home"], result["p_draw"], result["p_away"]],
                "source_authenticity_verified": False,
                "independently_timestamped": False,
            })
        return _hold("PROSPECTIVE_SOURCE_AND_RESULT_ATTESTATION_MISSING",
                     refit_count=len(predictions), predictions=predictions,
                     note="Each target was refitted using only earlier recorded results; model probabilities are unverified research diagnostics.")
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        return _hold(str(exc))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    with open(args.input, encoding="utf-8") as f:
        payload = json.load(f)
    print(json.dumps(refit_walkforward(payload), indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
