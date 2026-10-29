"""Prepare a private original ZIP after pinned GitHub relay verification.

No network, Drive authentication or durable-storage claim is supplied. The caller
must authenticate metadata fetches and bootstrap-verify local code BEFORE importing
this module: self-checking code cannot authenticate itself. Private configuration
contains independently reviewed file pins, never values learned from artifacts.
"""
import argparse
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from ops import private_relay_provenance as provenance
from ops import private_response_archive as archive
from ops import private_response_capture as capture
from ops import private_response_relay as relay

CONFIG_SCHEMA = 'football-king-private-drive-handoff-config-v1'
RECIPIENT_PATH = 'sources/policies/private_original_recipient_v1.txt'
REQUIRED_CODE_PATHS = frozenset((
    'ops/private_response_capture.py', 'ops/private_response_archive.py',
    'ops/private_response_relay.py', 'ops/private_relay_provenance.py',
    'ops/private_drive_handoff.py', 'ops/install_age.py', 'ops/odds_market.py', RECIPIENT_PATH))
WORKFLOWS = frozenset(('.github/workflows/private-all-market-research.yml',
                       '.github/workflows/private-original-relay-synthetic.yml'))
MAX_SOURCE_BYTES = 1_000_000


class HandoffError(ValueError):
    """Fixed public-safe failure, without file paths, key bytes or git output."""


def _require(value, reason):
    if not value: raise HandoffError(reason)


def _safe(function):
    @functools.wraps(function)
    def call(*args, **kwargs):
        try: return function(*args, **kwargs)
        except HandoffError: raise
        except Exception: raise HandoffError('PRIVATE_HANDOFF_REJECTED') from None
    return call


def _json(raw):
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=provenance._pairs,
                          parse_constant=provenance._constant)
    except Exception: raise HandoffError('PRIVATE_HANDOFF_JSON_REJECTED') from None


def _config(path):
    cfg = _json(relay._read(path, 128_000, private=True))
    _require(type(cfg) is dict and set(cfg) == {
        'schema', 'recipient_sha256', 'trusted_code_sha256', 'workflows'}
        and cfg['schema'] == CONFIG_SCHEMA and provenance._hash(cfg['recipient_sha256']),
        'PRIVATE_HANDOFF_CONFIG_REJECTED')
    flows, pins = cfg['workflows'], cfg['trusted_code_sha256']
    _require(type(flows) is dict and 0 < len(flows) <= 2 and set(flows) <= WORKFLOWS
             and type(pins) is dict and len(pins) <= 512
             and REQUIRED_CODE_PATHS | set(flows) <= set(pins), 'PRIVATE_HANDOFF_CONFIG_REJECTED')
    for path, pin in pins.items():
        _require(type(path) is str and (path in REQUIRED_CODE_PATHS | set(flows)
            or re.fullmatch(r'ops/[A-Za-z_][A-Za-z0-9_]{0,127}\.py', path))
            and provenance._hash(pin), 'PRIVATE_HANDOFF_CONFIG_PATH_REJECTED')
    for flow in flows.values():
        _require(type(flow) is dict and set(flow) == {'head_branch', 'allowed_events'}
                 and type(flow['allowed_events']) is list, 'PRIVATE_HANDOFF_CONFIG_REJECTED')
    return cfg


def _git(repository, arguments):
    # No lazy remote fetches, replace refs, hooks, pager or shell interpretation.
    env = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0')
    result = subprocess.run(['git', '--no-replace-objects', '--no-pager', '-C', str(repository),
        '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null', *arguments],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=30, env=env, check=False)
    _require(result.returncode == 0, 'PRIVATE_HANDOFF_SOURCE_UNAVAILABLE')
    return result.stdout


def _code(repository, source, cfg):
    repository = capture._path(repository)
    descriptor = relay._public_parent(repository); os.close(descriptor)
    local_root = Path(__file__).resolve().parents[1]
    _require(not (local_root / 'ops/__init__.py').exists()
             and not (local_root / 'ops/__init__.py').is_symlink()
             and not _git(repository, ['ls-tree', '--name-only', source, '--', 'ops/__init__.py']),
             'PRIVATE_HANDOFF_NAMESPACE_CHANGED')
    for path, expected in sorted(cfg['trusted_code_sha256'].items()):
        object_name = source + ':' + path
        size = _git(repository, ['cat-file', '-s', object_name]).strip()
        _require(len(size) <= 10 and size.isdigit() and 0 < int(size) <= MAX_SOURCE_BYTES,
                 'PRIVATE_HANDOFF_SOURCE_SIZE_LIMIT')
        # The blob belongs to the full immutable source SHA checked above. Its
        # size is bounded before git show captures bytes; replace refs disabled.
        raw = _git(repository, ['show', '--no-textconv', object_name])
        _require(len(raw) == int(size) and hashlib.sha256(raw).hexdigest() == expected,
                 'PRIVATE_HANDOFF_SOURCE_PIN_MISMATCH')
        if path.startswith('ops/'):
            local = relay._read(local_root / path, MAX_SOURCE_BYTES, private=False)
            _require(hashlib.sha256(local).hexdigest() == expected,
                     'PRIVATE_HANDOFF_LOCAL_CODE_PIN_MISMATCH')
        if path == RECIPIENT_PATH:
            _require(hashlib.sha256(raw.decode('ascii').strip().encode('ascii')).hexdigest()
                     == cfg['recipient_sha256'], 'PRIVATE_HANDOFF_RECIPIENT_PIN_MISMATCH')


@_safe
def prepare(*, run_metadata, cipher_metadata, receipt_metadata, cipher_zip, receipt_zip,
            trusted_config, source_repository, identity_file, age_binary, output_dir):
    cfg = _config(trusted_config)
    run = _json(relay._read(run_metadata, 2_000_000, private=False))
    _require(type(run) is dict and provenance._hash(run.get('head_sha'), 40)
             and provenance._positive_int(run.get('id')) and provenance._positive_int(run.get('run_attempt'))
             and run.get('path') in cfg['workflows'], 'PRIVATE_HANDOFF_RUN_REJECTED')
    flow = cfg['workflows'][run['path']]
    expected = provenance.ExpectedRun(source_sha=run['head_sha'], run_id=str(run['id']),
        attempt=str(run['run_attempt']), workflow_path=run['path'], recipient_sha256=cfg['recipient_sha256'],
        head_branch=flow['head_branch'], allowed_events=tuple(flow['allowed_events']))
    _code(source_repository, expected.source_sha, cfg)
    bundle = provenance.verify_bundle(run,
        _json(relay._read(cipher_metadata, 64_000, private=False)),
        relay._read(cipher_zip, provenance.MAX_CIPHERTEXT_ARTIFACT_BYTES, private=False),
        _json(relay._read(receipt_metadata, 64_000, private=False)),
        relay._read(receipt_zip, provenance.MAX_RECEIPT_ARTIFACT_BYTES, private=False), expected=expected)
    destination = capture._path(output_dir)
    _require(destination.name not in ('', '.', '..', '.git'), 'PRIVATE_HANDOFF_OUTPUT_REJECTED')
    parent = capture._open_chain(destination.parent)
    try:
        try: os.stat(destination.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError: pass
        else: raise HandoffError('PRIVATE_HANDOFF_OUTPUT_EXISTS')
        with tempfile.TemporaryDirectory(prefix='football-private-handoff-') as temporary:
            stage = Path(temporary); cipher = stage / 'ciphertext.age'; restored = stage / 'restoredpack'
            relay._write(cipher, bundle.ciphertext)
            pin = bundle.receipt
            context = {key: getattr(expected, key) for key in ('source_sha', 'run_id', 'attempt')}
            decrypted = relay.decrypt(cipher, restored, **context,
                expected_manifest_sha256=pin['manifest_sha256'], expected_archive_sha256=pin['archive_sha256'],
                expected_ciphertext_sha256=pin['ciphertext_sha256'], expected_recipient_sha256=cfg['recipient_sha256'],
                identity_path=identity_file, age_binary=age_binary)
            files, count = archive._source_files(restored, context, pin['manifest_sha256'], None)
            packed = archive._zip(files)
            _require(hashlib.sha256(packed).hexdigest() == pin['archive_sha256']
                     and len(packed) == pin['archive_bytes']
                     and count == pin['capture_count'] == decrypted['capture_count'],
                     'PRIVATE_HANDOFF_ORIGINAL_PIN_MISMATCH')
            report = {**bundle.report, 'schema': 'football-king-private-drive-handoff-v1',
                      'handoff_status': 'PREPARED_NOT_STORED', 'local_code_pins_verified': True,
                      'source_code_pins_verified': True, 'archive_bytes': len(packed),
                      'capture_count': count, 'github_to_drive_connected': False}
            os.mkdir(destination.name, 0o700, dir_fd=parent)
            relay._write(destination / 'original-response-pack.zip', packed)
            shutil.move(str(restored), str(destination / 'restoredpack'))
            relay._write(destination / 'safehandoff-receipt.json',
                         (json.dumps(report, sort_keys=True) + '\n').encode('ascii'))
            return report
    finally: os.close(parent)


class _Parser(argparse.ArgumentParser):
    def error(self, message): raise HandoffError('PRIVATE_HANDOFF_INVALID_ARGUMENTS')


def main(argv=None):
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument('operation', choices=('prepare',))
        for name in ('run-metadata', 'cipher-metadata', 'receipt-metadata', 'cipher-zip', 'receipt-zip',
                     'trusted-config', 'source-repository', 'identity-file', 'age-binary', 'output-dir'):
            parser.add_argument('--' + name, type=Path, required=True)
        args = vars(parser.parse_args(argv)); args.pop('operation')
        print(json.dumps(prepare(**args), sort_keys=True)); return 0
    except Exception as error:
        print(json.dumps({'schema': 'football-king-private-drive-handoff-v1', 'handoff_status': 'REJECTED',
                          'reason': str(error) if isinstance(error, HandoffError) else 'PRIVATE_HANDOFF_REJECTED',
                          'status': 'HOLD', **capture.FLAGS})); return 1


if __name__ == '__main__': raise SystemExit(main())
