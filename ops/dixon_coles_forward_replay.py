"""Replay sealed D pilot vectors against later, unverified native-ID FT bytes.

Select the forecast cohort before reading results. Every supplied proof is
freshly verified; saved audit JSON never enters this interface. All output is
descriptive research, never trusted outcome admission or production promotion.
Run with PYTHONPATH=ops python -m ops.dixon_coles_forward_replay.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import math
from pathlib import Path
import re

import dixon_coles_witness_audit as forecast_audit
import forecast_provenance_audit as provenance
import model_dixon_coles_forward as producer
import raw_openligadb_identity_linkage as linkage
from research_center import score, score_rps, calibration
from retrospective_backtest import wilson, block_ci
from team_identity import team_id
from ops import openliga_capture_provenance as capture_provenance
from ops import openliga_capture_pack as capture_pack
from ops import trusted_result_evidence as outputs


INPUT_SCHEMA = "football-king-dixon-coles-forward-replay-input-v1"
# Fixed pilot history: include earlier revisions, never silently truncate them.
# The preparer shares this 32-proof bound and fails closed on overflow.
MAX_FORECASTS, MAX_CAPTURES, MAX_CASES = 16, 32, 3000
MAX_OUTPUT_BYTES = 16_000_000
FORECAST_FILES = {**{name: provenance.MAX_FILE_BYTES for name in provenance.SUBJECT_NAMES},
                  "research.sigstore.json": provenance.MAX_BUNDLE_BYTES}
CAPTURE_FILES = {capture_provenance.SUBJECT_NAME: capture_provenance.MAX_TAR_BYTES,
                 capture_provenance.BUNDLE_NAME: capture_provenance.MAX_BUNDLE_BYTES}
MODELS = ("original", "derived_rho0", "candidate")


class ReplayError(ValueError):
    """A bounded public-safe rejection code, never source content or tool stderr."""


def _require(condition, reason):
    if not condition:
        raise ReplayError(reason)


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _safety():
    return {**linkage._safety(), "certified_case_count": 0,
            "recorded_kickoff_independently_authenticated": False,
            "model_calibration_verified": False, "prospective_qualification_verified": False,
            "source_identity_independently_authenticated": False,
            "market_prices_executable": False, "model_advantage_verified": False,
            "betting_roi_estimable": False, "automatic_model_promotion": False}


def _entry(value, *, forecast):
    required = {"proof_dir", "source_sha", "workflow_sha", "run_id", "attempt"}
    allowed = required | ({"expected_shadow_sha256"} if forecast else set())
    _require(type(value) is dict and required <= set(value) <= allowed, "INVALID_PROOF_REFERENCE")
    _require(isinstance(value["proof_dir"], (str, Path)), "INVALID_PROOF_DIRECTORY")
    folder = Path(value["proof_dir"])
    capture_provenance._clean_path(folder)
    _require(folder.is_dir(), "MISSING_PROOF_DIRECTORY")
    for key in ("source_sha", "workflow_sha"):
        _require(type(value[key]) is str and re.fullmatch(r"[0-9a-f]{40}", value[key]),
                 "INVALID_COMMIT_REFERENCE")
    for key in ("run_id", "attempt"):
        _require(type(value[key]) is str and re.fullmatch(r"[1-9][0-9]{0,19}", value[key]),
                 "INVALID_RUN_REFERENCE")
    if "expected_shadow_sha256" in value:
        _require(type(value["expected_shadow_sha256"]) is str
                 and re.fullmatch(r"[0-9a-f]{64}", value["expected_shadow_sha256"]),
                 "INVALID_SHADOW_DIGEST_REFERENCE")
    return folder, {key: value[key] for key in required - {"proof_dir"}}


def _snapshot(folder, files):
    return {name: _digest(capture_provenance._read(folder/name, maximum))
            for name, maximum in files.items()}


def _reference(options, snapshot, witness):
    return {"source_commit": options["source_sha"], "workflow_commit": options["workflow_sha"],
            "run_id": options["run_id"], "run_attempt": options["attempt"],
            "verified_tlog_utc": witness,
            "subject_sha256": {k: v for k, v in snapshot.items() if not k.endswith("sigstore.json")},
            "bundle_sha256": next(v for k, v in snapshot.items() if k.endswith("sigstore.json"))}


def _forecasts(entries, current, snapshots):
    pool, references = [], []
    for entry in entries:
        folder, options = _entry(entry, forecast=True)
        before = _snapshot(folder, FORECAST_FILES)
        verified = forecast_audit.audit(folder, **options, now=current)
        _require(verified.get("audit_completed") is True
                 and verified.get("signature_identity_and_subjects_verified") is True,
                 "FRESH_FORECAST_VERIFICATION_FAILED")
        _require(_snapshot(folder, FORECAST_FILES) == before
                 and verified.get("subject_sha256") == {k: before[k] for k in provenance.SUBJECT_NAMES},
                 "FORECAST_BYTES_CHANGED_AFTER_VERIFICATION")
        if "expected_shadow_sha256" in entry:
            _require(before["shadow.json"] == entry["expected_shadow_sha256"], "PINNED_SHADOW_DIGEST_MISMATCH")
        raw = capture_provenance._read(folder/"shadow.json", provenance.MAX_FILE_BYTES)
        _require(_digest(raw) == before["shadow.json"], "FORECAST_SHADOW_CHANGED")
        shadow = provenance._json(raw)
        reference = _reference(options, before, verified["verified_tlog_utc"])
        references.append(reference)
        snapshots.append((folder, FORECAST_FILES, before))
        if not verified.get("candidate_capture_present"):
            continue  # Legacy bytes stay absent; never reconstruct a missing D.
        rows = shadow[producer.TOP_KEY]["predictions"]
        if not rows:
            continue
        _require(verified.get("candidate_bytes_formula_source_binding_verified") is True
                 and len(rows) == len(verified["cases"]), "UNBOUND_CANDIDATE_COHORT")
        for row, observed in zip(rows, verified["cases"]):
            _require(all(producer._canonical(row.get(key)) == producer._canonical(observed.get(key))
                         for key in ("league", "event_id", "home", "away", "kickoff_utc_recorded",
                                     "source_prediction_utc", "candidate_generated_utc", "model_id",
                                     "protocol_sha256", "source_projection_sha256")), "UNBOUND_CANDIDATE_ROW")
            pool.append((row, reference, observed["observed_before_recorded_kickoff"] is True))
        _require(len(pool) <= MAX_FORECASTS * producer.MAX_ROWS, "CANDIDATE_ROW_LIMIT")
    return pool, references


def _select(pool):
    identities, fixture_ids, grouped = defaultdict(set), defaultdict(set), defaultdict(list)
    for row, reference, witnessed in pool:
        ko = producer._utc(row["kickoff_utc_recorded"]).isoformat()
        fixture = (row["league"], team_id(row["league"], row["home"]),
                   team_id(row["league"], row["away"]), ko)
        identities[row["event_id"]].add((fixture, row["home"], row["away"]))
        fixture_ids[fixture].add(row["event_id"])
        if witnessed:
            grouped[(row["event_id"], ko, row["protocol_sha256"])].append((row, reference, fixture))
    _require(len(grouped) <= MAX_CASES, "UNIQUE_CANDIDATE_LIMIT")
    selected = []
    for key in sorted(grouped):
        records = grouped[key]
        earliest = min(producer._utc(row["candidate_generated_utc"]) for row, _, _ in records)
        tied = [item for item in records if producer._utc(item[0]["candidate_generated_utc"]) == earliest]
        row, reference, fixture = min(tied, key=lambda item: (
            producer._utc(item[1]["verified_tlog_utc"]), producer._canonical(item[1])))
        reason = None
        if len(identities[key[0]]) != 1 or len(fixture_ids[fixture]) != 1:
            reason = "FORECAST_EVENT_OR_FIXTURE_IDENTITY_CONFLICT"
        elif len({producer._canonical(item[0]) for item in tied}) != 1:
            reason = "CONFLICTING_EARLIEST_CANDIDATE_CAPTURE"
        selected.append({"case_id": _digest(producer._canonical(key)), "row": row,
                         "forecast_reference": reference, "selection_problem": reason})
    return selected, sum(witnessed for _, _, witnessed in pool)


def _id_hint(value):
    # Coercion is quarantine-only: a malformed duplicate can poison an ID but
    # can never become an accepted provider identity or result.
    if type(value) is int or type(value) is bool:
        return str(int(value)) if 0 < value < 10**15 else None
    if type(value) is float and math.isfinite(value) and 0 < value < 10**15 and value.is_integer():
        return str(int(value))
    if type(value) is str and re.fullmatch(r"[0-9]{1,15}", value) and int(value) > 0:
        return str(int(value))
    return None


def _results(entries, current, snapshots, needed):
    index = {key: {"identities": set(), "scores": set(), "invalid": False, "finals": []}
             for key in needed}
    references = []
    for entry in entries:
        folder, options = _entry(entry, forecast=False)
        before = _snapshot(folder, CAPTURE_FILES)
        verified = capture_provenance.audit(folder, **options, now=current)
        _require(verified.get("audit_completed") is True
                 and verified.get("signature_identity_and_subject_verified") is True
                 and verified.get("capture_content_replayed") is True, "FRESH_CAPTURE_VERIFICATION_FAILED")
        _require(_snapshot(folder, CAPTURE_FILES) == before
                 and verified.get("subject_sha256") == {capture_provenance.SUBJECT_NAME: before[capture_provenance.SUBJECT_NAME]}
                 and verified.get("bundle_sha256") == before[capture_provenance.BUNDLE_NAME],
                 "CAPTURE_BYTES_CHANGED_AFTER_VERIFICATION")
        raw = capture_provenance._read(folder/capture_provenance.SUBJECT_NAME, capture_provenance.MAX_TAR_BYTES)
        _require(_digest(raw) == before[capture_provenance.SUBJECT_NAME], "CAPTURE_TAR_CHANGED")
        witness = capture_provenance._time(verified["verified_tlog_utc"])
        replay = capture_pack.validate_capture(raw, witness=witness, now=current)
        capture_pack._same(verified["capture_summary"],
                           {k: replay[k] for k in capture_provenance.SUMMARY_KEYS if k in replay},
                           "CAPTURE_SUMMARY_MISMATCH")
        members = capture_pack._members(raw)
        manifest = capture_pack._json(members["manifest.json"])
        records = capture_pack._json(members["openligadb.json"])
        _require(type(records) is list and len(records) <= linkage.MAX_RAW_RECORDS, "RAW_RECORD_LIMIT")
        claimed = producer._utc(replay["captured_utc"])
        completed = producer._utc(replay["source_receipt"]["completed_utc"])
        reference = _reference(options, before, verified["verified_tlog_utc"])
        reference.update(raw_sha256=replay["raw_sha256"], manifest_sha256=replay["manifest_sha256"],
                         claimed_raw_capture_utc=claimed.isoformat(),
                         claimed_source_response_completed_utc=completed.isoformat())
        references.append(reference)
        snapshots.append((folder, CAPTURE_FILES, before))
        counts = Counter(_id_hint(row.get("matchID")) for row in records if type(row) is dict)
        for position, row in enumerate(records):
            hint = _id_hint(row.get("matchID")) if type(row) is dict else None
            if hint not in index:
                continue
            bucket = index[hint]
            if counts[hint] != 1:
                bucket["invalid"] = True
            parsed = linkage._raw_record(row, position, set(), claimed)
            if (type(row.get("matchID")) is not int or parsed.get("link_status") == "QUARANTINED"
                    or manifest["season_start"] != 2026 or row.get("leagueShortcut") != "bl1"
                    or type(row.get("leagueSeason")) is not int or row["leagueSeason"] != 2026):
                bucket["invalid"] = True
                continue
            identity = (parsed["raw_team_ids"]["home"], parsed["raw_team_ids"]["away"],
                        parsed["raw_kickoff_utc"], parsed["raw_home"], parsed["raw_away"],
                        row["leagueShortcut"], row["leagueSeason"])
            bucket["identities"].add(identity)
            if not parsed["raw_match_is_finished"]:
                continue
            finals = row.get("matchResults")
            finals = [v for v in finals if type(v) is dict and v.get("resultTypeID") == 2] if type(finals) is list else []
            if (len(finals) != 1 or type(finals[0].get("resultTypeID")) is not int
                    or finals[0].get("resultTypeKind") != "After90Minutes"
                    or not parsed["ft_candidate"]):
                bucket["invalid"] = True
                continue
            goals = tuple(parsed["score_ft_candidate"])
            bucket["scores"].add(goals)
            bucket["finals"].append({"score": goals, "identity": identity, "raw_index": position,
                                      "captured": claimed, "completed": completed, "witness": witness,
                                      "reference": reference})
    return index, references


def _case(selected, index, current):
    row = selected["row"]
    case = {**_safety(), **{k: row[k] for k in ("league", "event_id", "home", "away",
            "kickoff_utc_recorded", "candidate_generated_utc", "source_prediction_utc",
            "source_projection_sha256", "protocol_sha256", "model_id")},
            "case_id": selected["case_id"], "forecast_reference": selected["forecast_reference"],
            "result_status": "PENDING", "reason": "NO_LATER_FINISHED_SOURCE_CANDIDATE",
            "score_ft_candidate": None, "models": None, "capture_reference": None}
    if selected["selection_problem"]:
        case.update(result_status="QUARANTINED", reason=selected["selection_problem"])
        return case
    match = re.fullmatch(r"openligadb:([1-9][0-9]{0,14})", row["event_id"])
    kickoff = producer._utc(row["kickoff_utc_recorded"])
    if (not match or row["league"] != "bundesliga"
            or not datetime(2026, 7, 1, tzinfo=timezone.utc) <= kickoff < datetime(2027, 7, 1, tzinfo=timezone.utc)):
        case["reason"] = "EXACT_NATIVE_RESULT_LINK_NOT_SUPPORTED"
        return case
    bucket = index[match[1]]
    if bucket["invalid"] or len(bucket["identities"]) > 1 or len(bucket["scores"]) > 1:
        case.update(result_status="QUARANTINED", reason="CONFLICTING_OR_MALFORMED_NATIVE_RESULT_CLAIMS")
        return case
    if bucket["identities"]:
        identity = next(iter(bucket["identities"]))
        if (identity[2] != kickoff.isoformat() or identity[3] != row["home"] or identity[4] != row["away"]):
            case.update(result_status="QUARANTINED", reason="RECORDED_NATIVE_FIXTURE_MISMATCH")
            return case
    forecast_witness = producer._utc(selected["forecast_reference"]["verified_tlog_utc"])
    eligible = [v for v in bucket["finals"] if current >= kickoff+timedelta(minutes=120)
                and min(v["captured"], v["completed"]) >= kickoff+timedelta(minutes=100)
                and min(v["captured"], v["completed"], v["witness"]) > forecast_witness]
    if not eligible:
        return case
    result = min(eligible, key=lambda v: (v["captured"], v["witness"], producer._canonical(v["reference"])))
    goals = list(result["score"])
    y = 0 if goals[0] > goals[1] else 1 if goals[0] == goals[1] else 2
    models = {}
    for name in MODELS:
        values = list(row[name])
        loss, brier = score(values, y)
        models[name] = {"probabilities": values, "log_loss": loss, "brier": brier,
                        "rps": score_rps(values, y),
                        "top_choice_correct": max(range(3), key=lambda i: values[i]) == y}
    case.update(result_status="SCORED_UNVERIFIED_CANDIDATE", reason="LATER_NATIVE_FT_CANDIDATE_REPLAYED",
                score_ft_candidate=goals, outcome=y, models=models,
                capture_reference={**result["reference"], "raw_index": result["raw_index"]})
    return case


def _metrics(cases):
    rows = [c for c in cases if c["result_status"] == "SCORED_UNVERIFIED_CANDIDATE"]
    if not rows:
        return None, None
    n = len(rows)
    metrics = {}
    for name in MODELS:
        values = [c["models"][name] for c in rows]
        hits = sum(v["top_choice_correct"] for v in values)
        metrics[name] = {"n": n, "mean_log_loss": sum(v["log_loss"] for v in values)/n,
                         "mean_brier": sum(v["brier"] for v in values)/n,
                         "mean_rps": sum(v["rps"] for v in values)/n,
                         "top_probability_accuracy": hits/n, "hit_rate_wilson95": wilson(hits, n),
                         "calibration": calibration([{"p": c["models"][name]["probabilities"],
                                                       "y": c["outcome"]} for c in rows])}
    comparison = {"primary_baseline": "derived_rho0", "same_case_count": n,
                  "rho0_minus_candidate_mean_log_loss": metrics["derived_rho0"]["mean_log_loss"]-metrics["candidate"]["mean_log_loss"],
                  "weekly_paired_ci": block_ci([{"date": c["kickoff_utc_recorded"][:10],
                      "original": c["models"]["derived_rho0"]["probabilities"],
                      "candidate": c["models"]["candidate"]["probabilities"], "y": c["outcome"]}
                      for c in rows], "candidate"), "advantage_verified": False}
    return metrics, comparison


def audit(forecasts, captures, *, now=None):
    report = {**_safety(), "schema": "football-king-dixon-coles-forward-replay-v1",
              "audit_completed": False, "derived_review_not_a_trust_input": True,
              "selection_scope": "EARLIEST_VALID_CAPTURE_WITHIN_SUPPLIED_FIXED_MANIFEST_ONLY",
              "result_capture_scope": "SUPPLIED_MANIFEST_ONLY_NOT_COMPLETE_PROVIDER_HISTORY",
              "cohort_selected_before_results": False, "unique_candidate_cases": 0,
              "total_witnessed_rows": 0, "duplicate_snapshot_rows": 0,
              "settled_candidate_count": 0, "pending_candidate_count": 0,
              "quarantined_candidate_count": 0, "cases": [], "metrics": None, "comparison": None,
              "source_attribution": "OpenLigaDB/community contributors; ODbL 1.0 https://opendatacommons.org/licenses/odbl/1-0/",
              "notice": "只對原封存候選與較後原生ID完場觀察作研究復盤；不認證實際開波、比分真偽、來源獨立性或正式資格。"}
    try:
        current = now if now is not None else datetime.now(timezone.utc)
        _require(isinstance(current, datetime) and current.tzinfo is not None and current.utcoffset() is not None,
                 "INVALID_REPLAY_CLOCK")
        current = current.astimezone(timezone.utc)
        _require(type(forecasts) is list and 0 < len(forecasts) <= MAX_FORECASTS
                 and type(captures) is list and len(captures) <= MAX_CAPTURES, "PROOF_COUNT_LIMIT")
        snapshots = []
        pool, forecast_refs = _forecasts(forecasts, current, snapshots)
        selected, witnessed = _select(pool)  # Results are deliberately unread until after selection.
        needed = {match[1] for c in selected if (match := re.fullmatch(
            r"openligadb:([1-9][0-9]{0,14})", c["row"]["event_id"]))}
        index, capture_refs = _results(captures, current, snapshots, needed)
        cases = [_case(c, index, current) for c in selected]
        metrics, comparison = _metrics(cases)
        _require(all(_snapshot(folder, files) == before for folder, files, before in snapshots),
                 "PROOF_BYTES_CHANGED_DURING_REPLAY")
        universe = sorted(forecast_refs, key=producer._canonical)
        report.update(audit_completed=True, checked_utc=current.isoformat(),
                      cohort_selected_before_results=True, forecast_references=universe,
                      capture_references=capture_refs,
                      selection_universe_sha256=_digest(producer._canonical(universe)),
                      selected_cohort_sha256=_digest(producer._canonical([
                          [c["case_id"], c["row"], c["forecast_reference"]] for c in selected])),
                      unique_candidate_cases=len(cases), total_witnessed_rows=witnessed,
                      duplicate_snapshot_rows=witnessed-len(cases), cases=cases,
                      settled_candidate_count=sum(c["result_status"] == "SCORED_UNVERIFIED_CANDIDATE" for c in cases),
                      pending_candidate_count=sum(c["result_status"] == "PENDING" for c in cases),
                      quarantined_candidate_count=sum(c["result_status"] == "QUARANTINED" for c in cases),
                      metrics=metrics, comparison=comparison,
                      reason="FIXED_COHORT_RESEARCH_REPLAY_COMPLETED")
        _require(len(producer._canonical(report)) <= MAX_OUTPUT_BYTES, "REPLAY_OUTPUT_LIMIT")
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError, AttributeError) as exc:
        report.update(audit_completed=False, cohort_selected_before_results=False,
                      unique_candidate_cases=0, total_witnessed_rows=0, duplicate_snapshot_rows=0,
                      settled_candidate_count=0, pending_candidate_count=0, quarantined_candidate_count=0,
                      cases=[], metrics=None, comparison=None,
                      reason=str(exc) if isinstance(exc, ReplayError) else "REPLAY_INPUT_OR_PROOF_REJECTED")
        report.pop("forecast_references", None)
        report.pop("capture_references", None)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        value = provenance._json(capture_provenance._read(args.manifest, 100_000))
        _require(type(value) is dict and set(value) == {"schema", "forecasts", "captures"}
                 and value["schema"] == INPUT_SCHEMA, "INVALID_REPLAY_MANIFEST")
        outputs._output(args.output, args.manifest)
        for entries, forecast in ((value["forecasts"], True), (value["captures"], False)):
            _require(type(entries) is list and len(entries) <= (MAX_FORECASTS if forecast else MAX_CAPTURES),
                     "PROOF_COUNT_LIMIT")
            for entry in entries:
                folder, _ = _entry(entry, forecast=forecast)
                outputs._output(args.output, folder)
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        parser.error("output must be a new regular derived file outside all proof inputs; manifest must be valid")
    report = audit(value["forecasts"], value["captures"])
    try:
        outputs._write_new(args.output, report)
    except (OSError, ValueError):
        return 1
    return 0 if report["audit_completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
