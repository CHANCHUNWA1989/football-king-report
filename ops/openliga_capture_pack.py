"""Seal and replay exact OpenLigaDB raw bytes under a deliberately narrow scope.

No network request is made here. The second provider's receipt is structurally
checked, but its raw bytes are absent from this subject and are not authenticated.
Neither a replay nor an attestation authenticates publisher truth or football FT.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import stat
import tarfile

from ops.raw_origin_metadata import SCHEMA, validate_manifest
from ops.shadow_raw_source_collector import validate_json_body


SUBJECT_NAME = 'openliga-capture.tar'
MEMBER_NAMES = ('manifest.json', 'openligadb.json', 'capture.json', 'NOTICE.txt')
MAX_RAW_BYTES = 3_000_000
MAX_MANIFEST_BYTES = 200_000
MAX_SUMMARY_BYTES = 100_000
MAX_NOTICE_BYTES = 10_000
MAX_CAPTURE_BYTES = 4_000_000
LIMITS = dict(zip(MEMBER_NAMES, (MAX_MANIFEST_BYTES, MAX_RAW_BYTES,
                               MAX_SUMMARY_BYTES, MAX_NOTICE_BYTES)))


def _utc(value, reason='INVALID_OPENLIGA_CAPTURE_TIME'):
    if isinstance(value, str):
        if not value.endswith(('Z', '+00:00')):
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
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('DUPLICATE_OPENLIGA_CAPTURE_JSON_KEY')
            value[key] = item
        return value

    def nonfinite(_):
        raise ValueError('NONFINITE_OPENLIGA_CAPTURE_JSON')

    def floating(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError('NONFINITE_OPENLIGA_CAPTURE_JSON')
        return number

    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                          parse_constant=nonfinite, parse_float=floating)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('INVALID_OPENLIGA_CAPTURE_JSON') from exc


def _encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def _same(actual, expected, reason):
    # Preserve JSON types: bool must never pass as an integer count.
    options = dict(sort_keys=True, separators=(',', ':'), allow_nan=False)
    if json.dumps(actual, **options) != json.dumps(expected, **options):
        raise ValueError(reason)


def _safe_path(value):
    path = Path(value)
    if '..' in path.parts:
        raise ValueError('UNSAFE_OPENLIGA_CAPTURE_PATH')
    path = path.absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('UNSAFE_OPENLIGA_CAPTURE_PATH')
    return path


def _read_regular(path, maximum, identities=None):
    path = _safe_path(path)
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or not 0 < before.st_size <= maximum):
        raise ValueError('INVALID_OPENLIGA_CAPTURE_REGULAR_FILE')
    identity = (before.st_dev, before.st_ino)
    if identities is not None and identity in identities:
        raise ValueError('ALIASED_OPENLIGA_CAPTURE_INPUT')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns,
                    opened.st_ctime_ns) != (before.st_dev, before.st_ino, before.st_size,
                                           before.st_mtime_ns, before.st_ctime_ns)):
            raise ValueError('OPENLIGA_CAPTURE_INPUT_CHANGED_DURING_READ')
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    current = path.lstat()
    signature = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_nlink,
                              item.st_size, item.st_mtime_ns, item.st_ctime_ns)
    if (len(raw) != before.st_size or len(raw) > maximum
            or signature(before) != signature(after) or signature(before) != signature(current)):
        raise ValueError('OPENLIGA_CAPTURE_INPUT_CHANGED_DURING_READ')
    if identities is not None:
        identities.add(identity)
    return raw


def _notice(year):
    return (
        'OpenLigaDB raw data attribution and license notice\n\n'
        'Contains information from OpenLigaDB (https://www.openligadb.de/), which is made available\n'
        'under the Open Database License (ODbL) 1.0: https://opendatacommons.org/licenses/odbl/1-0/.\n\n'
        'Source: https://api.openligadb.de/getmatchdata/bl1/' + str(year) + '\n'
        'Attribution: OpenLigaDB/community contributors\n'
        'Data license: Open Database License (ODbL) 1.0\n'
        'https://opendatacommons.org/licenses/odbl/1-0/\n\n'
        'The openligadb.json response is preserved as unmodified raw bytes.\n'
        'This data license is separate from the repository code license.\n'
        'No logos, images, API keys, or OpenFootball raw response are included.\n'
        'Capture provenance does not authenticate the publisher, upstream independence,\n'
        'actual kickoff, regulation-time FT, result IDs, or model/scoring eligibility.\n'
    ).encode('utf-8')


def _summary(manifest_raw, raw, *, current, witness):
    manifest = _json(manifest_raw)
    if not isinstance(manifest, dict) or manifest.get('schema') != SCHEMA:
        raise ValueError('NOT_CONTROLLED_ORIGIN_CHAIN')
    validate_manifest(manifest, now=current, before=witness)
    receipt = manifest['sources'][0]
    if receipt['provider'] != 'OpenLigaDB' or receipt['status'] != 'FETCHED_UNVERIFIED':
        raise ValueError('OPENLIGA_SUCCESS_RECEIPT_REQUIRED')
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) != receipt['bytes'] or digest != receipt['raw_sha256']:
        raise ValueError('OPENLIGA_RAW_RECEIPT_BYTES_MISMATCH')
    parsed = validate_json_body(raw, 'OpenLigaDB')
    # Count supplied records without certifying their IDs, scores, period, or truth.
    return {
        'schema': 'football-king-openliga-capture-summary-v1',
        'status': 'HOLD', 'production_recommendations': 'DISABLED', 'candidate_only': True,
        'origin_chain_scope': 'OPENLIGADB_ONLY', 'origin_manifest_schema': SCHEMA,
        'origin_chain_complete': True,
        'manifest_sha256': hashlib.sha256(manifest_raw).hexdigest(),
        'manifest_bytes': len(manifest_raw), 'source_receipt': receipt,
        'raw_sha256': digest, 'raw_bytes': len(raw), 'raw_record_count': len(parsed),
        'captured_utc': manifest['captured_utc'],
        'capture_latest_utc': manifest['sources'][-1]['completed_utc'],
        'upstream_independence': 'UNKNOWN',
        'raw_source_identity_authenticated': False,
        'publisher_identity_authenticated': False,
        'source_identity_independently_authenticated': False,
        'upstream_independence_authenticated': False,
        'actual_kickoff_authenticated': False, 'regulation_ft_authenticated': False,
        'outcomes_independently_authenticated': False, 'independently_verified': False,
        'eligible_for_model_scoring': False, 'eligible_for_betting_promotion': False,
        'formal_eligible': False,
    }


def _tar(files):
    size = sum(512 + ((len(body) + 511) // 512) * 512 for body in files.values()) + 1024
    if ((size + 10239) // 10240) * 10240 > MAX_CAPTURE_BYTES:
        raise ValueError('OVERSIZED_OPENLIGA_CAPTURE')
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name in MEMBER_NAMES:
            info = tarfile.TarInfo(name)
            info.mode, info.size = 0o600, len(files[name])
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = ''
            archive.addfile(info, io.BytesIO(files[name]))
    return stream.getvalue()


def _members(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_CAPTURE_BYTES:
        raise ValueError('INVALID_OR_OVERSIZED_OPENLIGA_CAPTURE')
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
            members = archive.getmembers()
            if len(members) != len(MEMBER_NAMES):
                raise ValueError('INVALID_OPENLIGA_CAPTURE_MEMBER_COUNT')
            files = {}
            for member in members:
                if member.name not in LIMITS or member.name in files:
                    raise ValueError('INVALID_OR_DUPLICATE_OPENLIGA_CAPTURE_MEMBER')
                if (member.type != tarfile.REGTYPE or member.pax_headers or member.linkname
                        or member.uid != 0 or member.gid != 0 or member.mtime != 0
                        or member.mode != 0o600 or member.uname or member.gname):
                    raise ValueError('INVALID_OPENLIGA_CAPTURE_MEMBER_METADATA')
                maximum = LIMITS[member.name]
                if not 0 < member.size <= maximum:
                    raise ValueError('INVALID_OPENLIGA_CAPTURE_MEMBER_SIZE')
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError('UNREADABLE_OPENLIGA_CAPTURE_MEMBER')
                with source:
                    body = source.read(maximum + 1)
                if len(body) != member.size:
                    raise ValueError('TRUNCATED_OPENLIGA_CAPTURE_MEMBER')
                files[member.name] = body
    except (tarfile.TarError, OSError, EOFError, OverflowError) as exc:
        raise ValueError('INVALID_OPENLIGA_CAPTURE_TAR') from exc
    if set(files) != set(MEMBER_NAMES) or raw != _tar(files):
        raise ValueError('NONCANONICAL_OPENLIGA_CAPTURE_TAR')
    return files


def validate_capture(raw_tar, *, witness=None, now=None):
    """Replay canonical original bytes, bounded by a verified log time if given."""
    try:
        current = _utc(datetime.now(timezone.utc) if now is None else now)
        witnessed = _utc(witness) if witness is not None else None
        if witnessed is not None and witnessed > current:
            raise ValueError('FUTURE_OPENLIGA_CAPTURE_WITNESS')
        files = _members(raw_tar)
        summary = _summary(files['manifest.json'], files['openligadb.json'],
                           current=current, witness=witnessed)
        _same(_json(files['capture.json']), summary, 'INCONSISTENT_OPENLIGA_CAPTURE_SUMMARY')
        # The generated summary and notice have exactly one representation.
        if files['capture.json'] != _encoded(summary):
            raise ValueError('NONCANONICAL_OPENLIGA_CAPTURE_SUMMARY')
        manifest = _json(files['manifest.json'])
        if files['NOTICE.txt'] != _notice(manifest['season_start']):
            raise ValueError('INCONSISTENT_OPENLIGA_CAPTURE_NOTICE')
        return dict(summary, controlled_capture_content_verified=True)
    except (OSError, TypeError, RecursionError, KeyError, OverflowError) as exc:
        raise ValueError('OPENLIGA_CAPTURE_CONTENT_REJECTED') from exc


def prepare(raw_dir, output_tar, now=None):
    """Snapshot an existing controlled raw directory; exclusively create one tar."""
    folder, output = _safe_path(raw_dir), _safe_path(output_tar)
    if not folder.is_dir():
        raise ValueError('INVALID_OPENLIGA_CAPTURE_INPUT_DIRECTORY')
    if output.name != SUBJECT_NAME:
        raise ValueError('INVALID_OPENLIGA_CAPTURE_SUBJECT_NAME')
    if output == folder or folder in output.parents:
        raise ValueError('OUTPUT_MUST_NOT_MODIFY_RAW_EVIDENCE')
    if output.exists():
        raise ValueError('OPENLIGA_CAPTURE_OUTPUT_ALREADY_EXISTS')
    entries = []
    for path in folder.iterdir():
        entries.append(path.name)
        if len(entries) > 3 or path.name not in ('manifest.json', 'openligadb.json', 'openfootball.json'):
            raise ValueError('UNEXPECTED_OPENLIGA_CAPTURE_INPUT_FILE')
    identities = set()
    files = {'manifest.json': _read_regular(folder / 'manifest.json', MAX_MANIFEST_BYTES, identities),
             'openligadb.json': _read_regular(folder / 'openligadb.json', MAX_RAW_BYTES, identities)}
    current = _utc(datetime.now(timezone.utc) if now is None else now)
    summary = _summary(files['manifest.json'], files['openligadb.json'], current=current, witness=None)
    manifest = _json(files['manifest.json'])
    expected = {'manifest.json', 'openligadb.json'}
    if manifest['sources'][1]['status'] == 'FETCHED_UNVERIFIED':
        expected.add('openfootball.json')
    if set(entries) != expected:
        raise ValueError('INCONSISTENT_OPENLIGA_CAPTURE_INPUT_FILES')
    if 'openfootball.json' in expected:
        # Bound and reject aliases in the source directory. These bytes are not
        # retained, hashed, replayed or represented as an authenticated source.
        _read_regular(folder / 'openfootball.json', MAX_RAW_BYTES, identities)
    files['capture.json'] = _encoded(summary)
    files['NOTICE.txt'] = _notice(manifest['season_start'])
    raw_tar = _tar(files)
    replayed = validate_capture(raw_tar, now=current)
    for name in ('manifest.json', 'openligadb.json'):
        if _read_regular(folder / name, LIMITS[name]) != files[name]:
            raise ValueError('OPENLIGA_CAPTURE_INPUT_CHANGED_DURING_PREPARATION')
    output.parent.mkdir(parents=True, exist_ok=True)
    output = _safe_path(output)
    created = False
    try:
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        created = True
        with os.fdopen(fd, 'wb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('INVALID_OPENLIGA_CAPTURE_OUTPUT_FILE')
            stream.write(raw_tar)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        raise
    return replayed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = prepare(args.raw, args.output)
    except (OSError, ValueError, TypeError, RecursionError):
        print(json.dumps({'status': 'HOLD', 'production_recommendations': 'DISABLED',
                          'independently_verified': False, 'eligible_for_model_scoring': False,
                          'error': 'OPENLIGA_CAPTURE_PREPARATION_REJECTED'}))
        return 1
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
