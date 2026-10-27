"""Restore the fixed two-snapshot D pilot for fresh signature verification.

The first registered snapshot supplies the complete original 20-case universe;
the later snapshot repeats 18 native-ID cases. No result or latest-run fallback
selects these inputs. This adapter authenticates neither signatures nor scores.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

import prepare_forecast_proof as existing


SCHEMA = 'football-king-dixon-coles-forward-replay-input-v1'
FORECASTS = (
    {'run_id': '40295717023', 'attempt': '1',
     'source_sha': '26039d4ee8fcddabee6d42ec8217ba04c01ed491',
     'workflow_sha': '26039d4ee8fcddabee6d42ec8217ba04c01ed491',
     'expected_shadow_sha256': '0ce01c472f8a5b5c1fdfdbeb13a5a755c5ca9284808bbce62d2287ea80b9663e',
     'archive_ref': '2026/10/26/40295717023-1'},
    {'run_id': '40377738523', 'attempt': '1',
     'source_sha': 'd419dd5cce314392d7dd00bf5f1e6352c3307f33',
     'workflow_sha': 'd419dd5cce314392d7dd00bf5f1e6352c3307f33',
     'expected_shadow_sha256': '22d5d2dde6b87ef16393f0234ac0d8dc7087150b83612e761024d80353aa9864',
     'archive_ref': '2026/10/26/40377738523-1'},
)
CAPTURE_FILES = {'openliga-capture.tar': 4_000_000, 'capture.sigstore.json': 2_000_000}


def _require(condition, reason):
    if not condition:
        raise existing.PreparationError(reason)


def _context(source, workflow, run_id, attempt):
    _require(all(type(value) is str and re.fullmatch(r'[0-9a-f]{40}', value)
                 for value in (source, workflow)), 'INVALID_CAPTURE_COMMIT')
    _require(all(type(value) is str and re.fullmatch(r'[1-9][0-9]{0,19}', value)
                 for value in (run_id, attempt)), 'INVALID_CAPTURE_RUN')


def _capture_preflight(path):
    descriptor = existing._open_directory(path)
    try:
        _require(set(os.listdir(descriptor)) == set(CAPTURE_FILES), 'INVALID_CAPTURE_PROOF_FILES')
        for name, maximum in CAPTURE_FILES.items():
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                     and 0 < info.st_size <= maximum, 'INVALID_CAPTURE_PROOF_FILE')
    finally:
        os.close(descriptor)


def _identity(info):
    return info.st_dev, info.st_ino


def _matches(parent_fd, name, descriptor):
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return _identity(current) == _identity(os.fstat(descriptor))


def _new_directory(parent_fd, name):
    os.mkdir(name, mode=0o700, dir_fd=parent_fd)
    before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    descriptor = os.open(name, existing.DIRECTORY_FLAGS, dir_fd=parent_fd)
    try:
        _require(_identity(before) == _identity(os.fstat(descriptor))
                 and _matches(parent_fd, name, descriptor), 'OUTPUT_DIRECTORY_CHANGED')
        _require(not os.listdir(descriptor), 'OUTPUT_DIRECTORY_NOT_EMPTY')
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _create_file(directory_fd, name, raw, created):
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         mode=0o600, dir_fd=directory_fd)
    # Keep the original FD until publication/cleanup, preventing inode reuse.
    created[name] = descriptor
    with os.fdopen(os.dup(descriptor), 'wb') as stream:
        stream.write(raw)


def _check_publication(parent_fd, name, output_fd, children, root_files):
    _require(_matches(parent_fd, name, output_fd), 'OUTPUT_DIRECTORY_CHANGED')
    _require(set(os.listdir(output_fd)) == {name for name, _, _ in children} | set(root_files),
             'OUTPUT_DIRECTORY_CONTENTS_CHANGED')
    for child_name, child_fd, files in children:
        _require(_matches(output_fd, child_name, child_fd), 'OUTPUT_DIRECTORY_CHANGED')
        _require(set(os.listdir(child_fd)) == set(files), 'OUTPUT_DIRECTORY_CONTENTS_CHANGED')
        for filename, descriptor in files.items():
            _require(_matches(child_fd, filename, descriptor), 'OUTPUT_FILE_CHANGED')
    for filename, descriptor in root_files.items():
        _require(_matches(output_fd, filename, descriptor), 'OUTPUT_FILE_CHANGED')
    _require(_matches(parent_fd, name, output_fd), 'OUTPUT_DIRECTORY_CHANGED')


def _remove_owned(parent_fd, name, descriptor, *, directory=False):
    """Best-effort cleanup through retained FDs; preserve replacement entries."""
    try:
        if _matches(parent_fd, name, descriptor):
            if directory:
                os.rmdir(name, dir_fd=parent_fd)
            else:
                os.unlink(name, dir_fd=parent_fd)
    except OSError:
        pass


def _publish(parent_fd, destination, payloads, manifest):
    """Create exclusively, retain ownership FDs, and publish the manifest last.

    Initial emptiness and final identity/content checks reject observed
    replacements. Standard POSIX mkdir/open and check/unlink are separate
    operations: a hostile same-UID actor can still race between them, including
    substituting an entirely empty directory before the first open.
    """
    output_fd = None
    children, root_files = [], {}
    try:
        try:
            output_fd = _new_directory(parent_fd, destination.name)
        except FileExistsError:
            raise existing.PreparationError('OUTPUT_DIRECTORY_ALREADY_EXISTS') from None
        for name, files in payloads:
            child_fd = _new_directory(output_fd, name)
            created = {}
            children.append((name, child_fd, created))
            for filename, raw in files.items():
                _create_file(child_fd, filename, raw, created)
        _check_publication(parent_fd, destination.name, output_fd, children, root_files)
        raw = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, allow_nan=False)+'\n').encode()
        _create_file(output_fd, '.manifest.json.stage', raw, root_files)
        _check_publication(parent_fd, destination.name, output_fd, children, root_files)
        # link() publishes atomically and fails rather than overwriting a name.
        os.link('.manifest.json.stage', 'manifest.json', src_dir_fd=output_fd,
                dst_dir_fd=output_fd, follow_symlinks=False)
        root_files['manifest.json'] = root_files['.manifest.json.stage']
        _check_publication(parent_fd, destination.name, output_fd, children, root_files)
        os.unlink('.manifest.json.stage', dir_fd=output_fd)
        del root_files['.manifest.json.stage']
        _check_publication(parent_fd, destination.name, output_fd, children, root_files)
    except BaseException:
        if output_fd is not None:
            for name, descriptor in root_files.items():
                _remove_owned(output_fd, name, descriptor)
            for name, child_fd, created in reversed(children):
                for filename, descriptor in created.items():
                    _remove_owned(child_fd, filename, descriptor)
                _remove_owned(output_fd, name, child_fd, directory=True)
            _remove_owned(parent_fd, destination.name, output_fd, directory=True)
        raise
    finally:
        for _, child_fd, created in children:
            for descriptor in created.values():
                os.close(descriptor)
            os.close(child_fd)
        for descriptor in set(root_files.values()):
            os.close(descriptor)
        if output_fd is not None:
            os.close(output_fd)


def prepare(root, destination, *, capture_proof, capture_source_sha, capture_workflow_sha,
            capture_run_id, capture_attempt):
    """Return the new manifest location, with no signature-verification claim."""
    _context(capture_source_sha, capture_workflow_sha, capture_run_id, capture_attempt)
    root, destination, capture = (existing._absolute_path(path)
                                  for path in (root, destination, capture_proof))
    for source in (root, capture):
        _require(not destination.is_relative_to(source) and not source.is_relative_to(destination),
                 'OVERLAPPING_INPUT_OR_OUTPUT')
    root_fd = parent_fd = None
    try:
        root_fd = existing._open_directory(root)
        parent_fd = existing._open_directory(destination.parent)
        _capture_preflight(capture)
        try:
            os.stat(destination.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise existing.PreparationError('OUTPUT_DIRECTORY_ALREADY_EXISTS')
        payloads, references = [], []
        _require(type(FORECASTS) is tuple and len(FORECASTS) == 2, 'INVALID_REGISTERED_COHORT')
        for pin in FORECASTS:
            _context(pin['source_sha'], pin['workflow_sha'], pin['run_id'], pin['attempt'])
            _, relative = existing._select(root_fd, (int(pin['run_id']), int(pin['attempt'])))
            _require(relative.as_posix() == pin['archive_ref'], 'PINNED_FORECAST_ARCHIVE_PATH_MISMATCH')
            descriptor = existing._open_directory(root/relative)
            try:
                files = {name: existing._read_gzip(descriptor, name,
                         existing.MAX_SUBJECT_BYTES if name in existing.SUBJECT_NAMES
                         else existing.MAX_BUNDLE_BYTES) for name in existing.PROOF_NAMES}
            finally:
                os.close(descriptor)
            _require(hashlib.sha256(files['shadow.json']).hexdigest() == pin['expected_shadow_sha256'],
                     'PINNED_SHADOW_DIGEST_MISMATCH')
            name = pin['run_id']+'-'+pin['attempt']
            payloads.append((name, files))
            references.append({key: pin[key] for key in (
                'source_sha', 'workflow_sha', 'run_id', 'attempt', 'expected_shadow_sha256')})
            references[-1]['proof_dir'] = str(destination/name)
        # All compressed inputs are preflighted before metadata or output.
        for pin in FORECASTS:
            sha = existing._run_metadata(pin['run_id'], pin['attempt'])
            _require(sha == pin['source_sha'] == pin['workflow_sha'],
                     'PINNED_FORECAST_COMMIT_MISMATCH')
        manifest = {'schema': SCHEMA, 'forecasts': references, 'captures': [{
            'proof_dir': str(capture), 'source_sha': capture_source_sha,
            'workflow_sha': capture_workflow_sha, 'run_id': capture_run_id,
            'attempt': capture_attempt}]}
        _publish(parent_fd, destination, payloads, manifest)
    except OSError:
        raise existing.PreparationError('UNSAFE_OR_UNREADABLE_PATH') from None
    finally:
        for descriptor in (parent_fd, root_fd):
            if descriptor is not None:
                os.close(descriptor)
    return {'status': 'HOLD', 'preparation_completed': True,
            'manifest': str(destination/'manifest.json'), 'forecast_batches': len(references),
            'signature_verification_performed': False}


def main(argv=None):
    try:
        parser = existing._Parser(description=__doc__)
        parser.add_argument('--archives', required=True)
        parser.add_argument('--output-dir', required=True)
        parser.add_argument('--capture-proof', required=True)
        for name in ('capture-source-sha', 'capture-workflow-sha', 'capture-run-id', 'capture-attempt'):
            parser.add_argument('--'+name, required=True)
        args = parser.parse_args(argv)
        result = prepare(Path(args.archives), Path(args.output_dir), capture_proof=Path(args.capture_proof),
                         capture_source_sha=args.capture_source_sha, capture_workflow_sha=args.capture_workflow_sha,
                         capture_run_id=args.capture_run_id, capture_attempt=args.capture_attempt)
    except Exception as exc:
        reason = str(exc) if isinstance(exc, existing.PreparationError) else 'COHORT_PREPARATION_FAILED'
        print(json.dumps({'status': 'HOLD', 'preparation_completed': False, 'reason': reason}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
