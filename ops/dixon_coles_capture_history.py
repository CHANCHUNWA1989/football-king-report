"""Restore every present capture in a fixed pilot run range, without scoring.

The catalogue is frozen before reading capture bodies or contacting GitHub.
There is no latest/top-N fallback. Metadata is checked afresh, but signatures
and publisher truth remain the replay verifier's separate responsibility.
"""
from datetime import date, datetime, timezone
import gzip
import io
import os
from pathlib import Path
import re
import stat
import subprocess
import zlib

import prepare_forecast_proof as existing


FIRST_RUN = 40258192078
BASELINE = (FIRST_RUN, 1)
MAX_HISTORY_CAPTURES = 31  # The caller supplies one additional current proof.
MAX_ARCHIVE_ENTRIES = 5000
FILE_LIMITS = {'openliga-capture.tar': 4_000_000, 'capture.sigstore.json': 2_000_000}
WORKFLOW_PATH = '.github/workflows/four-model-shadow-daily.yml'
WORKFLOW_ID = 383990991


def _require(condition, reason):
    if not condition:
        raise existing.PreparationError(reason)


def _key(run_id, attempt):
    _require(all(type(v) is str and re.fullmatch(r'[1-9][0-9]{0,19}', v)
                 for v in (run_id, attempt)), 'INVALID_CAPTURE_HISTORY_CUTOFF')
    key = int(run_id), int(attempt)
    _require(key >= BASELINE, 'INVALID_CAPTURE_HISTORY_CUTOFF')
    return key


def _identity(info):
    return info.st_dev, info.st_ino


def _child(parent, name):
    before = os.stat(name, dir_fd=parent, follow_symlinks=False)
    _require(stat.S_ISDIR(before.st_mode), 'UNSAFE_CAPTURE_ARCHIVE_DIRECTORY')
    child = os.open(name, existing.DIRECTORY_FLAGS, dir_fd=parent)
    try:
        _require(_identity(before) == _identity(os.fstat(child)),
                 'CAPTURE_DIRECTORY_CHANGED')
        return child
    except BaseException:
        os.close(child)
        raise


def _catalogue(root_fd):
    """Inspect only directory names and identities, never result bytes."""
    rows, seen, visited = [], set(), 0
    today = datetime.now(timezone.utc).date()

    def walk(descriptor, parts):
        nonlocal visited
        with os.scandir(descriptor) as entries:
            for entry in entries:
                visited += 1
                _require(visited <= MAX_ARCHIVE_ENTRIES, 'CAPTURE_ARCHIVE_ENTRY_LIMIT')
                info = entry.stat(follow_symlinks=False)
                _require(stat.S_ISDIR(info.st_mode), 'UNSAFE_CAPTURE_ARCHIVE_DIRECTORY')
                if len(parts) < 3:
                    digits = 4 if not parts else 2
                    _require(re.fullmatch(r'[0-9]{'+str(digits)+r'}', entry.name),
                             'INVALID_CAPTURE_ARCHIVE_DATE_PATH')
                    next_parts = parts + (entry.name,)
                    if len(next_parts) == 1:
                        _require(1 <= int(entry.name) <= today.year, 'INVALID_CAPTURE_ARCHIVE_YEAR')
                    elif len(next_parts) == 2:
                        _require(1 <= int(entry.name) <= 12, 'INVALID_CAPTURE_ARCHIVE_MONTH')
                    else:
                        try:
                            day = date(*(int(v) for v in next_parts))
                        except ValueError:
                            raise existing.PreparationError('INVALID_CAPTURE_ARCHIVE_DAY') from None
                        _require(day <= today, 'FUTURE_CAPTURE_ARCHIVE_DAY')
                    child = _child(descriptor, entry.name)
                    try:
                        walk(child, next_parts)
                    finally:
                        os.close(child)
                else:
                    matched = re.fullmatch(r'([1-9][0-9]{0,19})-([1-9][0-9]{0,19})', entry.name)
                    _require(matched is not None, 'INVALID_CAPTURE_ARCHIVE_RUN_PATH')
                    key = tuple(int(v) for v in matched.groups())
                    _require(key not in seen, 'AMBIGUOUS_CAPTURE_ARCHIVE')
                    seen.add(key)
                    rows.append((key, Path(*parts, entry.name), _identity(info)))

    walk(root_fd, ())
    return sorted(rows)


def _read_regular(descriptor, name, maximum):
    before = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
    _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
             and 0 < before.st_size <= maximum, 'UNSAFE_OR_OVERSIZED_CAPTURE_FILE')
    file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
    with os.fdopen(file_fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        _require(_identity(before) == _identity(opened)
                 and stat.S_ISREG(opened.st_mode) and opened.st_nlink == 1,
                 'CAPTURE_FILE_CHANGED')
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    linked = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
    def version(info):
        return (_identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)
    _require(version(before) == version(opened) == version(after) == version(linked),
             'CAPTURE_FILE_CHANGED')
    _require(0 < len(raw) <= maximum, 'COMPRESSED_CAPTURE_SIZE_LIMIT')
    return raw


def _read_gzip(descriptor, name, maximum):
    compressed = _read_regular(descriptor, name+'.gz', maximum + 65_536)
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            raw = stream.read(maximum + 1)
    except (OSError, EOFError, ValueError, zlib.error):
        raise existing.PreparationError('INVALID_CAPTURE_GZIP') from None
    _require(0 < len(raw) <= maximum, 'DECODED_CAPTURE_SIZE_LIMIT')
    if name == 'capture.sigstore.json':
        existing._json_object(raw, 'INVALID_CAPTURE_BUNDLE_JSON')
    return raw


def _files(descriptor, *, compressed):
    expected = {name+('.gz' if compressed else '') for name in FILE_LIMITS}
    _require(set(os.listdir(descriptor)) == expected, 'CAPTURE_ARCHIVE_FILE_ALLOWLIST')
    return {name: (_read_gzip(descriptor, name, maximum) if compressed
                   else _read_regular(descriptor, name, maximum))
            for name, maximum in FILE_LIMITS.items()}


def _metadata(run_id, attempt):
    argv = ['gh', 'api', 'repos/'+existing.REPOSITORY+'/actions/runs/'+run_id+'/attempts/'+attempt]
    try:
        result = subprocess.run(argv, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        raise existing.PreparationError('CAPTURE_RUN_METADATA_TOOL_UNAVAILABLE_OR_TIMEOUT') from None
    _require(result.returncode == 0, 'CAPTURE_RUN_METADATA_API_REJECTED')
    _require(isinstance(result.stdout, bytes) and 0 < len(result.stdout) <= existing.MAX_API_BYTES,
             'INVALID_CAPTURE_RUN_METADATA_SIZE')
    value = existing._json_object(result.stdout, 'INVALID_CAPTURE_RUN_METADATA_JSON')
    _require(type(value.get('id')) is int and value['id'] == int(run_id)
             and type(value.get('run_attempt')) is int and value['run_attempt'] == int(attempt),
             'CAPTURE_RUN_ATTEMPT_METADATA_MISMATCH')
    for key in ('repository', 'head_repository'):
        repository = value.get(key)
        _require(type(repository) is dict and type(repository.get('id')) is int
                 and repository['id'] == existing.REPOSITORY_ID
                 and repository.get('full_name') == existing.REPOSITORY,
                 'CAPTURE_RUN_REPOSITORY_MISMATCH')
    _require(type(value.get('workflow_id')) is int and value['workflow_id'] == WORKFLOW_ID
             and value.get('path') == WORKFLOW_PATH and value.get('head_branch') == 'main'
             and value.get('event') in ('schedule', 'workflow_dispatch')
             and value.get('status') == 'completed' and value.get('conclusion') == 'success',
             'UNTRUSTED_CAPTURE_RUN_METADATA')
    sha = value.get('head_sha')
    _require(type(sha) is str and re.fullmatch(r'[0-9a-f]{40}', sha), 'INVALID_CAPTURE_RUN_HEAD_SHA')
    return sha


def collect(root, *, current_proof: Path, run_id: str, attempt: str):
    """Return restored prior proofs from one immutable checkout's present history.

    The fixed baseline is mandatory. A byte-identical archive of the current
    proof is checked then omitted; older attempts stay separate. Every error
    rejects the whole history. No files are written and no signature is trusted.
    """
    cutoff = _key(run_id, attempt)
    root, current_proof = existing._absolute_path(root), existing._absolute_path(current_proof)
    _require(not root.is_relative_to(current_proof) and not current_proof.is_relative_to(root),
             'OVERLAPPING_CAPTURE_HISTORY_PATHS')
    root_fd = current_fd = None
    try:
        root_fd = existing._open_directory(root)
        catalogue = _catalogue(root_fd)
        _require(any(key == BASELINE for key, _, _ in catalogue), 'CAPTURE_HISTORY_BASELINE_MISSING')
        selected = [(key, path, identity) for key, path, identity in catalogue
                    if BASELINE <= key <= cutoff]
        historical = sum(key != cutoff for key, _, _ in selected)
        _require(historical <= MAX_HISTORY_CAPTURES, 'CAPTURE_HISTORY_COUNT_LIMIT')
        # Selection and all limits precede any result/bundle bytes or API call.
        current_fd = existing._open_directory(current_proof)
        current_files = _files(current_fd, compressed=False)
        restored = []
        for key, relative, identity in selected:
            descriptor = os.dup(root_fd)
            try:
                for part in relative.parts:
                    child = _child(descriptor, part)
                    os.close(descriptor)
                    descriptor = child
                _require(_identity(os.fstat(descriptor)) == identity, 'CAPTURE_DIRECTORY_CHANGED')
                files = _files(descriptor, compressed=True)
            finally:
                os.close(descriptor)
            if key == cutoff:
                _require(files == current_files, 'CURRENT_CAPTURE_ARCHIVE_MISMATCH')
                continue
            restored.append({'name':'capture-'+str(key[0])+'-'+str(key[1]),
                             'files':files, 'archive_ref':relative.as_posix(),
                             'reference':{'run_id':str(key[0]), 'attempt':str(key[1])}})
        # All compressed inputs are preflighted before network metadata checks.
        for item in restored:
            reference = item['reference']
            sha = _metadata(reference['run_id'], reference['attempt'])
            reference.update(source_sha=sha, workflow_sha=sha)
        _require(_catalogue(root_fd) == catalogue, 'CAPTURE_HISTORY_DIRECTORY_CHANGED')
        _require(_files(current_fd, compressed=False) == current_files, 'CURRENT_CAPTURE_PROOF_CHANGED')
        return restored
    except OSError:
        raise existing.PreparationError('UNSAFE_OR_UNREADABLE_CAPTURE_HISTORY') from None
    finally:
        for descriptor in (current_fd, root_fd):
            if descriptor is not None:
                os.close(descriptor)
