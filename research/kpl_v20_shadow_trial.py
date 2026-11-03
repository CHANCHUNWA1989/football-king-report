"""KPL V20 prospective shadow-trial registry and full-universe settlement audit.

Research only. The local wall clock, manifest, result source and hash are NOT an
independent timestamp authority. Nothing runs automatically or accesses a feed.
No model training, market quotes, picks, betting or live execution.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from research.kpl_v11_forecast_archive import _time, _canonical

TRIAL_KEYS = frozenset({
    "trial_id", "registration_at", "model_version", "model_frozen_at", "series"})
SERIES_KEYS = frozenset({
    "series_id", "team_ids", "first_game_start_at", "schedule_source_id"})
DECISION_KEYS = frozenset({
    "series_id", "game_number", "team_ids", "decision", "probability_a",
    "reason_code", "phase", "info_cutoff_at", "forecast_at",
    "game_start_at", "basis_source_id"})
OUTCOME_KEYS = frozenset({
    "series_id", "game_number", "team_ids", "winner_team_id",
    "game_start_at", "game_end_at", "observed_at", "source_id", "source_status"})
REASONS = frozenset({
    "SHADOW_FORECAST", "NO_BP", "SOURCE_MISSING", "SOURCE_STALE",
    "MODEL_UNCALIBRATED", "NO_CONSERVATIVE_DIRECTION", "OTHER"})
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MAX_SERIES = 200
MAX_MANIFEST_BYTES = 150_000
MAX_DECISION_BYTES = 6_000
CLOCK_TOLERANCE_SECONDS = 60


def _utcnow():
    """Local machine clock only; tests patch this dependency."""
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _id(value):
    return isinstance(value, str) and SAFE_ID.fullmatch(value) is not None


def _near_clock(claimed, actual):
    return abs((_time(claimed) - actual).total_seconds()) <= CLOCK_TOLERANCE_SECONDS


def _read_json(path, max_bytes):
    with Path(path).open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    if not raw or len(raw) > max_bytes or not raw.endswith(b"\n"):
        raise ValueError("missing/oversized/truncated local trial record")
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("duplicate JSON key")
            obj[key] = value
        return obj
    try:
        data = json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              ValueError("nonfinite JSON value")))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("invalid local trial JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("invalid local trial object")
    return data, hashlib.sha256(raw).hexdigest()


def _check_manifest(manifest):
    if not isinstance(manifest, dict) or set(manifest) != TRIAL_KEYS:
        raise ValueError("invalid trial manifest")
    if not _id(manifest["trial_id"]) or not _id(manifest["model_version"]):
        raise ValueError("invalid trial or model id")
    registered = _time(manifest["registration_at"])
    if _time(manifest["model_frozen_at"]) > registered:
        raise ValueError("model not frozen before trial registration")
    items = manifest["series"]
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_SERIES:
        raise ValueError("invalid series universe size")
    seen = set()
    for row in items:
        if not isinstance(row, dict) or set(row) != SERIES_KEYS:
            raise ValueError("invalid declared series")
        sid, teams = row["series_id"], row["team_ids"]
        if (not _id(sid) or sid in seen or not _id(row["schedule_source_id"])
                or not isinstance(teams, list) or len(teams) != 2
                or not all(_id(team) for team in teams)
                or teams[0] == teams[1]):
            raise ValueError("duplicate or malformed series identity")
        if _time(row["first_game_start_at"]) <= registered:
            raise ValueError("schedule not after registration")
        seen.add(sid)
    return registered


def _load_manifest(directory):
    obj, digest = _read_json(Path(directory) / "manifest.json", MAX_MANIFEST_BYTES)
    _check_manifest(obj)
    return obj, digest


def _exclusive_json(path, value):
    """Create-only. No claim of distributed filesystem or external WORM safety."""
    raw = _canonical(value) + b"\n"
    path = Path(path)
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return hashlib.sha256(raw).hexdigest()


def register_shadow_trial(root, manifest):
    """Register all expected BO7 series before the earliest advertised start.

    This does not connect to an official schedule; the caller's claimed
    registration time is checked against the LOCAL wall clock only.
    """
    registered = _check_manifest(manifest)
    now = _utcnow()
    if not _near_clock(manifest["registration_at"], now):
        raise ValueError("registration not near local current time")
    if any(_time(row["first_game_start_at"]) <= now
           for row in manifest["series"]):
        raise ValueError("cannot register an already started series")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    dest = root / manifest["trial_id"]
    dest.mkdir(exist_ok=False)
    try:
        digest = _exclusive_json(dest / "manifest.json", manifest)
        (dest / "decisions").mkdir(exist_ok=False)
    except Exception:
        # Directory is deliberately retained for forensic inspection; never
        # silently replace or overwrite an existing trial.
        raise
    return {"status": "HOLD", "trial_dir": str(dest),
            "manifest_sha256": digest, "registered_series_count": len(manifest["series"]),
            "independently_timestamped": False,
            "live_execution_allowed": False, "production_recommendations": "DISABLED"}


def _validate_decision(record, series, *, now):
    if not isinstance(record, dict) or set(record) != DECISION_KEYS:
        raise ValueError("invalid shadow decision schema")
    if (record["series_id"] != series["series_id"]
            or record["team_ids"] != series["team_ids"]
            or type(record["game_number"]) is not int
            or not 1 <= record["game_number"] <= 7
            or record["phase"] != "PRE_GAME"
            or not _id(record["basis_source_id"])):
        raise ValueError("invalid shadow decision identity/phase")
    cutoff = _time(record["info_cutoff_at"])
    issued = _time(record["forecast_at"])
    starts = _time(record["game_start_at"])
    if not cutoff <= issued < starts or not _near_clock(record["forecast_at"], now):
        raise ValueError("decision is late, backdated, or after kickoff")
    if starts < _time(series["first_game_start_at"]):
        raise ValueError("game start before registered schedule")
    # For G1, a changed start cannot be quietly used to evade the deadline.
    if record["game_number"] == 1 and now >= _time(series["first_game_start_at"]):
        raise ValueError("game one already scheduled to start")
    state, p, reason = record["decision"], record["probability_a"], record["reason_code"]
    if state == "HOLD":
        if p is not None or reason not in REASONS - {"SHADOW_FORECAST"}:
            raise ValueError("HOLD must not publish a probability")
    elif state == "FORECAST":
        if (type(p) not in (int, float) or not math.isfinite(p) or
                not 0 <= p <= 1 or reason != "SHADOW_FORECAST"):
            raise ValueError("invalid research forecast or probability")
    else:
        raise ValueError("unknown shadow decision")


def submit_shadow_decision(trial_dir, decision):
    """Atomic local create-only write of ONE pre-map FORECAST or explicit HOLD."""
    manifest, digest = _load_manifest(trial_dir)
    if not isinstance(decision, dict) or not _id(decision.get("series_id")):
        raise ValueError("unknown registered series")
    chosen = [s for s in manifest["series"] if s["series_id"] == decision["series_id"]]
    if len(chosen) != 1:
        raise ValueError("unknown registered series")
    now = _utcnow()
    _validate_decision(decision, chosen[0], now=now)
    slot = decision["game_number"]
    for earlier in range(1, slot):
        prev_path = Path(trial_dir) / "decisions" / f"{decision['series_id']}-g{earlier}.json"
        if not prev_path.is_file():
            raise ValueError("prior game has no recorded decision/HOLD")
        previous = _read_decision(prev_path, digest)[0]["decision"]
        if _time(previous["game_start_at"]) >= _time(decision["game_start_at"]):
            raise ValueError("nonchronological series game times")
    packet = {"manifest_sha256": digest, "recorded_at": _iso(now),
              "decision": decision}
    path = Path(trial_dir) / "decisions" / f"{decision['series_id']}-g{slot}.json"
    packet_hash = _exclusive_json(path, packet)
    return {"status": "HOLD", "record_sha256": packet_hash,
            "trial_id": manifest["trial_id"], "series_id": decision["series_id"],
            "game_number": slot, "decision": decision["decision"],
            "externally_witnessed": False, "live_execution_allowed": False,
            "production_recommendations": "DISABLED"}


def _read_decision(path, manifest_hash):
    packet, digest = _read_json(path, MAX_DECISION_BYTES)
    if (set(packet) != {"manifest_sha256", "recorded_at", "decision"}
            or packet["manifest_sha256"] != manifest_hash):
        raise ValueError("decision manifest binding mismatch")
    return packet, digest


def _validate_outcomes(outcomes, manifest, now):
    if not isinstance(outcomes, list) or len(outcomes) > MAX_SERIES * 7:
        raise ValueError("invalid outcome collection")
    by_series = {s["series_id"]: [] for s in manifest["series"]}
    ids = {s["series_id"]: s for s in manifest["series"]}
    seen = set()
    for r in outcomes:
        if not isinstance(r, dict) or set(r) != OUTCOME_KEYS:
            raise ValueError("invalid outcome schema")
        sid, g = r["series_id"], r["game_number"]
        if not isinstance(sid, str) or sid not in ids or type(g) is not int or not 1 <= g <= 7:
            raise ValueError("unknown or invalid outcome slot")
        if (sid, g) in seen:
            raise ValueError("duplicate outcome")
        seen.add((sid, g))
        if (r["team_ids"] != ids[sid]["team_ids"]
                or r["winner_team_id"] not in ids[sid]["team_ids"]
                or r["source_status"] not in ("SOURCE_ASSERTED", "UNVERIFIED")
                or not _id(r["source_id"])):
            raise ValueError("invalid outcome identity or evidence")
        start, end, observed = [_time(r[k]) for k in
                                ("game_start_at", "game_end_at", "observed_at")]
        if not _time(ids[sid]["first_game_start_at"]) <= start < end <= observed <= now:
            raise ValueError("result unavailable or time leakage")
        by_series[sid].append(r)
    complete = set()
    for sid, group in by_series.items():
        group.sort(key=lambda r:r["game_number"])
        if [r["game_number"] for r in group] != list(range(1, len(group) + 1)):
            raise ValueError("noncontiguous result series")
        score = {t:0 for t in ids[sid]["team_ids"]}
        prev = None
        for r in group:
            start = _time(r["game_start_at"])
            if prev is not None and start <= prev:
                raise ValueError("nonchronological result games")
            if max(score.values()) >= 4:
                raise ValueError("game after BO7 already won")
            score[r["winner_team_id"]] += 1
            prev = start
        if max(score.values()) == 4:
            complete.add(sid)
    return by_series, complete


def audit_shadow_trial(trial_dir, outcomes):
    """Audit every enrolled series; HOLD is retained in the coverage denominator.

    Numeric diagnostics are allowed only for completed series with
    SOURCE_ASSERTED results, which remain self-asserted and NOT ground truth.
    """
    manifest, manifest_hash = _load_manifest(trial_dir)
    now = _utcnow()
    by_series, complete = _validate_outcomes(outcomes, manifest, now)
    decisions_dir = Path(trial_dir) / "decisions"
    slots = {}
    for path in decisions_dir.iterdir():
        if not path.is_file() or path.suffix != ".json":
            raise ValueError("unexpected shadow decision artifact")
        packet, _ = _read_decision(path, manifest_hash)
        d = packet["decision"]
        if not isinstance(d, dict) or not _id(d.get("series_id")):
            raise ValueError("invalid sealed decision")
        series = next((s for s in manifest["series"] if s["series_id"] == d["series_id"]), None)
        if series is None:
            raise ValueError("decision not in registered universe")
        _validate_decision(d, series, now=_time(packet["recorded_at"]))
        if not _time(manifest["registration_at"]) <= _time(packet["recorded_at"]) < _time(d["game_start_at"]):
            raise ValueError("decision recorded before registration or after kickoff")
        key = (d["series_id"], d["game_number"])
        if key in slots or path.name != f"{d['series_id']}-g{d['game_number']}.json":
            raise ValueError("duplicate or renamed shadow record")
        slots[key] = d
    missing = held = forecasts = 0
    scored = []
    incomplete_count = len(manifest["series"]) - len(complete)
    for sid, results in by_series.items():
        if sid not in complete:
            continue
        for r in results:
            d = slots.get((sid, r["game_number"]))
            if d is None:
                missing += 1
            elif d["game_start_at"] != r["game_start_at"]:
                raise ValueError("recorded kickoff differs from result")
            elif d["decision"] == "HOLD":
                held += 1
            else:
                forecasts += 1
                if r["source_status"] == "SOURCE_ASSERTED":
                    scored.append((d["probability_a"],
                                   int(r["winner_team_id"] == d["team_ids"][0])))
    played = sum(len(by_series[sid]) for sid in complete)
    metrics = None
    if scored:
        n = len(scored)
        brier = sum((p-y)**2 for p,y in scored)/n
        logloss = -sum(y*math.log(max(p, 1e-15)) +
                       (1-y)*math.log(max(1-p, 1e-15))
                       for p,y in scored)/n
        with_dir = [(p > .5) == bool(y) for p,y in scored if p != .5]
        metrics = {"source_asserted_only": True, "scored_forecasts": n,
                   "brier": brier, "log_loss": logloss,
                   "uniform_50_brier": .25,
                   "direction_count": len(with_dir),
                   "direction_accuracy": (sum(with_dir)/len(with_dir)
                                          if with_dir else None)}
    return {
        "status": "HOLD", "trial_id": manifest["trial_id"],
        "registered_series_count": len(manifest["series"]),
        "completed_series_count": len(complete),
        "unresolved_registered_series_count": incomplete_count,
        "completed_played_maps": played,
        "missing_pregame_decision_count": missing,
        "hold_decision_count": held,
        "forecast_decision_count": forecasts,
        "played_map_decision_coverage": ((held+forecasts)/played if played else None),
        "played_map_forecast_coverage": (forecasts/played if played else None),
        "diagnostic_only_not_real_kpl": metrics,
        "trial_registration_independently_witnessed": False,
        "decisions_independently_witnessed": False,
        "results_independently_authenticated": False,
        "schedule_independently_authenticated": False,
        "real_kpl_accuracy_verified": False, "positive_ev_verified": False,
        "live_execution_allowed": False, "production_recommendations": "DISABLED",
        "research_only": True,
        "reasons": ["LOCAL_CLOCK_AND_FILES_NOT_EXTERNALLY_ANCHORED",
                    "OFFICIAL_RESULT_AND_SCHEDULE_PROVENANCE_NOT_VERIFIED",
                    "NO_REAL_KPL_CALIBRATION_OR_POSITIVE_EV_EVIDENCE"],
    }
