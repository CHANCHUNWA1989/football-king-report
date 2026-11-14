"""Optional Penaltyblog Poisson/Dixon-Coles challenger for *offline* research.

No network or side effects. Caller-supplied history has NOT been independently
source-authenticated; outputs must never enter the existing sealed A/B/C ledger.
"""
import argparse
import json
import math
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "football-king-penaltyblog-offline-input-v1"
OUTPUT_SCHEMA = "football-king-penaltyblog-research-challenger-v1"
MIN_TRAINING = 30
MAX_TRAINING = 2500
MODELS = {"poisson": "PoissonGoalsModel", "dixon_coles": "DixonColesGoalModel"}
_MATCH_FIELDS = {"source_namespace", "event_id", "league_id", "home_team_id",
                 "away_team_id", "kickoff_utc", "result_recorded_utc", "home_goals", "away_goals"}
_TARGET_FIELDS = {"source_namespace", "event_id", "league_id", "home_team_id",
                  "away_team_id", "kickoff_utc"}


def _timestamp(raw):
    if not isinstance(raw, str) or not 1 <= len(raw) <= 64:
        raise ValueError("INVALID_TIMESTAMP")
    try:
        result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError("INVALID_TIMESTAMP")
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("INVALID_TIMESTAMP") from None


def _id(raw, *, namespace=False):
    if not isinstance(raw, str) or not 1 <= len(raw) <= 128 or raw != raw.strip():
        raise ValueError("INVALID_ID")
    if any(ord(c) < 32 or ord(c) == 127 for c in raw):
        raise ValueError("INVALID_ID")
    if namespace and not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", raw):
        raise ValueError("INVALID_SOURCE_NAMESPACE")
    return raw


def _fixture(row, fields):
    if not isinstance(row, dict) or set(row) != fields:
        raise ValueError("INVALID_FIXTURE_FIELDS")
    for key in ("event_id", "league_id", "home_team_id", "away_team_id"):
        _id(row[key])
    _id(row["source_namespace"], namespace=True)
    if row["home_team_id"] == row["away_team_id"]:
        raise ValueError("SAME_TEAM")
    return _timestamp(row["kickoff_utc"])


def _validate(payload):
    if (not isinstance(payload, dict)
            or set(payload) != {"schema", "production_recommendations", "as_of_utc",
                                "model", "target_fixture", "historical_matches"}
            or payload["schema"] != SCHEMA
            or payload["production_recommendations"] != "DISABLED"
            or payload["model"] not in MODELS):
        raise ValueError("INVALID_RESEARCH_CONTRACT")
    as_of = _timestamp(payload["as_of_utc"])
    target = payload["target_fixture"]
    kickoff = _fixture(target, _TARGET_FIELDS)
    if not as_of < kickoff:
        raise ValueError("TARGET_NOT_PREMATCH")
    rows = payload["historical_matches"]
    if not isinstance(rows, list) or not MIN_TRAINING <= len(rows) <= MAX_TRAINING:
        raise ValueError("INSUFFICIENT_OR_EXCESS_TRAINING")
    seen_event, seen_fixture = set(), set()
    counts = Counter()
    for row in rows:
        prior_kickoff = _fixture(row, _MATCH_FIELDS)
        if (row["source_namespace"] != target["source_namespace"]
                or row["league_id"] != target["league_id"]):
            raise ValueError("CROSS_SOURCE_OR_LEAGUE_MISMATCH")
        available = _timestamp(row["result_recorded_utc"])
        if not prior_kickoff < available < as_of:
            raise ValueError("LOOKAHEAD_OR_UNAVAILABLE_RESULT")
        key = (row["source_namespace"], row["event_id"])
        fixture_key = (row["home_team_id"], row["away_team_id"], prior_kickoff)
        if (key in seen_event or fixture_key in seen_fixture
                or row["event_id"] == target["event_id"]):
            raise ValueError("DUPLICATE_OR_TARGET_RESULT")
        seen_event.add(key)
        seen_fixture.add(fixture_key)
        for goal_key in ("home_goals", "away_goals"):
            if type(row[goal_key]) is not int or not 0 <= row[goal_key] <= 20:
                raise ValueError("INVALID_RESULT_SCORE")
        counts.update((row["home_team_id"], row["away_team_id"]))
    if any(counts[team] < 5 for team in (target["home_team_id"], target["away_team_id"])):
        raise ValueError("TARGET_TEAMS_NOT_TRAINED")
    return target, rows


def _hold(reason):
    return {"schema": OUTPUT_SCHEMA, "status": "HOLD", "reason": reason,
            "production_recommendations": "DISABLED", "positive_ev_verified": False,
            "model_promoted": False, "source_authenticity_verified": False,
            "prospective_capture_verified": False, "results_independently_verified": False}


def evaluate(payload, *, model_factory=None):
    """Train an optional research challenger; never output actionable odds/EV.

    model_factory is only for isolated tests; normal calls import penaltyblog.
    """
    try:
        target, rows = _validate(payload)
    except (ValueError, TypeError, OverflowError, KeyError):
        return _hold("INVALID_OR_UNVERIFIED_INPUT")
    if model_factory is None:
        try:
            from penaltyblog import models
            model_factory = getattr(models, MODELS[payload["model"]])
        except (ImportError, AttributeError):
            return _hold("OPTIONAL_PENALTYBLOG_NOT_INSTALLED")
    try:
        model = model_factory(
            [r["home_goals"] for r in rows], [r["away_goals"] for r in rows],
            [r["home_team_id"] for r in rows], [r["away_team_id"] for r in rows],
        )
        model.fit()
        grid = model.predict(target["home_team_id"], target["away_team_id"],
                             max_goals=15, normalize=True)
        probs = list(grid.home_draw_away)
        if (len(probs) != 3 or any(type(x) not in (int, float) or
                not math.isfinite(x) or not 0 <= x <= 1 for x in probs)
                or abs(sum(probs)-1) > 1e-6):
            raise ValueError("INVALID_PENALTYBLOG_PROBABILITIES")
    except Exception:
        return _hold("MODEL_FIT_OR_PREDICTION_FAILED")
    return {
        **_hold("RESEARCH_ONLY_UNVERIFIED_INPUT"), "status": "RESEARCH_ONLY",
        "model_id": f"penaltyblog-{payload['model']}-offline-challenger-v1",
        "dependency": "penaltyblog (optional; installed separately)",
        "fixture_id": target["event_id"], "source_namespace": target["source_namespace"],
        "league_id": target["league_id"], "as_of_utc": payload["as_of_utc"],
        "kickoff_utc": target["kickoff_utc"], "training_match_count": len(rows),
        "p_home": probs[0], "p_draw": probs[1], "p_away": probs[2],
        "is_sealed_original_forecast": False,
        "automatic_model_promotion": False,
    }


def _unique_json(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[k] = v
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Optional offline penaltyblog challenger")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if Path(args.input).resolve() == Path(args.output).resolve():
        raise ValueError("INPUT_OUTPUT_ALIAS")
    with open(args.input, encoding="utf-8") as fh:
        payload = json.load(fh, object_pairs_hook=_unique_json,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
    report = evaluate(payload)
    body = (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    target = Path(args.output)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(body)
        out.flush()
        os.fsync(out.fileno())
    print(json.dumps({"status": report["status"], "reason": report["reason"],
                      "production_recommendations": "DISABLED"}))
    return report


if __name__ == "__main__":
    main()
