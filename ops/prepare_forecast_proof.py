"""Prepare latest or explicitly pinned forecast bytes for NEW verification.

Only the four fixed gzip inputs are decoded. Saved verification reports and
certificate fields never supply identities. A fresh official Actions API call
pins the selected run attempt; this adapter does not verify any signature.
"""
import argparse
from datetime import date, datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import zlib


REPOSITORY = "CHANCHUNWA1989/football-king-report"
REPOSITORY_ID = 1411226578
WORKFLOW_PATH = ".github/workflows/football-king-iphone.yml"
SUBJECT_NAMES = ("shadow.json", "paired.json", "slate.json")
PROOF_NAMES = SUBJECT_NAMES + ("research.sigstore.json",)
MAX_COMPRESSED_BYTES = 4 * 1024 * 1024
MAX_SUBJECT_BYTES = 8 * 1024 * 1024
MAX_BUNDLE_BYTES = 2 * 1024 * 1024
MAX_API_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 5000
MAX_PINNED_PAIRS = 10000
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


class PreparationError(ValueError):
    """A public-safe rejection code, without command output or file contents."""


def _require(condition, reason):
    if not condition:
        raise PreparationError(reason)


def _absolute_path(value):
    try:
        path = Path(value)
    except (TypeError, ValueError):
        raise PreparationError("INVALID_INPUT_OR_OUTPUT_PATH") from None
    _require(len(str(path)) <= 4096 and "\0" not in str(path) and ".." not in path.parts,
             "INVALID_INPUT_OR_OUTPUT_PATH")
    # POSIX permits a distinct spelling with two leading slashes. Normalize it
    # before containment checks; no symlink is resolved or accepted here.
    return Path("/", *path.absolute().parts[1:])


def _open_directory(path):
    """Anchor each ancestor without following symlinks, including above root."""
    descriptor = os.open(path.anchor, DIRECTORY_FLAGS)
    try:
        for part in path.parts[1:]:
            before = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
            _require(stat.S_ISDIR(before.st_mode), "UNSAFE_DIRECTORY_PATH")
            child = os.open(part, DIRECTORY_FLAGS, dir_fd=descriptor)
            after = os.fstat(child)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                os.close(child)
                raise PreparationError("DIRECTORY_CHANGED_DURING_PREFLIGHT")
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _select(root_fd, requested=None):
    seen = set()
    latest = None
    visited = 0
    today = datetime.now(timezone.utc).date()

    def walk(descriptor, parts):
        nonlocal latest, visited
        with os.scandir(descriptor) as entries:
            for entry in entries:
                visited += 1
                _require(visited <= MAX_ARCHIVE_ENTRIES, "ARCHIVE_ENTRY_LIMIT")
                info = entry.stat(follow_symlinks=False)
                _require(stat.S_ISDIR(info.st_mode), "UNSAFE_ARCHIVE_DIRECTORY")
                if len(parts) < 3:
                    digits = 4 if not parts else 2
                    _require(re.fullmatch(r"[0-9]{" + str(digits) + r"}", entry.name)
                             is not None, "INVALID_ARCHIVE_DATE_PATH")
                    next_parts = parts + (entry.name,)
                    if len(next_parts) == 1:
                        _require(1 <= int(entry.name) <= today.year,
                                 "INVALID_ARCHIVE_YEAR")
                    elif len(next_parts) == 2:
                        _require(1 <= int(entry.name) <= 12, "INVALID_ARCHIVE_MONTH")
                    else:
                        try:
                            archive_day = date(*(int(part) for part in next_parts))
                        except ValueError:
                            raise PreparationError("INVALID_ARCHIVE_DATE") from None
                        _require(archive_day <= today, "FUTURE_ARCHIVE_DATE")
                else:
                    matched = re.fullmatch(r"([1-9][0-9]{0,19})-([1-9][0-9]{0,19})",
                                           entry.name)
                    _require(matched is not None, "INVALID_ARCHIVE_RUN_PATH")
                    key = tuple(int(value) for value in matched.groups())
                    _require(key not in seen, "AMBIGUOUS_ARCHIVE_RUN_ATTEMPT")
                    seen.add(key)
                    relative = Path(*parts, entry.name)
                    if ((requested is None and (latest is None or key > latest[0]))
                            or key == requested):
                        latest = (key, relative)
                    continue
                child = os.open(entry.name, DIRECTORY_FLAGS, dir_fd=descriptor)
                try:
                    after = os.fstat(child)
                    _require((info.st_dev, info.st_ino) == (after.st_dev, after.st_ino),
                             "DIRECTORY_CHANGED_DURING_PREFLIGHT")
                    walk(child, next_parts)
                finally:
                    os.close(child)

    walk(root_fd, ())
    _require(latest is not None, "PINNED_FORECAST_ARCHIVE_NOT_FOUND"
             if requested is not None else "NO_FORECAST_ARCHIVE")
    return latest


def _unique_object(items):
    result = {}
    for key, value in items:
        _require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _nonfinite(_):
    raise PreparationError("NONFINITE_JSON_NUMBER")


def _json_object(raw, reason):
    try:
        result = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_nonfinite)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise PreparationError(reason) from None
    _require(isinstance(result, dict), reason)
    return result


def _read_gzip(descriptor, name, limit):
    name += ".gz"
    before = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
    _require(stat.S_ISREG(before.st_mode), "UNSAFE_PROOF_FILE")
    _require(0 < before.st_size <= MAX_COMPRESSED_BYTES, "COMPRESSED_PROOF_SIZE_LIMIT")
    file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
    with os.fdopen(file_fd, "rb") as stream:
        after = os.fstat(stream.fileno())
        _require(stat.S_ISREG(after.st_mode)
                 and (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino),
                 "PROOF_FILE_CHANGED_DURING_PREFLIGHT")
        compressed = stream.read(MAX_COMPRESSED_BYTES + 1)
    _require(0 < len(compressed) <= MAX_COMPRESSED_BYTES, "COMPRESSED_PROOF_SIZE_LIMIT")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
            raw = stream.read(limit + 1)
    except (OSError, EOFError, ValueError, zlib.error):
        raise PreparationError("INVALID_PROOF_GZIP") from None
    _require(0 < len(raw) <= limit, "DECODED_PROOF_SIZE_LIMIT")
    _json_object(raw, "INVALID_PROOF_JSON")
    return raw


def _run_metadata(run_id, attempt):
    argv = ["gh", "api", "repos/" + REPOSITORY + "/actions/runs/" + run_id
            + "/attempts/" + attempt]
    try:
        completed = subprocess.run(argv, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        raise PreparationError("RUN_METADATA_TOOL_UNAVAILABLE_OR_TIMEOUT") from None
    _require(completed.returncode == 0, "RUN_METADATA_API_REJECTED")
    _require(isinstance(completed.stdout, bytes)
             and 0 < len(completed.stdout) <= MAX_API_BYTES, "INVALID_RUN_METADATA_SIZE")
    metadata = _json_object(completed.stdout, "INVALID_RUN_METADATA_JSON")
    _require(type(metadata.get("id")) is int and metadata["id"] == int(run_id)
             and type(metadata.get("run_attempt")) is int
             and metadata["run_attempt"] == int(attempt), "RUN_ATTEMPT_METADATA_MISMATCH")
    for key in ("repository", "head_repository"):
        repository = metadata.get(key)
        _require(isinstance(repository, dict) and type(repository.get("id")) is int
                 and repository["id"] == REPOSITORY_ID
                 and type(repository.get("full_name")) is str
                 and repository["full_name"] == REPOSITORY, "RUN_REPOSITORY_MISMATCH")
    _require(metadata.get("head_branch") == "main" and metadata.get("path") == WORKFLOW_PATH
             and metadata.get("status") == "completed"
             and metadata.get("conclusion") == "success", "UNTRUSTED_RUN_METADATA")
    sha = metadata.get("head_sha")
    _require(type(sha) is str and re.fullmatch(r"[0-9a-f]{40}", sha) is not None,
             "INVALID_RUN_HEAD_SHA")
    return sha


def _publish(parent_fd, destination, payloads, manifest):
    try:
        os.mkdir(destination.name, mode=0o700, dir_fd=parent_fd)
    except FileExistsError:
        raise PreparationError("OUTPUT_DIRECTORY_ALREADY_EXISTS") from None
    output_fd = None
    created = []
    try:
        output_fd = os.open(destination.name, DIRECTORY_FLAGS, dir_fd=parent_fd)
        documents = dict(payloads)
        documents["selection.json"] = (json.dumps(manifest, sort_keys=True) + "\n").encode()
        for name, raw in documents.items():
            file_fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                              mode=0o600, dir_fd=output_fd)
            created.append(name)
            with os.fdopen(file_fd, "wb") as stream:
                stream.write(raw)
    except BaseException:
        for name in created:
            os.unlink(name, dir_fd=output_fd)
        os.rmdir(destination.name, dir_fd=parent_fd)
        raise
    finally:
        if output_fd is not None:
            os.close(output_fd)


def prepare(root: Path, destination: Path, *, run_id=None, attempt=None,
            case_id=None, paired_sha256=None) -> dict:
    """Decode one exact batch, without fallback or signature-authentication claims.

    A case review supplies all four pins. Digests and case membership select
    bytes only; forecast_provenance_audit must freshly verify their signature.
    Omitted pins preserve latest-run selection for the normal daily path.
    """
    requested = None
    pins = (run_id, attempt, case_id, paired_sha256)
    if any(value is not None for value in pins):
        _require(all(type(value) is str and re.fullmatch(pattern, value) is not None
                     for value, pattern in zip(pins, (
                         r"[1-9][0-9]{0,19}", r"[1-9][0-9]{0,19}",
                         r"[0-9a-f]{64}", r"[0-9a-f]{64}"))), "INVALID_FORECAST_PIN")
        requested = (int(run_id), int(attempt))
    root, destination = _absolute_path(root), _absolute_path(destination)
    _require(destination.name and not destination.is_relative_to(root),
             "OUTPUT_INSIDE_ARCHIVES")
    root_fd = parent_fd = candidate_fd = None
    try:
        root_fd = _open_directory(root)
        parent_fd = _open_directory(destination.parent)
        try:
            os.stat(destination.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise PreparationError("OUTPUT_DIRECTORY_ALREADY_EXISTS")
        (run_number, attempt_number), relative = _select(root_fd, requested)
        # Select FIRST: a broken latest batch is never skipped for an older one.
        candidate_fd = os.dup(root_fd)
        for part in relative.parts:
            child = os.open(part, DIRECTORY_FLAGS, dir_fd=candidate_fd)
            os.close(candidate_fd)
            candidate_fd = child
        payloads = {name: _read_gzip(candidate_fd, name,
                                   MAX_SUBJECT_BYTES if name in SUBJECT_NAMES else MAX_BUNDLE_BYTES)
                    for name in PROOF_NAMES}
        if requested is not None:
            _require(hashlib.sha256(payloads["paired.json"]).hexdigest() == paired_sha256,
                     "PINNED_PAIRED_DIGEST_MISMATCH")
            rows = _json_object(payloads["paired.json"], "INVALID_PROOF_JSON").get("comparisons")
            _require(isinstance(rows, list) and len(rows) <= MAX_PINNED_PAIRS
                     and all(isinstance(row, dict) for row in rows), "INVALID_PINNED_PAIR_COHORT")
            _require(sum(row.get("case_id") == case_id for row in rows) == 1,
                     "PINNED_CASE_MISSING_OR_AMBIGUOUS")
        run_id, attempt = str(run_number), str(attempt_number)
        sha = _run_metadata(run_id, attempt)
        manifest = {"proof_dir": str(destination.resolve()), "source_sha": sha, "workflow_sha": sha,
                    "run_id": run_id, "attempt": attempt,
                    "source_root_relative_ref": relative.as_posix()}
        if requested is not None:
            manifest.update(selection_mode="PINNED_ORIGINAL_CASE",
                            expected_case_id=case_id, paired_sha256=paired_sha256)
        _publish(parent_fd, destination, payloads, manifest)
        return manifest
    except OSError:
        raise PreparationError("UNSAFE_OR_UNREADABLE_PATH") from None
    finally:
        for descriptor in (candidate_fd, parent_fd, root_fd):
            if descriptor is not None:
                os.close(descriptor)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise PreparationError("INVALID_ARGUMENTS")


def main(argv=None):
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument("--archives", required=True)
        parser.add_argument("--output-dir", required=True)
        parser.add_argument("--run-id")
        parser.add_argument("--attempt")
        parser.add_argument("--case-id")
        parser.add_argument("--paired-sha256")
        args = parser.parse_args(argv)
        result = prepare(Path(args.archives), Path(args.output_dir),
                         run_id=args.run_id, attempt=args.attempt,
                         case_id=args.case_id, paired_sha256=args.paired_sha256)
    except Exception as exc:
        reason = str(exc) if isinstance(exc, PreparationError) else "PREPARATION_FAILED"
        print(json.dumps({"status": "HOLD", "preparation_completed": False, "reason": reason}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
