"""Replay raw provider IDs against freshly reverified original forecast IDs.

This diagnostic does not authenticate publisher responses, capture times,
actual kickoffs or regulation-time results. Every output remains HOLD.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile

import forecast_provenance_audit
from shadow_raw_source_collector import URLS
from source_fixture_identity import validate_sealed_identity


MAX_MANIFEST_BYTES = 200_000
MAX_RAW_BYTES = 3_000_000
MAX_RAW_RECORDS = 20_000
MAX_OUTPUT_BYTES = 32_000_000
LINK = "SAME_PROVIDER_FIXED_ID_UNAUTHENTICATED_LINK"


class LinkageError(ValueError):
    """Public-safe rejection code; never raw CLI errors or publisher content."""


def _require(condition, reason):
    if not condition:
        raise LinkageError(reason)


def _safety():
    return {"status": "HOLD", "production_recommendations": "DISABLED",
            "independently_verified": False, "eligible_for_model_scoring": False,
            "eligible_for_betting_promotion": False,
            "raw_source_authenticated": False, "raw_capture_time_authenticated": False,
            "original_endpoint_verified": False, "source_freshness_verified": False,
            "forecast_team_ids_verified": False,
            "actual_kickoff_independently_authenticated": False,
            "regulation_90_minute_ft_authenticated": False,
            "outcomes_independently_authenticated": False}


def _no_symlink_path(path):
    _require(isinstance(path, Path), "INVALID_INPUT_PATH")
    # Preserve '..' while inspecting the lexical parent chain: resolving or
    # normalizing first could conceal a symlink encountered before '..'.
    absolute = path if path.is_absolute() else Path.cwd() / path
    _require(not any(parent.is_symlink() for parent in (absolute, *absolute.parents)),
             "SYMLINK_PATH_COMPONENT")


def _read(path, maximum):
    # O_NOFOLLOW closes the lstat/open symlink race; O_NONBLOCK avoids FIFOs.
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(descriptor)
        _require(stat.S_ISREG(info.st_mode), "UNSAFE_INPUT_FILE")
        _require(0 < info.st_size <= maximum, "INPUT_FILE_SIZE_LIMIT")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            raw = stream.read(maximum + 1)
        _require(0 < len(raw) <= maximum, "INPUT_FILE_SIZE_LIMIT")
        return raw
    except OSError as exc:
        raise LinkageError("MISSING_OR_UNSAFE_INPUT_FILE") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _json(raw):
    def unique(items):
        result = {}
        for key, value in items:
            _require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    def constant(_):
        raise LinkageError("NONFINITE_JSON_NUMBER")

    def finite(value):
        number = float(value)
        _require(math.isfinite(number), "NONFINITE_JSON_NUMBER")
        return number

    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=constant,
                          parse_float=finite)
    except LinkageError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise LinkageError("INVALID_JSON") from exc


def _utc(value, reason):
    _require(type(value) is str and 0 < len(value) <= 80, reason)
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, OverflowError) as exc:
        raise LinkageError(reason) from exc
    _require(stamp.tzinfo is not None and stamp.utcoffset() == timedelta(0), reason)
    return stamp.astimezone(timezone.utc)


def _name(value):
    return (type(value) is str and 0 < len(value) <= 160
            and value == value.strip() and value.isprintable())


def _raw_id(value, reason):
    _require(type(value) is int and value > 0, reason)
    return str(value)


def _load_raw(raw_dir):
    _require(isinstance(raw_dir, Path) and not raw_dir.is_symlink() and raw_dir.is_dir(),
             "INVALID_RAW_DIRECTORY")
    manifest_bytes = _read(raw_dir / "manifest.json", MAX_MANIFEST_BYTES)
    manifest = _json(manifest_bytes)
    _require(type(manifest) is dict
             and manifest.get("schema") == "football-king-raw-ft-source-candidates-v1"
             and manifest.get("status") == "HOLD"
             and manifest.get("production_recommendations") == "DISABLED"
             and manifest.get("independently_verified") is False, "UNSAFE_RAW_MANIFEST")
    year = manifest.get("season_start")
    _require(type(year) is int and 2000 <= year <= 2100, "INVALID_MANIFEST_SEASON")
    capture = _utc(manifest.get("captured_utc"), "INVALID_RAW_CAPTURE_UTC")
    sources = manifest.get("sources")
    _require(type(sources) is list and len(sources) <= len(URLS)
             and all(type(source) is dict for source in sources), "INVALID_SOURCE_LIST")
    selected = [source for source in sources if source.get("provider") == "OpenLigaDB"]
    _require(len(selected) == 1, "MISSING_OR_DUPLICATE_OPENLIGADB_SOURCE")
    source = selected[0]
    _require(source.get("status") == "FETCHED_UNVERIFIED", "OPENLIGADB_NOT_FETCHED_UNVERIFIED")
    expected_url = URLS["OpenLigaDB"].format(year=year)
    _require(source.get("source_url") == expected_url, "SOURCE_URL_MISMATCH")
    _require(source.get("raw_file") == "openligadb.json", "UNSAFE_RAW_FILE_PATH")
    _require(type(source.get("bytes")) is int and 0 < source["bytes"] <= MAX_RAW_BYTES,
             "INVALID_MANIFEST_BYTE_SIZE")
    _require(type(source.get("raw_sha256")) is str
             and re.fullmatch(r"[0-9a-f]{64}", source["raw_sha256"]), "INVALID_RAW_DIGEST")
    raw = _read(raw_dir / "openligadb.json", MAX_RAW_BYTES)
    _require(len(raw) == source["bytes"], "RAW_BYTE_SIZE_MISMATCH")
    digest = hashlib.sha256(raw).hexdigest()
    _require(digest == source["raw_sha256"], "RAW_HASH_MISMATCH")
    # Parse exactly the bytes that passed both size and digest checks.
    records = _json(raw)
    _require(type(records) is list and len(records) <= MAX_RAW_RECORDS,
             "INVALID_OR_OVERSIZED_OPENLIGADB_RECORDS")
    return records, capture, {"raw_sha256": digest, "raw_member": "openligadb.json",
                             "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                             "source_url": expected_url, "season_start": year,
                             "claimed_raw_capture_utc": manifest["captured_utc"]}


def _raw_record(row, index, duplicate_ids, capture):
    item = {**_safety(), "raw_index": index, "link_status": "QUARANTINED",
            "fixed_id_linked": False, "ft_candidate": False,
            "score_ft_candidate": None}
    try:
        _require(type(row) is dict, "INVALID_RAW_RECORD")
        match_id = _raw_id(row.get("matchID"), "INVALID_RAW_MATCH_ID")
        item["raw_match_id"] = match_id
        _require(match_id not in duplicate_ids, "DUPLICATE_RAW_MATCH_ID")
        home, away = row.get("team1"), row.get("team2")
        _require(type(home) is dict and type(away) is dict, "INVALID_RAW_TEAMS")
        home_id = _raw_id(home.get("teamId"), "INVALID_RAW_TEAM_ID")
        away_id = _raw_id(away.get("teamId"), "INVALID_RAW_TEAM_ID")
        item["raw_team_ids"] = {"home": home_id, "away": away_id}
        _require(home_id != away_id, "DUPLICATE_RAW_TEAM_ID")
        _require(_name(home.get("teamName")) and _name(away.get("teamName"))
                 and home["teamName"] != away["teamName"], "INVALID_RAW_TEAM_NAMES")
        item.update(raw_home=home["teamName"], raw_away=away["teamName"])
        kickoff = _utc(row.get("matchDateTimeUTC"), "INVALID_RAW_KICKOFF_UTC")
        item["raw_kickoff_utc"] = kickoff.isoformat()
        finished = row.get("matchIsFinished")
        _require(type(finished) is bool, "INVALID_RAW_FINISHED_FLAG")
        item["raw_match_is_finished"] = finished
        item.update(link_status="UNMATCHED", reason="NO_EXACT_SEALED_PROVIDER_ID")
        if not finished:
            item["ft_candidate_reason"] = "RAW_MATCH_NOT_FINISHED"
            return item
        try:
            results = row.get("matchResults")
            _require(type(results) is list, "INVALID_RAW_RESULTS")
            # Equality would also admit 2.0; a malformed final must not hide
            # beside a valid one or create an ambiguous final result.
            finals = [result for result in results if type(result) is dict
                      and result.get("resultTypeID") == 2]
            _require(len(finals) == 1, "MISSING_OR_DUPLICATE_RAW_FINAL_RESULT")
            final = finals[0]
            _require(type(final.get("resultTypeID")) is int, "INVALID_RAW_FINAL_RESULT_TYPE")
            goals = [final.get("pointsTeam1"), final.get("pointsTeam2")]
            _require(all(type(goal) is int and 0 <= goal <= 30 for goal in goals),
                     "INVALID_RAW_FINAL_GOALS")
            _require(capture >= kickoff, "RAW_CAPTURE_BEFORE_RECORDED_KICKOFF")
            item.update(ft_candidate=True, score_ft_candidate=goals,
                        ft_candidate_reason="UNAUTHENTICATED_RAW_FT_CANDIDATE")
        except LinkageError as exc:
            item["ft_candidate_reason"] = str(exc)
    except LinkageError as exc:
        item["reason"] = str(exc)
    return item


def _sealed_index(pairs, cases):
    eligible = {}
    claims = defaultdict(list)
    exclusions = []
    _require(type(cases) is list and len(cases) == len(pairs), "PROVENANCE_CASE_SET_MISMATCH")
    for index, (row, case) in enumerate(zip(pairs, cases)):
        excluded = {**_safety(), "pair_index": index}
        if type(row) is dict and _name(row.get("case_id")):
            excluded["case_id"] = row["case_id"]
        try:
            _require(type(row) is dict, "INVALID_SEALED_ROW")
            try:
                validate_sealed_identity(row)
            except ValueError as exc:
                raise LinkageError("INVALID_SEALED_SOURCE_IDENTITY") from exc
            identity = row.get("source_fixture_identity")
            _require(type(identity) is dict, "LEGACY_OR_UNTYPED_SOURCE_IDENTITY")
            # validate_sealed_identity pins the only supported namespace.
            key = (identity["provider"], identity["match_id"])
            fixture = (row.get("league"), row.get("home"), row.get("away"),
                       _utc(row.get("kickoff_utc"), "INVALID_SEALED_KICKOFF_UTC").isoformat())
            claims[key].append((index, fixture))
            _require(type(case) is dict and case.get("pair_index") == index
                     and case.get("case_id") == row.get("case_id"), "PROVENANCE_CASE_SET_MISMATCH")
            _require(case.get("observed_before_recorded_kickoff") is True,
                     "FORECAST_NOT_OBSERVED_BEFORE_RECORDED_KICKOFF")
            _require(case.get("source_fixture_identity") == identity
                     and case.get("forecast_event_id") == row["forecast_event_id"],
                     "PROVENANCE_SOURCE_IDENTITY_MISMATCH")
            eligible[index] = (key, row, case)
        except LinkageError as exc:
            excluded["reason"] = str(exc)
            exclusions.append(excluded)
    conflicts = {key for key, rows in claims.items() if len({fixture for _, fixture in rows}) > 1}
    by_id = defaultdict(list)
    for index, (key, row, case) in eligible.items():
        if key in conflicts:
            exclusions.append({**_safety(), "pair_index": index, "case_id": row["case_id"],
                               "reason": "CONFLICTING_SEALED_PROVIDER_ID"})
        elif len(claims[key]) != 1:
            exclusions.append({**_safety(), "pair_index": index, "case_id": row["case_id"],
                               "reason": "DUPLICATE_SEALED_PROVIDER_ID"})
        else:
            by_id[key].append((index, row, case))
    return by_id, conflicts, exclusions


def audit_linkage(raw_dir, proof, *, source_sha, workflow_sha, run_id, attempt, now=None):
    """Reverify the fixed proof this call; saved audits are never inputs."""
    report = {**_safety(), "schema": "football-king-raw-openligadb-identity-linkage-v1",
              "audit_completed": False, "forecast_signature_reverified": False,
              "linked_count": 0, "ft_candidate_count": 0, "raw_record_count": 0,
              "cases": [], "sealed_exclusions": [],
              "notice": "固定來源 ID 只供重播未認證連結；不認證實際開波、90分鐘賽果或模型表現。"}
    try:
        _no_symlink_path(proof)
        _no_symlink_path(raw_dir)
        # Always invoke the existing verifier directly, including failed raw inputs.
        provenance = forecast_provenance_audit.audit(
            proof, source_sha=source_sha, workflow_sha=workflow_sha,
            run_id=run_id, attempt=attempt, now=now)
        _require(type(provenance) is dict and provenance.get("audit_completed") is True
                 and provenance.get("signature_identity_and_subjects_verified") is True,
                 "FRESH_FORECAST_PROVENANCE_VERIFICATION_FAILED")
        _require(isinstance(proof, Path) and not proof.is_symlink() and proof.is_dir(),
                 "INVALID_PROOF_DIRECTORY")
        paired_bytes = _read(proof / "paired.json", forecast_provenance_audit.MAX_FILE_BYTES)
        digest = hashlib.sha256(paired_bytes).hexdigest()
        subjects = provenance.get("subject_sha256")
        _require(type(subjects) is dict and subjects.get("paired.json") == digest,
                 "PAIRED_BYTES_CHANGED_AFTER_FRESH_AUDIT")
        paired = _json(paired_bytes)
        _require(type(paired) is dict and type(paired.get("comparisons")) is list
                 and len(paired["comparisons"]) <= forecast_provenance_audit.MAX_COHORT_ROWS,
                 "INVALID_FRESH_PAIRED_DOCUMENT")
        checked = _utc(provenance.get("checked_utc"), "INVALID_FRESH_AUDIT_CLOCK")
        report.update(forecast_signature_reverified=True, paired_sha256=digest,
                      checked_utc=checked.isoformat(),
                      provenance_reference={"source_commit": provenance.get("source_commit"),
                          "workflow_commit": provenance.get("workflow_commit"),
                          "run_id": provenance.get("run_id"), "run_attempt": provenance.get("run_attempt"),
                          "verified_tlog_utc": provenance.get("verified_tlog_utc"),
                          "subject_sha256": subjects, "bundle_sha256": provenance.get("bundle_sha256"),
                          "verification_tool": "gh attestation verify"})
        by_id, conflicts, exclusions = _sealed_index(paired["comparisons"], provenance.get("cases"))
        records, capture, refs = _load_raw(raw_dir)
        report.update(refs, raw_record_count=len(records), sealed_exclusions=exclusions)
        _require(capture <= checked + timedelta(minutes=5), "RAW_CAPTURE_CLAIM_IN_FUTURE")
        id_counts = Counter(row["matchID"] for row in records if type(row) is dict
                            and type(row.get("matchID")) is int and row["matchID"] > 0)
        duplicates = {str(value) for value, count in id_counts.items() if count > 1}
        rows = []
        for index, record in enumerate(records):
            item = _raw_record(record, index, duplicates, capture)
            item.update(raw_sha256=refs["raw_sha256"], raw_member=refs["raw_member"],
                        paired_sha256=digest)
            if item["link_status"] != "QUARANTINED":
                key = ("OpenLigaDB", item["raw_match_id"])
                candidates = by_id.get(key, [])
                if key in conflicts:
                    item.update(link_status="QUARANTINED", reason="CONFLICTING_SEALED_PROVIDER_ID")
                elif len(candidates) == 1:
                    pair_index, pair, case = candidates[0]
                    item.update(pair_index=pair_index, case_id=pair["case_id"],
                                forecast_event_id=pair["forecast_event_id"],
                                source_fixture_identity=dict(pair["source_fixture_identity"]),
                                recorded_kickoff_utc=pair["kickoff_utc"],
                                verified_tlog_utc=case.get("verified_tlog_utc"))
                    if (_utc(pair["kickoff_utc"], "INVALID_SEALED_KICKOFF_UTC").isoformat()
                            != item["raw_kickoff_utc"]):
                        item.update(link_status="CONFLICT", reason="EXACT_ID_KICKOFF_CONFLICT")
                    elif (pair["home"] != item["raw_home"] or pair["away"] != item["raw_away"]):
                        item.update(link_status="CONFLICT", reason="EXACT_ID_PROVIDER_TEAM_NAMES_CONFLICT")
                    else:
                        item.update(link_status=LINK, reason=LINK, fixed_id_linked=True)
            # Scores are candidates only for the exact linked original forecast.
            if not item["fixed_id_linked"]:
                item.update(ft_candidate=False, score_ft_candidate=None)
            rows.append(item)
        report.update(audit_completed=True, cases=rows,
                      linked_count=sum(row["fixed_id_linked"] for row in rows),
                      ft_candidate_count=sum(row["ft_candidate"] for row in rows),
                      reason_counts=dict(sorted(Counter(row["reason"] for row in rows).items())),
                      reason="RAW_FIXED_ID_LINKAGE_AUDIT_COMPLETED")
        _require(len((json.dumps(report, ensure_ascii=False) + "\n").encode("utf-8"))
                 <= MAX_OUTPUT_BYTES, "OUTPUT_SIZE_LIMIT")
    except (LinkageError, OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        # Public-safe codes only. Never propagate raw tool or filesystem messages.
        report.update(audit_completed=False, cases=[], sealed_exclusions=[], linked_count=0,
                      ft_candidate_count=0, reason=str(error) if isinstance(error, LinkageError)
                      else "LINKAGE_INPUT_OR_TOOL_ERROR")
    return report


def _write_output(output, report, raw_dir, proof):
    _no_symlink_path(output)
    _require(isinstance(output, Path) and not output.is_symlink(), "UNSAFE_OUTPUT_PATH")
    resolved = output.resolve()
    _require(not any(resolved.is_relative_to(directory.resolve()) for directory in (raw_dir, proof)),
             "OUTPUT_MUST_BE_OUTSIDE_INPUT_DIRECTORIES")
    if output.exists():
        info = output.stat()
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "UNSAFE_OUTPUT_ALIAS")
    body = (json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    _require(len(body) <= MAX_OUTPUT_BYTES, "OUTPUT_SIZE_LIMIT")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".raw-id-linkage-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(body)
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = audit_linkage(args.raw_dir, args.proof, source_sha=args.source_sha,
                           workflow_sha=args.workflow_sha, run_id=args.run_id, attempt=args.attempt)
    try:
        _write_output(args.output, report, args.raw_dir, args.proof)
    except (LinkageError, OSError, ValueError, TypeError, OverflowError, RecursionError):
        return 1
    return 0 if report["audit_completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
