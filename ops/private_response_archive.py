"""Opt-in private GitHub original-pack transport; no source certification.

Create-only remote writes and pinned readback detect observed changes. Repository
administrators can later alter visibility or delete data; no WORM guarantee is
made. Tokens and destination identities are never public report fields.
"""
import argparse
import base64
from dataclasses import dataclass
import functools
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from urllib.error import HTTPError
from urllib.parse import quote, unquote
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

from ops import private_response_capture as capture

MAX_ARCHIVE_BYTES = 36_000_000
MAX_METADATA_BYTES = 64_000
MAX_BLOB_JSON_BYTES = MAX_ARCHIVE_BYTES * 2 + MAX_METADATA_BYTES
MAX_FILES = 15
ORIGIN = 'https://api.github.com'
API_VERSION = '2026-03-10'
CONFIG_NAMES = ('PRIVATE_ARCHIVE_REPOSITORY', 'PRIVATE_ARCHIVE_REPOSITORY_ID',
                'PRIVATE_ARCHIVE_TOKEN')


class ArchiveError(ValueError):
    """Fixed error codes only; never include paths, tokens or server bodies."""


def _require(condition, code):
    if not condition:
        raise ArchiveError(code)


def _safe_entry(function):
    @functools.wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ArchiveError:
            raise
        except Exception:
            raise ArchiveError('PRIVATE_ARCHIVE_OPERATION_REJECTED') from None
    return call


@dataclass(frozen=True, repr=False)
class Configuration:
    repository: str
    repository_id: int
    token: str

    def __post_init__(self):
        _require(type(self.repository) is str and type(self.token) is str
                 and type(self.repository_id) is int and 1 <= self.repository_id < 10**20,
                 'PRIVATE_ARCHIVE_CONFIGURATION_INVALID')
        parts = self.repository.split('/')
        _require(len(parts) == 2 and all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', v)
                 and '..' not in v for v in parts), 'PRIVATE_ARCHIVE_CONFIGURATION_INVALID')
        _require(0 < len(self.token) <= 4096 and all(33 <= ord(c) <= 126 for c in self.token)
                 and self.token not in self.repository, 'PRIVATE_ARCHIVE_CONFIGURATION_INVALID')


@_safe_entry
def configuration(environ=None, *, required=False):
    environ = os.environ if environ is None else environ
    values = [environ.get(name, '') for name in CONFIG_NAMES]
    if not any(values):
        _require(not required, 'PRIVATE_ARCHIVE_CONFIGURATION_MISSING')
        return None
    _require(all(type(v) is str and v for v in values), 'PRIVATE_ARCHIVE_CONFIGURATION_INVALID')
    repository, identity, token = values
    _require(re.fullmatch(r'[1-9][0-9]{0,19}', identity), 'PRIVATE_ARCHIVE_CONFIGURATION_INVALID')
    return Configuration(repository, int(identity), token)


def _hash(value, length):
    _require(type(value) is str and re.fullmatch('[0-9a-f]{%d}' % length, value),
             'PRIVATE_ARCHIVE_INVALID_PIN')
    return value


def _context(source_sha, run_id, attempt, manifest_pin):
    context = capture._context(source_sha, run_id, attempt)
    _hash(manifest_pin, 64)
    return context


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _blob_digest(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()


def _remote_path(context, pin):
    return 'captures/v1/{source_sha}/{run_id}-{attempt}/{pin}.zip'.format(**context, pin=pin)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        response.close()
        raise ArchiveError('PRIVATE_ARCHIVE_REDIRECT_REJECTED')


def default_opener():
    # Keep inherited TLS/proxy configuration; refuse redirects before forwarding auth.
    return build_opener(_NoRedirect()).open


class _Client:
    def __init__(self, config, opener):
        _require(type(config) is Configuration, 'PRIVATE_ARCHIVE_CONFIGURATION_INVALID')
        config.__post_init__()
        self.config = config
        self.opener = default_opener() if opener is None else opener
        self.base = '/repos/' + config.repository

    def request(self, method, path, *, data=None, maximum=MAX_METADATA_BYTES, expected=200,
                accept='application/vnd.github+json'):
        _require(path.startswith(self.base + '/') or path == self.base,
                 'PRIVATE_ARCHIVE_REQUEST_REJECTED')
        url = ORIGIN + path
        _require(all(self.config.token not in value for value in (url, unquote(url), unquote(unquote(url)))),
                 'PRIVATE_ARCHIVE_REQUEST_REJECTED')
        payload = None if data is None else json.dumps(data, separators=(',', ':'), allow_nan=False).encode()
        _require(payload is None or len(payload) <= MAX_BLOB_JSON_BYTES,
                 'PRIVATE_ARCHIVE_REQUEST_SIZE_LIMIT')
        request = Request(url, data=payload, method=method,
                          headers={'Authorization': 'Bearer ' + self.config.token,
                                   'Accept': accept, 'X-GitHub-Api-Version': API_VERSION,
                                   'Content-Type': 'application/json',
                                   'User-Agent': 'FootballKingPrivateArchive/1.0'})
        try:
            with self.opener(request, timeout=60) as response:
                _require(type(response.status) is int and response.status == expected
                         and response.geturl() == request.full_url,
                         'PRIVATE_ARCHIVE_HTTP_REJECTED')
                raw = response.read(maximum + 1)
            _require(type(raw) is bytes and 0 < len(raw) <= maximum,
                     'PRIVATE_ARCHIVE_RESPONSE_SIZE_LIMIT')
            return capture._parse(raw)
        except ArchiveError:
            raise
        except HTTPError as error:
            error.close()
            raise ArchiveError('PRIVATE_ARCHIVE_HTTP_REJECTED') from None
        except Exception:
            raise ArchiveError('PRIVATE_ARCHIVE_HTTP_REJECTED') from None

    def target(self):
        data = self.request('GET', self.base)
        _require(type(data) is dict and type(data.get('id')) is int
                 and data['id'] == self.config.repository_id
                 and data.get('full_name') == self.config.repository
                 and data.get('private') is True and data.get('visibility') == 'private'
                 and data.get('archived') is False and data.get('disabled') is False,
                 'PRIVATE_ARCHIVE_TARGET_REJECTED')
        branch = data.get('default_branch')
        _require(type(branch) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,199}', branch)
                 and '..' not in branch and '//' not in branch
                 and not branch.endswith(('/', '.', '.lock')), 'PRIVATE_ARCHIVE_BRANCH_REJECTED')
        return branch

    def initialized_branch(self, branch):
        ref = self.request('GET', self.base + '/git/ref/heads/' + quote(branch, safe=''))
        _require(type(ref) is dict and ref.get('ref') == 'refs/heads/' + branch
                 and type(ref.get('object')) is dict and ref['object'].get('type') == 'commit',
                 'PRIVATE_ARCHIVE_BRANCH_REJECTED')
        _hash(ref['object'].get('sha'), 40)

    def readback(self, context, pin, blob, commit, archive_digest):
        path = _remote_path(context, pin)
        entry = self.request('GET', self.base + '/contents/' + path + '?ref=' + commit,
                             accept='application/vnd.github.object+json')
        _require(type(entry) is dict and entry.get('type') == 'file'
                 and entry.get('path') == path and entry.get('sha') == blob
                 and type(entry.get('size')) is int and 0 < entry['size'] <= MAX_ARCHIVE_BYTES,
                 'PRIVATE_ARCHIVE_COMMIT_REACHABILITY_REJECTED')
        response = self.request('GET', self.base + '/git/blobs/' + blob,
                                maximum=MAX_BLOB_JSON_BYTES)
        _require(type(response) is dict and response.get('sha') == blob
                 and response.get('encoding') == 'base64' and type(response.get('size')) is int
                 and response['size'] == entry['size'] and type(response.get('content')) is str
                 and len(response['content']) <= MAX_BLOB_JSON_BYTES,
                 'PRIVATE_ARCHIVE_BLOB_REJECTED')
        encoded_size = 4 * ((entry['size'] + 2) // 3)
        _require(len(response['content']) <= encoded_size + encoded_size // 60 + 4,
                 'PRIVATE_ARCHIVE_BLOB_REJECTED')
        encoded = response['content'].replace('\n', '')
        _require(len(encoded) == encoded_size, 'PRIVATE_ARCHIVE_BLOB_REJECTED')
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception:
            raise ArchiveError('PRIVATE_ARCHIVE_BLOB_REJECTED') from None
        _require(0 < len(raw) <= MAX_ARCHIVE_BYTES and len(raw) == entry['size']
                 and _blob_digest(raw) == blob and _digest(raw) == archive_digest,
                 'PRIVATE_ARCHIVE_BLOB_DIGEST_MISMATCH')
        return raw


def _limit(name):
    if name == 'manifest.json':
        return capture.MAX_MANIFEST_BYTES
    if re.fullmatch(r'capture-00[0-6]\.body\.json', name):
        return capture.MAX_BODY_BYTES
    if re.fullmatch(r'capture-00[0-6]\.receipt\.json', name):
        return capture.MAX_RECEIPT_BYTES
    raise ArchiveError('PRIVATE_ARCHIVE_FILE_ALLOWLIST')


def _secret_guard(files, token):
    for name, raw in files.items():
        # Existing decoder covers raw, JSON escapes and two bounded URL passes.
        capture._body(raw if name.endswith('.body.json') else b'[' + raw + b']', secret=token)


def _install(root, files, context, pin, *, session=None):
    session = capture.CaptureSession(root, **context) if session is None else session
    try:
        for name in sorted(files):
            session._create(name, files[name])
        session._check_owned()
    finally:
        session.close()
    return capture.replay(root, **context, expected_manifest_sha256=pin)['capture_count']


def _validate_copy(files, context, pin):
    with tempfile.TemporaryDirectory(prefix='football-private-archive-') as temporary:
        return _install(Path(temporary) / 'pack', files, context, pin)


def _source_files(root, context, pin, token):
    records = capture.replay_records(root, **context, expected_manifest_sha256=pin)
    names = {'manifest.json'}
    for index in range(len(records)):
        names.update(capture._names(index))
    path = capture._path(root)
    descriptor = capture._open_chain(path)
    try:
        capture._directory_mode(descriptor)
        _require(set(os.listdir(descriptor)) == names, 'PRIVATE_ARCHIVE_FILE_ALLOWLIST')
        files = {name: capture._read(descriptor, name, _limit(name)) for name in sorted(names)}
        _require(set(os.listdir(descriptor)) == names, 'PRIVATE_ARCHIVE_FILE_ALLOWLIST')
        check = capture._open_chain(path)
        try:
            _require(capture._identity(os.fstat(check)) == capture._identity(os.fstat(descriptor)),
                     'PRIVATE_ARCHIVE_SOURCE_CHANGED')
        finally:
            os.close(check)
    finally:
        os.close(descriptor)
    _secret_guard(files, token)
    count = _validate_copy(files, context, pin)
    return files, count


def _zip(files):
    _require(type(files) is dict and 1 <= len(files) <= MAX_FILES and 'manifest.json' in files,
             'PRIVATE_ARCHIVE_FILE_ALLOWLIST')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for name in sorted(files):
            raw = files[name]
            _require(type(raw) is bytes and 0 < len(raw) <= _limit(name),
                     'PRIVATE_ARCHIVE_FILE_SIZE_LIMIT')
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, raw)
    raw = stream.getvalue()
    _require(0 < len(raw) <= MAX_ARCHIVE_BYTES, 'PRIVATE_ARCHIVE_SIZE_LIMIT')
    return raw


def _unzip(raw):
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_ARCHIVE_BYTES,
             'PRIVATE_ARCHIVE_SIZE_LIMIT')
    files = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        _require(1 <= len(infos) <= MAX_FILES and not archive.comment,
                 'PRIVATE_ARCHIVE_FILE_ALLOWLIST')
        for info in infos:
            _require(info.filename not in files and not info.is_dir()
                     and info.compress_type == zipfile.ZIP_STORED
                     and info.compress_size == info.file_size and info.flag_bits == 0
                     and not info.extra and not info.comment and info.create_system == 3
                     and stat.S_ISREG(info.external_attr >> 16)
                     and stat.S_IMODE(info.external_attr >> 16) == 0o600
                     and 0 < info.file_size <= _limit(info.filename),
                     'PRIVATE_ARCHIVE_ZIP_LAYOUT_REJECTED')
            files[info.filename] = archive.read(info)
    _require(_zip(files) == raw, 'PRIVATE_ARCHIVE_ZIP_LAYOUT_REJECTED')
    return files


def _report(operation, context, pin, blob, commit, archive_digest, count):
    return {'schema': 'football-king-private-response-archive-v1', 'operation': operation,
            'archive_status': 'REMOTE_READBACK_VERIFIED', 'remote_roundtrip_completed': True,
            **context, 'manifest_sha256': pin, 'archive_blob_sha': blob,
            'archive_commit_sha': commit, 'archive_sha256': archive_digest,
            'capture_count': count, **capture.FLAGS, 'status': 'HOLD', 'certified_case_count': 0,
            'eligible_for_model_scoring': False, 'eligible_for_betting_promotion': False}


@_safe_entry
def upload(private_dir, *, source_sha, run_id, attempt, expected_manifest_sha256, config, opener=None):
    context = _context(source_sha, run_id, attempt, expected_manifest_sha256)
    _require(type(config) is Configuration, 'PRIVATE_ARCHIVE_CONFIGURATION_INVALID')
    files, count = _source_files(private_dir, context, expected_manifest_sha256, config.token)
    raw = _zip(files)
    blob, archive_digest = _blob_digest(raw), _digest(raw)
    client = _Client(config, opener)
    branch = client.target()
    client.initialized_branch(branch)
    _require(client.target() == branch, 'PRIVATE_ARCHIVE_TARGET_CHANGED')
    response = client.request('PUT', client.base + '/contents/' + _remote_path(context, expected_manifest_sha256),
                              data={'message': 'Archive private response pack ' + expected_manifest_sha256,
                                    'content': base64.b64encode(raw).decode('ascii'), 'branch': branch}, expected=201)
    _require(type(response) is dict and type(response.get('content')) is dict
             and response['content'].get('sha') == blob and type(response.get('commit')) is dict,
             'PRIVATE_ARCHIVE_WRITE_RECEIPT_REJECTED')
    commit = _hash(response['commit'].get('sha'), 40)
    restored = client.readback(context, expected_manifest_sha256, blob, commit, archive_digest)
    _require(client.target() == branch, 'PRIVATE_ARCHIVE_TARGET_CHANGED')
    copied = _unzip(restored)
    _secret_guard(copied, config.token)
    _require(_validate_copy(copied, context, expected_manifest_sha256) == count,
             'PRIVATE_ARCHIVE_REPLAY_MISMATCH')
    return _report('upload', context, expected_manifest_sha256, blob, commit, archive_digest, count)


@_safe_entry
def restore(private_dir, *, source_sha, run_id, attempt, expected_manifest_sha256,
            expected_blob_sha, expected_commit_sha, expected_archive_sha256, config, opener=None):
    context = _context(source_sha, run_id, attempt, expected_manifest_sha256)
    blob, commit, archive_digest = (_hash(expected_blob_sha, 40), _hash(expected_commit_sha, 40),
                                    _hash(expected_archive_sha256, 64))
    session = capture.CaptureSession(Path(private_dir), **context)
    try:
        client = _Client(config, opener)
        branch = client.target()
        client.initialized_branch(branch)
        raw = client.readback(context, expected_manifest_sha256, blob, commit, archive_digest)
        _require(client.target() == branch, 'PRIVATE_ARCHIVE_TARGET_CHANGED')
        files = _unzip(raw)
        _secret_guard(files, config.token)
        count = _install(private_dir, files, context, expected_manifest_sha256, session=session)
    finally:
        session.close()
    return _report('restore', context, expected_manifest_sha256, blob, commit, archive_digest, count)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ArchiveError('PRIVATE_ARCHIVE_INVALID_ARGUMENTS')


def main(argv=None):
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument('operation', choices=('upload', 'restore'))
        parser.add_argument('--private-dir', required=True, type=Path)
        for name in ('source-sha', 'run-id', 'attempt', 'expected-manifest-sha256'):
            parser.add_argument('--' + name, required=True)
        for name in ('expected-blob-sha', 'expected-commit-sha', 'expected-archive-sha256'):
            parser.add_argument('--' + name)
        args = parser.parse_args(argv)
        _context(args.source_sha, args.run_id, args.attempt, args.expected_manifest_sha256)
        if args.operation == 'upload':
            _require(all(v is None for v in (args.expected_blob_sha, args.expected_commit_sha,
                                            args.expected_archive_sha256)), 'PRIVATE_ARCHIVE_INVALID_ARGUMENTS')
        config = configuration(required=args.operation == 'restore')
        if config is None:
            print(json.dumps({'archive_status': 'NOT_CONFIGURED', 'remote_roundtrip_completed': False,
                              'status': 'HOLD', **capture.FLAGS}))
            return 0
        options = dict(source_sha=args.source_sha, run_id=args.run_id, attempt=args.attempt,
                       expected_manifest_sha256=args.expected_manifest_sha256, config=config)
        if args.operation == 'restore':
            report = restore(args.private_dir, **options, expected_blob_sha=args.expected_blob_sha,
                             expected_commit_sha=args.expected_commit_sha,
                             expected_archive_sha256=args.expected_archive_sha256)
        else:
            report = upload(args.private_dir, **options)
            output = os.environ.get('GITHUB_OUTPUT')
            if output:
                with open(output, 'a', encoding='utf-8') as stream:
                    for name in ('blob_sha', 'commit_sha', 'sha256'):
                        stream.write('private_archive_' + name + '=' + report['archive_' + name] + '\n')
    except Exception as error:
        code = str(error) if isinstance(error, ArchiveError) else 'PRIVATE_ARCHIVE_OPERATION_REJECTED'
        print(json.dumps({'archive_status': 'REJECTED', 'reason': code,
                          'remote_roundtrip_completed': False, 'status': 'HOLD', **capture.FLAGS}))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
