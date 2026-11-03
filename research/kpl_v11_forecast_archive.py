"""KPL per-game forecast archives and chronological offline holdout (research only).

No KPL provider/network adapter, model fitting, betting or production integration.
All provenance and outcome verification flags are external assertions, NOT proofs.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

MAX_ARCHIVE_BYTES = 32_000_000
MAX_ROWS = 100_000
KINDS = frozenset({"past_result", "past_bp", "current_bp", "team_form", "roster", "market"})
PHASES = frozenset({"PRE_GAME", "BP_LOCKED"})
FORECAST_KEYS = frozenset({
    "prediction_id", "series_id", "game_number", "team_ids",
    "predicted_team_id", "probability", "model_version", "phase",
    "info_cutoff_at", "forecast_at", "game_start_at", "evidence", "status"})
EVIDENCE_KEYS = frozenset({
    "source_id", "kind", "subject_game", "published_at", "captured_at"})
RESULT_KEYS = frozenset({
    "prediction_id", "series_id", "game_number", "winner_team_id",
    "game_end_at", "observed_at", "source_id", "verified"})


def _time(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return dt.astimezone(timezone.utc)


def _ident(value):
    return (isinstance(value, str) and 0 < len(value) <= 128
            and value == value.strip())


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def validate_forecast(row):
    """All input information must have been captured by the forecast cutoff."""
    if not isinstance(row, dict) or set(row) != FORECAST_KEYS:
        raise ValueError("invalid forecast fields")
    if (not all(_ident(row[key]) for key in
                ("prediction_id", "series_id", "predicted_team_id", "model_version"))
            or row["status"] != "RESEARCH_ONLY"
            or row["phase"] not in PHASES):
        raise ValueError("invalid forecast identity/status/phase")
    game = row["game_number"]
    teams = row["team_ids"]
    if (type(game) is not int or not 1 <= game <= 7 or not isinstance(teams, list)
            or len(teams) != 2 or not all(_ident(x) for x in teams)
            or len(set(teams)) != 2 or row["predicted_team_id"] not in teams):
        raise ValueError("invalid team/game identity")
    p = row["probability"]
    if type(p) not in (float, int) or not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError("invalid probability")
    cutoff = _time(row["info_cutoff_at"])
    forecast = _time(row["forecast_at"])
    start = _time(row["game_start_at"])
    if not cutoff <= forecast < start:
        raise ValueError("forecast cutoff/time leakage")
    evidence = row["evidence"]
    if not isinstance(evidence, list) or not evidence or len(evidence) > 100:
        raise ValueError("missing/excessive evidence")
    fingerprints = set()
    for e in evidence:
        if not isinstance(e, dict) or set(e) != EVIDENCE_KEYS:
            raise ValueError("invalid evidence fields")
        kind, source, subject = e["kind"], e["source_id"], e["subject_game"]
        if (kind not in KINDS or not _ident(source) or type(subject) is not int
                or not 0 <= subject <= game):
            raise ValueError("invalid evidence identity or future game")
        if kind in ("past_result", "past_bp") and not 1 <= subject < game:
            raise ValueError("future/current game result/BP leakage")
        if kind == "current_bp" and (subject != game or row["phase"] != "BP_LOCKED"):
            raise ValueError("current BP before allowed phase")
        if kind in ("market", "roster") and subject != game:
            raise ValueError("wrong game for market/roster")
        if kind == "team_form" and subject != 0:
            raise ValueError("team_form must be series-independent")
        published = _time(e["published_at"])
        captured = _time(e["captured_at"])
        if not published <= captured <= cutoff:
            raise ValueError("post-cutoff evidence")
        fingerprint = (source, kind, subject)
        if fingerprint in fingerprints:
            raise ValueError("duplicate evidence fingerprint")
        fingerprints.add(fingerprint)
    return True


def _digest(prev_hash, forecast):
    return hashlib.sha256(_canonical({"previous_hash": prev_hash,
                                      "forecast": forecast})).hexdigest()


def verify_archive(path):
    """Detect local edits relative to stored hash chain, not independent immutability."""
    path = Path(path)
    if not path.exists():
        return {"records": [], "head_hash": "0" * 64}
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("oversized forecast archive")
    records, prev = [], "0" * 64
    ids, slots = set(), set()
    last_time = None
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.endswith("\n") or not line.strip() or len(records) >= MAX_ROWS:
                raise ValueError("truncated or excessive archive")
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("invalid archive JSON") from exc
            if not isinstance(item, dict) or set(item) != {"forecast", "previous_hash", "entry_hash"}:
                raise ValueError("invalid archive row")
            row = item["forecast"]
            validate_forecast(row)
            expected = _digest(prev, row)
            if item["previous_hash"] != prev or item["entry_hash"] != expected:
                raise ValueError("forecast archive chain mismatch")
            slot = (row["series_id"], row["game_number"])
            if row["prediction_id"] in ids or slot in slots:
                raise ValueError("duplicate archived forecast/game")
            timestamp = _time(row["forecast_at"])
            if last_time is not None and timestamp <= last_time:
                raise ValueError("archive time not strictly increasing")
            records.append(row)
            prev, last_time = expected, timestamp
            ids.add(row["prediction_id"])
            slots.add(slot)
    return {"records": records, "head_hash": prev}


def archive_forecast(path, forecast):
    """Append to a locally locked hash chain; caller must secure external head anchor.

    The local .lock provides single-process/multi-process exclusion on a shared
    filesystem, but neither the lock nor SHA256 prevents repository owners from
    rewriting the whole file. Do not call this tamper-proof archival storage.
    """
    validate_forecast(forecast)
    dest = Path(path)
    lock = dest.with_name(dest.name + ".lock")
    fd = os.open(str(lock), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.close(fd)
        state = verify_archive(dest)
        if len(state["records"]) >= MAX_ROWS:
            raise ValueError("archive full")
        for row in state["records"]:
            if row["prediction_id"] == forecast["prediction_id"]:
                raise ValueError("duplicate prediction")
            if (row["series_id"], row["game_number"]) == (
                    forecast["series_id"], forecast["game_number"]):
                raise ValueError("duplicate game prediction")
            if _time(forecast["forecast_at"]) <= _time(row["forecast_at"]):
                raise ValueError("cannot backdate archive")
        previous = state["head_hash"]
        digest = _digest(previous, forecast)
        data = _canonical({"forecast": forecast, "previous_hash": previous,
                           "entry_hash": digest}) + b"\n"
        if dest.exists() and dest.stat().st_size + len(data) > MAX_ARCHIVE_BYTES:
            raise ValueError("archive exceeds size limit")
        with dest.open("ab") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        return {"status": "RESEARCH_ONLY", "head_hash": digest,
                "external_immutable_anchor_verified": False,
                "live_execution_allowed": False}
    finally:
        lock.unlink(missing_ok=True)


def _validated_result(row, forecast):
    if not isinstance(row, dict) or set(row) != RESULT_KEYS:
        raise ValueError("invalid result fields")
    if (row["prediction_id"] != forecast["prediction_id"]
            or row["series_id"] != forecast["series_id"]
            or type(row["game_number"]) is not int
            or row["game_number"] != forecast["game_number"]
            or row["winner_team_id"] not in forecast["team_ids"]
            or not _ident(row["source_id"]) or row["verified"] is not True):
        raise ValueError("unverified or mismatched result")
    end, observed = _time(row["game_end_at"]), _time(row["observed_at"])
    if not _time(forecast["game_start_at"]) < end <= observed:
        raise ValueError("result time leakage")
    return int(row["winner_team_id"] == forecast["predicted_team_id"])


def _scores(pairs):
    if not pairs:
        return None
    n = len(pairs)
    brier = sum((p - y) ** 2 for p, y in pairs) / n
    logloss = -sum(y * math.log(max(min(p, 1 - 1e-15), 1e-15))
                   + (1 - y) * math.log(max(min(1 - p, 1 - 1e-15), 1e-15))
                   for p, y in pairs) / n
    bins = []
    for index in range(5):
        subset = [(p, y) for p, y in pairs if min(int(p * 5), 4) == index]
        if subset:
            bins.append({"bin": index, "count": len(subset),
                         "mean_predicted": sum(p for p, _ in subset) / len(subset),
                         "observed_rate": sum(y for _, y in subset) / len(subset)})
    ece = sum(v["count"] * abs(v["mean_predicted"] - v["observed_rate"])
              for v in bins) / n
    return {"count": n, "brier": brier, "log_loss": logloss,
            "ece_5_bins": ece, "calibration_bins": bins}


def chronological_holdout(forecasts, results, *, train_fraction=0.7, min_test=30):
    """Chronologically split by WHOLE series, after independent result admission.

    Does not fit models. Test results are used for scoring only, never feature
    construction, train-prior estimation or selection of a model hyperparameter.
    """
    if (not isinstance(forecasts, list) or not isinstance(results, list)
            or len(forecasts) != len(results) or len(forecasts) > MAX_ROWS
            or type(train_fraction) not in (int, float)
            or not 0 < train_fraction < 1
            or type(min_test) is not int or min_test < 1):
        raise ValueError("invalid holdout parameters/length")
    if len(forecasts) < min_test + 2:
        raise ValueError("insufficient holdout rows")
    ids, slots = set(), set()
    seen_series, series_order = set(), []
    starts = []
    for row in forecasts:
        validate_forecast(row)
        if row["prediction_id"] in ids:
            raise ValueError("duplicate prediction ID")
        slot = (row["series_id"], row["game_number"])
        if slot in slots:
            raise ValueError("duplicate game forecast")
        ids.add(row["prediction_id"])
        slots.add(slot)
        starts.append(_time(row["game_start_at"]))
        if row["series_id"] != (series_order[-1] if series_order else None):
            if row["series_id"] in seen_series:
                raise ValueError("noncontiguous series")
            series_order.append(row["series_id"])
            seen_series.add(row["series_id"])
    if starts != sorted(starts):
        raise ValueError("game starts must be chronological")
    # Ensure no overlapping series spans across temporal split boundaries.
    series_count = len(series_order)
    if series_count < 2:
        raise ValueError("at least two complete series required")
    outcome_by_id = {}
    for r in results:
        if not isinstance(r, dict) or not isinstance(r.get("prediction_id"), str):
            raise ValueError("invalid result row")
        key = r["prediction_id"]
        if key in outcome_by_id or key not in ids:
            raise ValueError("duplicate or unknown result")
        outcome_by_id[key] = r
    if len(outcome_by_id) != len(ids):
        raise ValueError("missing result")
    scored = []
    for row in forecasts:
        result = outcome_by_id[row["prediction_id"]]
        y = _validated_result(result, row)
        scored.append((row, result, y))
    # Choose a boundary between entire series, nearest the desired train size.
    boundaries = [i for i in range(1, len(scored)) if
                  scored[i - 1][0]["series_id"] != scored[i][0]["series_id"]]
    eligible = [i for i in boundaries if i >= 2 and len(scored) - i >= min_test]
    if not eligible:
        raise ValueError("insufficient series-level holdout")
    target = len(scored) * train_fraction
    split = min(eligible, key=lambda i: (abs(i - target), i))
    train, test = scored[:split], scored[split:]
    cutoff = min(_time(f["forecast_at"]) for f, _, _ in test)
    if any(_time(r["observed_at"]) >= cutoff for _, r, _ in train):
        raise ValueError("training outcomes unavailable before holdout forecast")
    train_pairs = [(f["probability"], y) for f, _, y in train]
    test_pairs = [(f["probability"], y) for f, _, y in test]
    train_prior = sum(y for _, _, y in train) / len(train)
    baseline = [(train_prior, y) for _, _, y in test]
    report = {"train": _scores(train_pairs), "holdout": _scores(test_pairs),
              "train_prior_baseline": _scores(baseline),
              "train_series": len({f["series_id"] for f, _, _ in train}),
              "test_series": len({f["series_id"] for f, _, _ in test}),
              "train_prior": train_prior, "min_test": min_test,
              "holdout_brier_improvement_vs_train_prior":
                  _scores(baseline)["brier"] - _scores(test_pairs)["brier"],
              "data_authenticity_independently_verified": False,
              "provider_usage_rights_verified": False,
              "research_only": True, "live_execution_allowed": False,
              "production_recommendations": "DISABLED", "status": "HOLD"}
    return report
