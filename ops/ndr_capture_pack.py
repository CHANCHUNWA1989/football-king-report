"""Bound and replay exact NDR capture bytes without authenticating results.

The deterministic tar is a provenance subject for the controlled capture job.
Content verification replays the local parsers; it does not authenticate NDR,
the displayed result period, kickoff, independent outcomes or model eligibility.
No tar member is ever extracted to a path supplied by the archive.
"""
import argparse
import hashlib
import io
import json
import math
import os
import re
import stat
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ops import ndr_completion_collector as collector
from ops.ndr_completion_observations import parse_detail
from ops.ndr_result_observations import MAX_MANIFEST_BYTES, _checked_path, observe
from ops.shadow_external_evidence_collector import SOURCES as INDEX_SOURCES

NDR_CAPTURE_FILENAME = 'ndr-capture.tar'
MAX_CAPTURE_BYTES = 16_000_000
MAX_FILE_BYTES = 3_000_000
MAX_MEMBERS = 7
DETAIL_NAME = re.compile(r'ndr-detail-([1-9][0-9]{0,9})\.html\Z')
UTC_TIME = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)\Z')
BASE_NAMES = ('index-manifest.json', 'ndr.html', 'completion-manifest.json', 'report.json')
REQUIRED_NAMES = frozenset(BASE_NAMES) - {'ndr.html'}
FETCH_REASONS = frozenset({
    'INVALID_NDR_DETAIL_URL', 'NON_200_NDR_DETAIL_RESPONSE',
    'UNEXPECTED_NDR_DETAIL_FINAL_URL', 'NON_HTML_NDR_DETAIL_RESPONSE',
    'INVALID_OR_OVERSIZED_NDR_DETAIL_RESPONSE', 'NDR_DETAIL_FETCH_FAILED',
})


def _utc(value, reason='INVALID_NDR_CAPTURE_TIME'):
    if isinstance(value, str):
        if not UTC_TIME.fullmatch(value):
            raise ValueError(reason)
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError(reason) from exc
    if (not isinstance(value, datetime) or value.tzinfo is None
            or value.utcoffset() is None or value.utcoffset().total_seconds() != 0):
        raise ValueError(reason)
    return value


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('DUPLICATE_NDR_CAPTURE_JSON_KEY')
            result[key] = value
        return result

    def nonfinite(_):
        raise ValueError('NONFINITE_NDR_CAPTURE_JSON')

    def floating(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError('NONFINITE_NDR_CAPTURE_JSON')
        return parsed

    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                           parse_constant=nonfinite, parse_float=floating)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('INVALID_NDR_CAPTURE_JSON') from exc
    if not isinstance(value, dict):
        raise ValueError('INVALID_NDR_CAPTURE_JSON_OBJECT')
    return value


def _same(actual, expected, reason):
    # JSON equality is typed: Python's True == 1 must never satisfy counts or flags.
    try:
        options = {'sort_keys': True, 'separators': (',', ':'), 'allow_nan': False}
        equal = json.dumps(actual, **options) == json.dumps(expected, **options)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ValueError(reason) from exc
    if not equal:
        raise ValueError(reason)


def _names(files):
    return [name for name in BASE_NAMES if name in files] + sorted(name for name in files if DETAIL_NAME.fullmatch(name))


def _tar(files):
    # Bound serialization before allocating its output buffer.
    size = sum(512 + ((len(body) + 511) // 512) * 512 for body in files.values()) + 1024
    if ((size + 10239) // 10240) * 10240 > MAX_CAPTURE_BYTES:
        raise ValueError('OVERSIZED_NDR_CAPTURE_CONTENT')
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name in _names(files):
            item = tarfile.TarInfo(name)
            item.uid = item.gid = item.mtime = 0
            item.mode, item.size = 0o600, len(files[name])
            item.uname = item.gname = ''
            archive.addfile(item, io.BytesIO(files[name]))
    return stream.getvalue()


def _members(raw):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_CAPTURE_BYTES:
        raise ValueError('INVALID_OR_OVERSIZED_NDR_CAPTURE')
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
            members = archive.getmembers()
            if not 3 <= len(members) <= MAX_MEMBERS:
                raise ValueError('INVALID_NDR_CAPTURE_MEMBER_COUNT')
            files, total = {}, 0
            for member in members:
                name = member.name
                if (name not in BASE_NAMES and not DETAIL_NAME.fullmatch(name)) or name in files:
                    raise ValueError('INVALID_OR_DUPLICATE_NDR_CAPTURE_MEMBER')
                if (member.type != tarfile.REGTYPE or member.pax_headers or member.linkname
                        or member.uid != 0 or member.gid != 0 or member.mtime != 0
                        or member.mode != 0o600 or member.uname or member.gname):
                    raise ValueError('INVALID_NDR_CAPTURE_MEMBER_METADATA')
                maximum = MAX_MANIFEST_BYTES if name == 'index-manifest.json' else MAX_FILE_BYTES
                if not 0 < member.size <= maximum:
                    raise ValueError('INVALID_NDR_CAPTURE_MEMBER_SIZE')
                total += member.size
                if total > MAX_CAPTURE_BYTES:
                    raise ValueError('OVERSIZED_NDR_CAPTURE_CONTENT')
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError('UNREADABLE_NDR_CAPTURE_MEMBER')
                with source:
                    body = source.read(maximum + 1)
                if len(body) != member.size:
                    raise ValueError('TRUNCATED_NDR_CAPTURE_MEMBER')
                files[name] = body
    except (tarfile.TarError, OSError, EOFError, OverflowError) as exc:
        raise ValueError('INVALID_NDR_CAPTURE_TAR') from exc
    if not REQUIRED_NAMES <= set(files):
        raise ValueError('MISSING_NDR_CAPTURE_MEMBER')
    # One canonical representation also rejects hidden extensions, nonzero
    # padding, concatenated archives, leading/trailing bytes and alternative order.
    if raw != _tar(files):
        raise ValueError('NONCANONICAL_NDR_CAPTURE_TAR')
    return files


def _manifest(report):
    return {
        'schema': 'football-king-ndr-completion-raw-evidence-v1',
        'captured_utc': report['captured_utc'], 'status': 'HOLD',
        'production_recommendations': 'DISABLED', 'independently_verified': False,
        'eligible_for_model_scoring': False, 'source_index': report['source_index'],
        'max_requests': collector.MAX_REQUESTS,
        'requests_attempted': report['requests_attempted'], 'sources': report['sources'],
    }


def _index_manifest(manifest):
    # Preserve the original collector bytes, but recognize its complete shape so
    # unused fields cannot smuggle authenticated-result or promotion claims.
    keys = {'schema', 'captured_utc', 'status', 'independently_verified',
            'eligible_for_model_scoring', 'production_recommendations', 'sources'}
    if set(manifest) != keys:
        raise ValueError('INVALID_NDR_CAPTURE_INDEX_MANIFEST_SHAPE')
    sources = manifest.get('sources')
    if not isinstance(sources, list) or len(sources) > 2:
        raise ValueError('INVALID_NDR_CAPTURE_INDEX_SOURCES')
    seen = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError('INVALID_NDR_CAPTURE_INDEX_SOURCE')
        provider = source.get('provider')
        if not isinstance(provider, str) or provider not in INDEX_SOURCES or provider in seen:
            raise ValueError('INVALID_OR_DUPLICATE_NDR_CAPTURE_INDEX_PROVIDER')
        seen.add(provider)
        if source.get('source_url') != INDEX_SOURCES[provider]:
            raise ValueError('INVALID_NDR_CAPTURE_INDEX_SOURCE_URL')
        base = {'provider', 'source_url', 'status'}
        if source.get('status') == 'ERROR':
            error_type = source.get('error_type')
            if (set(source) != base | {'error_type'} or not isinstance(error_type, str)
                    or not re.fullmatch(r'[A-Za-z][A-Za-z0-9]{0,63}', error_type)):
                raise ValueError('INCONSISTENT_NDR_INDEX_SOURCE_FAILURE')
            continue
        required = base | {'raw_file', 'raw_sha256', 'bytes', 'http_status', 'content_type'}
        if set(source) != required or source.get('status') != 'FETCHED_UNVERIFIED':
            raise ValueError('INVALID_NDR_CAPTURE_INDEX_SOURCE_SHAPE')
        content_type = source.get('content_type')
        digest = source.get('raw_sha256')
        if (source.get('raw_file') != provider.lower() + '.html'
                or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)
                or type(source.get('bytes')) is not int or not 0 < source['bytes'] <= MAX_FILE_BYTES
                or type(source.get('http_status')) is not int or source['http_status'] != 200
                or not isinstance(content_type, str)
                or content_type.split(';', 1)[0].strip().lower() not in ('text/html', 'application/xhtml+xml')):
            raise ValueError('INVALID_NDR_CAPTURE_INDEX_SOURCE_METADATA')


def _replay(files, *, current, witness):
    manifest = _json(files['index-manifest.json'])
    report = _json(files['report.json'])
    completion_manifest = _json(files['completion-manifest.json'])
    _index_manifest(manifest)
    index_time = _utc(manifest.get('captured_utc'))
    started = _utc(report.get('captured_utc'))
    bound = min(current, witness) if witness is not None else current
    if not index_time <= started <= bound:
        raise ValueError('INVALID_NDR_CAPTURE_CHRONOLOGY')
    # Existing observe() performs index integrity and row parsing. Its fixed
    # filenames are written only inside this fresh private temporary directory;
    # unrelated DFB raw evidence is neither needed nor implicitly authenticated.
    with tempfile.TemporaryDirectory(prefix='ndr-capture-replay-') as temporary:
        folder = Path(temporary)
        (folder / 'manifest.json').write_bytes(files['index-manifest.json'])
        if 'ndr.html' in files:
            (folder / 'ndr.html').write_bytes(files['ndr.html'])
        index = observe(folder, now=current)
    rows = collector._validated_rows(index)
    expected = collector._safe_report(report['captured_utc'])
    expected['source_available'] = index.get('source_available') is True
    expected['source_index'] = index.get('source')
    present = {'index-manifest.json', 'completion-manifest.json', 'report.json'}
    requests, captures = [], []
    if expected['source_available']:
        present.add('ndr.html')
    else:
        expected['source_unavailable_reason'] = 'NDR_SOURCE_NOT_AVAILABLE'
    sources = report.get('sources')
    cohort = rows[:collector.MAX_REQUESTS] if expected['source_available'] else []
    if not isinstance(sources, list) or len(sources) != len(cohort):
        raise ValueError('INVALID_NDR_CAPTURE_ATTEMPT_COHORT')
    previous = started
    for item, source in zip(cohort, sources):
        if not isinstance(source, dict):
            raise ValueError('INVALID_NDR_CAPTURE_DETAIL_SOURCE')
        fixture_id, url = item['provider_fixture_id'], item['fixture_url']
        requested = _utc(source.get('requested_utc'))
        if not previous <= requested <= bound:
            raise ValueError('INVALID_NDR_CAPTURE_REQUEST_CHRONOLOGY')
        requests.append(requested)
        expected_source = {
            'provider': 'NDR', 'provider_fixture_id': fixture_id, 'source_url': url,
            'status': 'ERROR', 'final_url': None, 'requested_utc': source['requested_utc'],
            'capture_time_independently_authenticated': False,
            'source_identity_independently_authenticated': False,
        }
        expected['requests_attempted'] += 1
        expected['attempt_count'] = expected['requests_attempted']
        previous = requested
        if source.get('status') == 'ERROR':
            reason = source.get('error')
            if not isinstance(reason, str) or reason not in FETCH_REASONS:
                raise ValueError('INVALID_NDR_CAPTURE_FETCH_REASON')
            expected_source['error'] = reason
            if 'http_status' in source:
                code = source['http_status']
                if type(code) is not int or not 100 <= code <= 599 or reason != 'NDR_DETAIL_FETCH_FAILED':
                    raise ValueError('INVALID_NDR_CAPTURE_ERROR_HTTP_STATUS')
                expected_source['http_status'] = code
            _same(source, expected_source, 'INCONSISTENT_NDR_CAPTURE_FETCH_ERROR')
            expected['sources'].append(expected_source)
            expected['fetch_errors'].append({'provider_fixture_id': fixture_id, 'reason': reason})
            continue
        captured = _utc(source.get('captured_utc'))
        if not requested <= captured <= bound:
            raise ValueError('INVALID_NDR_CAPTURE_DETAIL_CHRONOLOGY')
        captures.append(captured)
        previous = captured
        name = f'ndr-detail-{fixture_id}.html'
        if name not in files:
            raise ValueError('MISSING_NDR_CAPTURE_DETAIL_BYTES')
        raw = files[name]
        present.add(name)
        content_type = source.get('content_type')
        if content_type not in ('text/html', 'application/xhtml+xml'):
            raise ValueError('INVALID_NDR_CAPTURE_DETAIL_MEDIA_TYPE')
        expected_source.update({
            'status': 'FETCHED_UNVERIFIED', 'final_url': url,
            'captured_utc': source['captured_utc'], 'raw_file': name,
            'raw_sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
            'http_status': 200, 'content_type': content_type,
        })
        _same(source, expected_source, 'INCONSISTENT_NDR_CAPTURE_DETAIL_METADATA')
        expected['sources'].append(expected_source)
        try:
            observation = parse_detail(raw, item)
            if not isinstance(observation, dict) or observation.get('provider_fixture_id') != fixture_id:
                raise ValueError('INVALID_NDR_DETAIL_OBSERVATION')
            if (observation.get('completion_display_observed') is not True
                    or observation.get('completion_authenticated') is not False
                    or observation.get('period_authenticated') is not False
                    or observation.get('candidate_only') is not True
                    or observation.get('status') != 'HOLD'
                    or observation.get('production_recommendations') != 'DISABLED'
                    or observation.get('independently_verified') is not False
                    or observation.get('eligible_for_model_scoring') is not False):
                raise ValueError('UNSAFE_NDR_DETAIL_OBSERVATION')
        except (ValueError, TypeError, RecursionError) as exc:
            expected['rejections'].append({
                'provider_fixture_id': fixture_id,
                'reason': collector._reason(exc, 'NDR_DETAIL_DISPLAY_REJECTED'),
            })
            continue
        expected['observations'].append(dict(
            observation, status='HOLD', production_recommendations='DISABLED',
            candidate_only=True, independently_verified=False,
            eligible_for_model_scoring=False, detail_source=dict(expected_source)))
    expected['observation_count'] = len(expected['observations'])
    if present != set(files):
        raise ValueError('UNLISTED_NDR_CAPTURE_RAW_BYTES')
    _same(report, expected, 'INCONSISTENT_NDR_CAPTURE_REPORT')
    _same(completion_manifest, _manifest(expected), 'INCONSISTENT_NDR_CAPTURE_COMPLETION_MANIFEST')
    return {
        'schema': 'football-king-ndr-capture-content-verification-v1',
        'status': 'HOLD', 'production_recommendations': 'DISABLED', 'candidate_only': True,
        'controlled_capture_content_verified': True, 'independently_verified': False,
        'eligible_for_model_scoring': False, 'formal_eligible': False,
        'source_available': expected['source_available'],
        'requests_attempted': expected['requests_attempted'],
        'observation_count': expected['observation_count'],
        'rejection_count': len(expected['rejections']),
        'fetch_error_count': len(expected['fetch_errors']),
        'index_observation_count': len(rows),
        'index_rejected_row_count': index['rejected_row_count'],
        'index_captured_utc': index_time.isoformat(), 'report_started_utc': started.isoformat(),
        'requested_utc': [value.isoformat() for value in requests],
        'detail_captured_utc': [value.isoformat() for value in captures],
        'capture_latest_utc': max([index_time, started, *requests, *captures]).isoformat(),
    }


def validate_capture(raw_tar, *, witness=None, now=None):
    """Replay a bounded canonical tar; return safe counts and recorded chronology.

    ``witness`` is the already cryptographically verified UTC log time, when
    available. These checks establish consistency with recorded wall-clock
    metadata; they never independently authenticate the publisher or results.
    """
    current = _utc(datetime.now(timezone.utc) if now is None else now, 'INVALID_CURRENT_UTC_TIME')
    witnessed = _utc(witness, 'INVALID_NDR_CAPTURE_WITNESS_TIME') if witness is not None else None
    if witnessed is not None and witnessed > current + timedelta(minutes=5):
        raise ValueError('FUTURE_NDR_CAPTURE_WITNESS_TIME')
    try:
        return _replay(_members(raw_tar), current=current, witness=witnessed)
    except (OSError, TypeError, RecursionError, KeyError, OverflowError) as exc:
        raise ValueError('NDR_CAPTURE_CONTENT_REJECTED') from exc


def _read(path, maximum, identities):
    path = _checked_path(path)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        before = os.fstat(stream.fileno())
        identity = (before.st_dev, before.st_ino)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or not 0 < before.st_size <= maximum or identity in identities):
            raise ValueError('INVALID_NDR_CAPTURE_INPUT_FILE')
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
        if (len(raw) != before.st_size or len(raw) > maximum
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns or after.st_nlink != 1):
            raise ValueError('NDR_CAPTURE_INPUT_CHANGED_DURING_READ')
        identities.add(identity)
    return raw


def prepare(index_dir, completion_dir, output_tar, now=None):
    """Snapshot exact original inputs, replay, then exclusively write one tar."""
    index, completion, output = map(_checked_path, (index_dir, completion_dir, output_tar))
    if not index.is_dir() or not completion.is_dir() or index == completion:
        raise ValueError('INVALID_NDR_CAPTURE_INPUT_DIRECTORIES')
    if output.name != NDR_CAPTURE_FILENAME:
        raise ValueError('INVALID_NDR_CAPTURE_SUBJECT_NAME')
    if any(output == source or source in output.parents for source in (index, completion)):
        raise ValueError('OUTPUT_MUST_NOT_MODIFY_RAW_EVIDENCE')
    if output.exists():
        raise ValueError('NDR_CAPTURE_OUTPUT_ALREADY_EXISTS')
    details = []
    entry_count = 0
    for path in completion.iterdir():
        entry_count += 1
        if entry_count > 2 + collector.MAX_REQUESTS:
            raise ValueError('TOO_MANY_NDR_COMPLETION_INPUT_FILES')
        if path.name in ('manifest.json', 'report.json'):
            continue
        if not DETAIL_NAME.fullmatch(path.name):
            raise ValueError('UNEXPECTED_NDR_COMPLETION_INPUT_FILE')
        details.append(path)
    if len(details) > collector.MAX_REQUESTS:
        raise ValueError('TOO_MANY_NDR_COMPLETION_DETAIL_FILES')
    identities = set()
    files = {
        'index-manifest.json': _read(index / 'manifest.json', MAX_MANIFEST_BYTES, identities),
        'completion-manifest.json': _read(completion / 'manifest.json', MAX_FILE_BYTES, identities),
        'report.json': _read(completion / 'report.json', MAX_FILE_BYTES, identities),
    }
    if (index / 'ndr.html').exists() or (index / 'ndr.html').is_symlink():
        files['ndr.html'] = _read(index / 'ndr.html', MAX_FILE_BYTES, identities)
    for path in details:
        files[path.name] = _read(path, MAX_FILE_BYTES, identities)
        if sum(map(len, files.values())) > MAX_CAPTURE_BYTES:
            raise ValueError('OVERSIZED_NDR_CAPTURE_CONTENT')
    raw = _tar(files)
    summary = validate_capture(raw, now=now)
    # No output is created until every copied byte and report has been checked.
    output.parent.mkdir(parents=True, exist_ok=True)
    output = _checked_path(output)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    created = False
    try:
        fd = os.open(output, flags, 0o600)
        created = True
        with os.fdopen(fd, 'wb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('INVALID_NDR_CAPTURE_OUTPUT_FILE')
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        raise
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', required=True)
    parser.add_argument('--completion', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        summary = prepare(args.index, args.completion, args.output)
    except (OSError, ValueError, TypeError, RecursionError):
        print(json.dumps({'status': 'HOLD', 'production_recommendations': 'DISABLED',
                          'independently_verified': False, 'eligible_for_model_scoring': False,
                          'formal_eligible': False, 'error': 'NDR_CAPTURE_PREPARATION_REJECTED'}))
        return 1
    print(json.dumps(summary))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
