"""Private original-response pack and replay; no provider or result authentication.

Only the collector's existing response bytes enter this module. No network,
credentials, public upload, durable transport or certified outcome is supplied.
"""
import argparse
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from urllib.parse import unquote


MAX_CAPTURES = 7
MAX_BODY_BYTES = 5_000_000
MAX_RECEIPT_BYTES = 8_000
MAX_MANIFEST_BYTES = 32_000
MAX_JSON_NODES = 250_000
MAX_SECRET_PERCENT_PASSES = 2
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
RECEIPT_SCHEMA = 'football-king-private-response-receipt-v1'
PACK_SCHEMA = 'football-king-private-response-pack-v1'
FLAGS = {'raw_source_authenticated': False, 'capture_time_authenticated': False,
         'durable_archive_verified': False, 'production_recommendations': 'DISABLED'}


class CaptureError(ValueError):
    """A fixed public-safe error code, without paths, credentials or body text."""


def _require(condition, reason):
    if not condition:
        raise CaptureError(reason)


def _context(source_sha, run_id, attempt):
    _require(type(source_sha) is str and re.fullmatch('[0-9a-f]{40}', source_sha),
             'INVALID_CAPTURE_CONTEXT')
    _require(all(type(v) is str and re.fullmatch('[1-9][0-9]{0,19}', v)
                 for v in (run_id, attempt)), 'INVALID_CAPTURE_CONTEXT')
    return {'source_sha': source_sha, 'run_id': run_id, 'attempt': attempt}


def _path(value):
    try:
        p = Path(value)
    except (TypeError, ValueError):
        raise CaptureError('INVALID_PRIVATE_PATH') from None
    _require('..' not in p.parts and '\0' not in str(p) and len(str(p)) <= 4096,
             'INVALID_PRIVATE_PATH')
    return Path('/', *p.absolute().parts[1:])


def _identity(info):
    return info.st_dev, info.st_ino


def _version(info):
    return (_identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_nlink, stat.S_IMODE(info.st_mode), info.st_uid)


def _no_repository(descriptor):
    try:
        os.stat('.git', dir_fd=descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise CaptureError('PRIVATE_PATH_INSIDE_REPOSITORY')


def _open_chain(path):
    descriptor = os.open(path.anchor, DIRECTORY_FLAGS)
    try:
        _no_repository(descriptor)
        for part in path.parts[1:]:
            before = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
            _require(stat.S_ISDIR(before.st_mode), 'UNSAFE_PRIVATE_DIRECTORY')
            child = os.open(part, DIRECTORY_FLAGS, dir_fd=descriptor)
            if _identity(before) != _identity(os.fstat(child)):
                os.close(child)
                raise CaptureError('PRIVATE_DIRECTORY_CHANGED')
            os.close(descriptor)
            descriptor = child
            _no_repository(descriptor)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _directory_mode(descriptor):
    info = os.fstat(descriptor)
    _require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700
             and info.st_uid == os.getuid(), 'PRIVATE_DIRECTORY_PERMISSIONS')


def _read(descriptor, name, maximum):
    before = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
    _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
             and stat.S_IMODE(before.st_mode) == 0o600 and before.st_uid == os.getuid()
             and 0 < before.st_size <= maximum, 'UNSAFE_PRIVATE_FILE')
    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
    with os.fdopen(child, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        _require(_version(before) == _version(opened), 'PRIVATE_FILE_CHANGED')
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    linked = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
    _require(_version(before) == _version(after) == _version(linked), 'PRIVATE_FILE_CHANGED')
    _require(0 < len(raw) <= maximum, 'PRIVATE_FILE_SIZE_LIMIT')
    return raw


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _unique(items):
    out = {}
    for key, value in items:
        _require(key not in out, 'DUPLICATE_CAPTURE_JSON_KEY')
        out[key] = value
    return out


def _bad_constant(_):
    raise CaptureError('NONFINITE_CAPTURE_JSON')


def _float(value):
    result = float(value)
    _require(math.isfinite(result), 'NONFINITE_CAPTURE_JSON')
    return result


def _parse(raw):
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique,
                          parse_constant=_bad_constant, parse_float=_float)
    except CaptureError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise CaptureError('INVALID_CAPTURE_JSON') from None


def _body(raw, secret=None):
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_BODY_BYTES, 'CAPTURE_BODY_SIZE_LIMIT')
    value = _parse(raw)
    _require(type(value) is list, 'INVALID_CAPTURE_RESPONSE_SHAPE')
    if secret is not None:
        _require(type(secret) is str and 0 < len(secret) <= 4096, 'INVALID_CAPTURE_SECRET_GUARD')
        try:
            encoded_secret = secret.encode('utf-8')
        except UnicodeError:
            raise CaptureError('INVALID_CAPTURE_SECRET_GUARD') from None
        _require(encoded_secret not in raw, 'CAPTURE_CONTAINS_SECRET')
    pending, visited = [value], 0
    while pending:
        visited += 1
        _require(visited <= MAX_JSON_NODES, 'CAPTURE_JSON_NODE_LIMIT')
        item = pending.pop()
        if type(item) is dict:
            pending.extend(item.keys());pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)
        elif type(item) is str and secret is not None:
            _require(secret not in item, 'CAPTURE_CONTAINS_SECRET')
            # Inspect bounded common URL encodings without rewriting stored bytes.
            for _ in range(MAX_SECRET_PERCENT_PASSES):
                decoded = unquote(item)
                if decoded == item:
                    break
                _require(secret not in decoded, 'CAPTURE_CONTAINS_SECRET')
                item = decoded
    return value


def _request(path, params):
    # Import lazily: odds_market's optional capture hook can call this module.
    from ops.odds_market import SPORTS
    if type(path) is str and path == '/sports/':
        _require(params is None or type(params) is dict and not params,
                 'INVALID_PRIVATE_CAPTURE_REQUEST')
        return {}
    _require(type(path) is str and path in {'/sports/'+v+'/odds/' for v in SPORTS.values()},
             'INVALID_PRIVATE_CAPTURE_REQUEST')
    expected = {'regions': 'eu', 'markets': 'h2h', 'oddsFormat': 'decimal', 'dateFormat': 'iso'}
    _require(type(params) is dict and params == expected
             and all(type(k) is str and type(v) is str for k,v in params.items()),
             'INVALID_PRIVATE_CAPTURE_REQUEST')
    return dict(expected)


def _quota(value):
    _require(type(value) is dict and set(value) == {'used', 'remaining', 'last'}
             and all(v is None or type(v) is int and v >= 0 for v in value.values()),
             'INVALID_CAPTURE_QUOTA')
    return dict(value)


def _clock(value):
    _require(isinstance(value, datetime) and value.tzinfo is not None
             and value.utcoffset() == timedelta(0), 'INVALID_CAPTURE_CLOCK')
    return value.astimezone(timezone.utc)


def _stamp(value):
    _require(type(value) is str and 0 < len(value) <= 80, 'INVALID_CAPTURE_CLOCK')
    try:
        parsed = _clock(datetime.fromisoformat(value))
    except (ValueError, TypeError, OverflowError):
        raise CaptureError('INVALID_CAPTURE_CLOCK') from None
    _require(parsed.isoformat() == value, 'INVALID_CAPTURE_CLOCK')
    return parsed


def _encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                       allow_nan=False)+'\n').encode('utf-8')


def _names(index):
    return 'capture-%03d.body.json'%index, 'capture-%03d.receipt.json'%index


def _summary(context, manifest_sha256, count, pinned, *, sealed=False):
    return {'schema': 'football-king-private-response-pack-summary-v1', **context, **FLAGS,
            'status': 'HOLD', 'capture_count': count, 'manifest_sha256': manifest_sha256,
            'manifest_digest_pinned': pinned, 'pack_sealed': True,
            'replay_completed': not sealed, 'certified_case_count': 0,
            'eligible_for_model_scoring': False, 'eligible_for_betting_promotion': False}


class CaptureSession:
    def __init__(self, root: Path, *, source_sha: str, run_id: str, attempt: str):
        self._parent_fd = self._root_fd = None
        self._owned, self._entries, self._last = {}, [], None
        self._context = _context(source_sha, run_id, attempt)
        self._root = _path(root)
        _require(self._root.name not in ('', '.', '..'), 'INVALID_PRIVATE_PATH')
        try:
            self._parent_fd = _open_chain(self._root.parent)
            try:
                os.mkdir(self._root.name, 0o700, dir_fd=self._parent_fd)
            except FileExistsError:
                raise CaptureError('PRIVATE_CAPTURE_DIRECTORY_EXISTS') from None
            before = os.stat(self._root.name, dir_fd=self._parent_fd, follow_symlinks=False)
            self._root_fd = os.open(self._root.name, DIRECTORY_FLAGS, dir_fd=self._parent_fd)
            _require(_identity(before) == _identity(os.fstat(self._root_fd)),
                     'PRIVATE_DIRECTORY_CHANGED')
            self._check_owned()
        except BaseException as exc:
            self.close()
            if isinstance(exc, OSError):
                raise CaptureError('UNSAFE_PRIVATE_CAPTURE_PATH') from None
            raise

    def close(self):
        for descriptor, _, _ in self._owned.values():
            os.close(descriptor)
        self._owned.clear()
        for name in ('_root_fd', '_parent_fd'):
            descriptor = getattr(self, name, None)
            if descriptor is not None:
                os.close(descriptor);setattr(self, name, None)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _check_owned(self):
        _require(self._root_fd is not None and self._parent_fd is not None,
                 'PRIVATE_CAPTURE_SESSION_CLOSED')
        check = _open_chain(self._root.parent)
        try:
            _require(_identity(os.fstat(check)) == _identity(os.fstat(self._parent_fd)),
                     'PRIVATE_DIRECTORY_CHANGED')
        finally:
            os.close(check)
        current = os.stat(self._root.name, dir_fd=self._parent_fd, follow_symlinks=False)
        _require(_identity(current) == _identity(os.fstat(self._root_fd)), 'PRIVATE_DIRECTORY_CHANGED')
        _directory_mode(self._root_fd)
        _require(set(os.listdir(self._root_fd)) == set(self._owned), 'PRIVATE_CAPTURE_CONTENTS_CHANGED')
        for name, (descriptor, version, digest) in self._owned.items():
            info = os.fstat(descriptor)
            linked = os.stat(name, dir_fd=self._root_fd, follow_symlinks=False)
            _require(_version(info) == version == _version(linked), 'PRIVATE_FILE_CHANGED')
            _require(_digest(os.pread(descriptor, info.st_size + 1, 0)) == digest,
                     'PRIVATE_FILE_CHANGED')

    def check_request(self, path, params=None):
        """Validate before GET; return a detached canonical, key-free params copy."""
        try:
            self._check_owned()
        except OSError:
            raise CaptureError('UNSAFE_PRIVATE_CAPTURE_PATH') from None
        _require(len(self._entries) < MAX_CAPTURES, 'PRIVATE_CAPTURE_COUNT_LIMIT')
        return _request(path, params)

    def _create(self, name, raw):
        descriptor = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                             | os.O_NONBLOCK, 0o600, dir_fd=self._root_fd)
        try:
            with os.fdopen(os.dup(descriptor), 'wb') as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
            info = os.fstat(descriptor)
            _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                     and stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == os.getuid(),
                     'UNSAFE_PRIVATE_FILE')
            self._owned[name] = (descriptor, _version(info), _digest(raw))
        except BaseException:
            os.close(descriptor)
            raise

    @property
    def last_receipt(self):
        return copy.deepcopy(self._last)

    def record(self, raw: bytes, *, path: str, params=None, quota, requested, completed, secret: str):
        params = self.check_request(path, params)
        _body(raw, secret)
        q = _quota(quota)
        start, end = _clock(requested), _clock(completed)
        _require(start <= end, 'INVALID_CAPTURE_TIME_ORDER')
        index = len(self._entries)
        body_name, receipt_name = _names(index)
        receipt = {'schema': RECEIPT_SCHEMA, **self._context, **FLAGS, 'capture_id': index,
                   'endpoint_path': path, 'params': params, 'quota': q,
                   'requested_utc': start.isoformat(), 'completed_utc': end.isoformat(),
                   'raw_file': body_name, 'raw_sha256': _digest(raw), 'raw_bytes': len(raw)}
        encoded = _encode(receipt)
        _require(len(encoded) <= MAX_RECEIPT_BYTES, 'CAPTURE_RECEIPT_SIZE_LIMIT')
        _require(secret.encode('utf-8') not in encoded, 'CAPTURE_CONTAINS_SECRET')
        try:
            self._create(body_name, raw)
            self._create(receipt_name, encoded)
            self._check_owned()
        except OSError:
            self.close()
            raise CaptureError('PRIVATE_CAPTURE_WRITE_FAILED') from None
        except BaseException:
            self.close()
            raise
        self._entries.append({'capture_id': index, 'raw_file': body_name,
                              'raw_sha256': _digest(raw), 'raw_bytes': len(raw),
                              'receipt_file': receipt_name, 'receipt_sha256': _digest(encoded),
                              'receipt_bytes': len(encoded)})
        self._last = receipt
        return copy.deepcopy(receipt)

    def seal(self):
        try:
            self._check_owned()
            manifest = {'schema': PACK_SCHEMA, **self._context, **FLAGS,
                        'capture_count': len(self._entries), 'captures': self._entries}
            raw = _encode(manifest)
            _require(len(raw) <= MAX_MANIFEST_BYTES, 'CAPTURE_MANIFEST_SIZE_LIMIT')
            self._create('manifest.json', raw)
            self._check_owned()
            result = _summary(self._context, _digest(raw), len(self._entries), False, sealed=True)
        except OSError:
            raise CaptureError('PRIVATE_CAPTURE_SEAL_FAILED') from None
        finally:
            self.close()
        return result


def _load(root, *, source_sha, run_id, attempt, expected_manifest_sha256=None):
    context = _context(source_sha, run_id, attempt)
    _require(expected_manifest_sha256 is None or type(expected_manifest_sha256) is str
             and re.fullmatch('[0-9a-f]{64}', expected_manifest_sha256), 'INVALID_MANIFEST_PIN')
    root = _path(root)
    descriptor = None
    try:
        descriptor = _open_chain(root);_directory_mode(descriptor)
        raw = _read(descriptor, 'manifest.json', MAX_MANIFEST_BYTES)
        digest = _digest(raw)
        _require(expected_manifest_sha256 is None or digest == expected_manifest_sha256,
                 'PRIVATE_MANIFEST_PIN_MISMATCH')
        manifest = _parse(raw)
        keys = {'schema', *context, *FLAGS, 'capture_count', 'captures'}
        _require(type(manifest) is dict and set(manifest) == keys
                 and manifest['schema'] == PACK_SCHEMA
                 and all(manifest[k] == v and type(manifest[k]) is type(v)
                         for k,v in {**context, **FLAGS}.items()), 'INVALID_PRIVATE_MANIFEST')
        count, entries = manifest['capture_count'], manifest['captures']
        _require(type(count) is int and 0 <= count <= MAX_CAPTURES
                 and type(entries) is list and len(entries) == count, 'PRIVATE_CAPTURE_COUNT_LIMIT')
        expected, records, before = {'manifest.json'}, [], {'manifest.json': raw}
        for index, entry in enumerate(entries):
            body_name, receipt_name = _names(index)
            _require(type(entry) is dict and set(entry) == {'capture_id','raw_file','raw_sha256',
                     'raw_bytes','receipt_file','receipt_sha256','receipt_bytes'}
                     and type(entry['capture_id']) is int and entry['capture_id'] == index
                     and entry['raw_file'] == body_name and entry['receipt_file'] == receipt_name,
                     'INVALID_PRIVATE_MANIFEST_ENTRY')
            body = _read(descriptor, body_name, MAX_BODY_BYTES)
            receipt_raw = _read(descriptor, receipt_name, MAX_RECEIPT_BYTES)
            _require(type(entry['raw_bytes']) is int and entry['raw_bytes'] == len(body)
                     and type(entry['receipt_bytes']) is int and entry['receipt_bytes'] == len(receipt_raw)
                     and entry['raw_sha256'] == _digest(body)
                     and entry['receipt_sha256'] == _digest(receipt_raw), 'PRIVATE_CAPTURE_DIGEST_MISMATCH')
            receipt = _parse(receipt_raw)
            rkeys = {'schema', *context, *FLAGS, 'capture_id','endpoint_path','params','quota',
                     'requested_utc','completed_utc','raw_file','raw_sha256','raw_bytes'}
            _require(type(receipt) is dict and set(receipt) == rkeys and receipt['schema'] == RECEIPT_SCHEMA
                     and all(receipt[k] == v and type(receipt[k]) is type(v)
                             for k,v in {**context, **FLAGS}.items())
                     and type(receipt['capture_id']) is int and receipt['capture_id'] == index
                     and receipt['raw_file'] == body_name and receipt['raw_sha256'] == _digest(body)
                     and type(receipt['raw_bytes']) is int and receipt['raw_bytes'] == len(body),
                     'INVALID_PRIVATE_CAPTURE_RECEIPT')
            _require(type(receipt['params']) is dict
                     and _request(receipt['endpoint_path'], receipt['params']) == receipt['params'],
                     'INVALID_PRIVATE_CAPTURE_RECEIPT')
            _quota(receipt['quota'])
            _require(_stamp(receipt['requested_utc']) <= _stamp(receipt['completed_utc']),
                     'INVALID_CAPTURE_TIME_ORDER')
            _body(body)
            records.append({'receipt': receipt, 'raw': body})
            before[body_name], before[receipt_name] = body, receipt_raw
            expected.update((body_name, receipt_name))
        _require(set(os.listdir(descriptor)) == expected, 'PRIVATE_CAPTURE_FILE_ALLOWLIST')
        # Reject observed substitution even after a successfully parsed first read.
        for name, original in before.items():
            limit = MAX_MANIFEST_BYTES if name == 'manifest.json' else (
                MAX_BODY_BYTES if name.endswith('.body.json') else MAX_RECEIPT_BYTES)
            _require(_read(descriptor, name, limit) == original, 'PRIVATE_CAPTURE_CHANGED_DURING_REPLAY')
        _require(set(os.listdir(descriptor)) == expected, 'PRIVATE_CAPTURE_FILE_ALLOWLIST')
        _directory_mode(descriptor)
        check = _open_chain(root)
        try:
            _require(_identity(os.fstat(check)) == _identity(os.fstat(descriptor)),
                     'PRIVATE_DIRECTORY_CHANGED')
        finally:
            os.close(check)
        return records, digest, context
    except OSError:
        raise CaptureError('MISSING_UNSAFE_OR_CHANGED_PRIVATE_PACK') from None
    finally:
        if descriptor is not None:os.close(descriptor)


def replay_records(root, *, source_sha, run_id, attempt, expected_manifest_sha256=None):
    """Private in-memory records; never print or upload their original bodies."""
    return _load(root, source_sha=source_sha, run_id=run_id, attempt=attempt,
                 expected_manifest_sha256=expected_manifest_sha256)[0]


def replay(root, *, source_sha, run_id, attempt, expected_manifest_sha256=None):
    records, digest, context = _load(root, source_sha=source_sha, run_id=run_id, attempt=attempt,
                                   expected_manifest_sha256=expected_manifest_sha256)
    return _summary(context, digest, len(records), expected_manifest_sha256 is not None)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CaptureError('INVALID_ARGUMENTS')


def main(argv=None):
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument('--private-dir', type=Path, required=True)
        for name in ('source-sha','run-id','attempt'):
            parser.add_argument('--'+name, required=True)
        parser.add_argument('--expected-manifest-sha256')
        args = parser.parse_args(argv)
        result = replay(args.private_dir, source_sha=args.source_sha, run_id=args.run_id,
                        attempt=args.attempt, expected_manifest_sha256=args.expected_manifest_sha256)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        code = str(exc) if isinstance(exc, CaptureError) else 'PRIVATE_CAPTURE_REPLAY_REJECTED'
        print(json.dumps({'status':'HOLD','replay_completed':False,'reason':code,**FLAGS}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
