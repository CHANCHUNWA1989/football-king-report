"""Bind relay artifacts to externally pinned, authenticated GitHub responses.

This pure validator performs no network or signature verification. Its caller
MUST obtain run/artifact metadata through authenticated GitHub REST and pin the
reviewed source commit, workflow, branch, recipient and requested run/attempt
independently of downloaded artifacts. Saved dictionaries are not proof.

An age public recipient authenticates no sender. The separate safe receipt is
accepted only after BOTH artifact ZIP digests and SAME trusted-run identities
are checked. No upstream publisher, source clock or football result is certified.
"""
from dataclasses import dataclass
import hashlib
import io
import json
import re
import stat
import zipfile


REPOSITORY = 'CHANCHUNWA1989/football-king-report'
REPOSITORY_ID = 1411226578
CIPHERTEXT_MEMBER = 'original-response-pack.zip.age'
RECEIPT_MEMBER = 'producer-receipt.json'
MAX_ARCHIVE_BYTES = 36_000_000
MAX_CIPHERTEXT_BYTES = 36_100_000
MAX_CIPHERTEXT_ARTIFACT_BYTES = 36_200_000
MAX_RECEIPT_BYTES = 8_000
MAX_RECEIPT_ARTIFACT_BYTES = 64_000
RECEIPT_KEYS = frozenset((
    'schema', 'operation', 'relay_status', 'source_sha', 'run_id', 'attempt',
    'manifest_sha256', 'archive_sha256', 'ciphertext_sha256', 'recipient_sha256',
    'archive_bytes', 'ciphertext_bytes', 'capture_count', 'encryption',
    'raw_source_authenticated', 'capture_time_authenticated', 'durable_archive_verified',
    'production_recommendations', 'status', 'certified_case_count',
    'eligible_for_model_scoring', 'eligible_for_betting_promotion'))
FALSE_FLAGS = ('raw_source_authenticated', 'capture_time_authenticated',
               'durable_archive_verified', 'eligible_for_model_scoring',
               'eligible_for_betting_promotion')


class ProvenanceError(ValueError):
    """Public-safe fixed error code without response payloads or paths."""


def _require(condition, reason):
    if not condition:
        raise ProvenanceError(reason)


def _hash(value, length=64):
    return type(value) is str and re.fullmatch('[0-9a-f]{%d}' % length, value) is not None


def _positive_int(value, maximum=None):
    return type(value) is int and value > 0 and (maximum is None or value <= maximum)


def _decimal(value):
    return type(value) is str and re.fullmatch('[1-9][0-9]{0,19}', value) is not None


@dataclass(frozen=True)
class ExpectedRun:
    """These pins come from the caller's reviewed configuration, never payloads."""
    source_sha: str
    run_id: str
    attempt: str
    workflow_path: str
    recipient_sha256: str
    head_branch: str = 'main'
    allowed_events: tuple = ('push', 'schedule', 'workflow_dispatch')
    repository_full_name: str = REPOSITORY
    repository_id: int = REPOSITORY_ID

    def __post_init__(self):
        _require(_hash(self.source_sha, 40) and _hash(self.recipient_sha256)
                 and _decimal(self.run_id) and _decimal(self.attempt), 'INVALID_RELAY_EXPECTED_CONTEXT')
        _require(self.repository_full_name == REPOSITORY
                 and type(self.repository_id) is int and self.repository_id == REPOSITORY_ID,
                 'INVALID_RELAY_EXPECTED_REPOSITORY')
        _require(type(self.workflow_path) is str and re.fullmatch(
            r'\.github/workflows/[a-z0-9][a-z0-9-]*\.yml', self.workflow_path),
            'INVALID_RELAY_EXPECTED_WORKFLOW')
        _require(type(self.head_branch) is str and re.fullmatch(
            r'[A-Za-z0-9][A-Za-z0-9._/-]{0,199}', self.head_branch)
            and '..' not in self.head_branch and not self.head_branch.endswith('/'),
            'INVALID_RELAY_EXPECTED_BRANCH')
        _require(type(self.allowed_events) is tuple and 0 < len(self.allowed_events) <= 3
                 and all(type(event) is str and event in ('push', 'schedule', 'workflow_dispatch')
                         for event in self.allowed_events)
                 and len(set(self.allowed_events)) == len(self.allowed_events),
                 'INVALID_RELAY_EXPECTED_EVENTS')


@dataclass(frozen=True)
class ProvenanceResult:
    receipt: dict
    ciphertext: bytes
    report: dict


def _repository(value, expected):
    return type(value) is dict and type(value.get('id')) is int \
        and value['id'] == expected.repository_id \
        and value.get('full_name') == expected.repository_full_name


def _run(run, expected):
    _require(type(run) is dict and _repository(run.get('repository'), expected)
             and _repository(run.get('head_repository'), expected), 'RELAY_RUN_REPOSITORY_MISMATCH')
    _require(type(run.get('id')) is int and run['id'] == int(expected.run_id)
             and type(run.get('run_attempt')) is int and run['run_attempt'] == int(expected.attempt)
             and run.get('head_sha') == expected.source_sha
             and run.get('head_branch') == expected.head_branch
             and run.get('path') == expected.workflow_path, 'RELAY_RUN_CONTEXT_MISMATCH')
    _require(run.get('event') in expected.allowed_events
             and run.get('status') == 'completed' and run.get('conclusion') == 'success',
             'RELAY_RUN_NOT_SUCCESSFUL_TRUSTED_EVENT')


def _artifact(meta, raw, expected, kind, maximum):
    _require(type(raw) is bytes and 0 < len(raw) <= maximum, 'RELAY_ARTIFACT_SIZE_LIMIT')
    _require(type(meta) is dict and _positive_int(meta.get('id'))
             and meta.get('name') == ('football-private-original-' + kind + '-'
                                      + expected.run_id + '-' + expected.attempt)
             and meta.get('expired') is False
             and type(meta.get('size_in_bytes')) is int and meta['size_in_bytes'] == len(raw)
             and meta.get('digest') == 'sha256:' + hashlib.sha256(raw).hexdigest(),
             'RELAY_ARTIFACT_METADATA_OR_DIGEST_MISMATCH')
    origin = meta.get('workflow_run')
    _require(type(origin) is dict and type(origin.get('id')) is int
             and origin['id'] == int(expected.run_id)
             and type(origin.get('repository_id')) is int
             and origin['repository_id'] == expected.repository_id
             and type(origin.get('head_repository_id')) is int
             and origin['head_repository_id'] == expected.repository_id
             and origin.get('head_sha') == expected.source_sha
             and origin.get('head_branch') == expected.head_branch,
             'RELAY_ARTIFACT_PRODUCER_MISMATCH')


def _single_member(raw, member, maximum):
    try:
        # Artifact ZIPs have one local member and a comment-free EOCD. Reject
        # prepended/trailing bytes instead of letting ZipFile silently ignore it.
        _require(raw.startswith(b'PK\x03\x04') and len(raw) >= 22
                 and raw[-22:-18] == b'PK\x05\x06', 'RELAY_ARTIFACT_ZIP_REJECTED')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            _require(len(infos) == 1 and not archive.comment, 'RELAY_ARTIFACT_MEMBER_ALLOWLIST')
            info = infos[0]
            mode = info.external_attr >> 16
            _require(info.filename == member and info.orig_filename == member and not info.is_dir()
                     and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                     and not info.flag_bits & 1
                     and stat.S_IFMT(mode) in (0, stat.S_IFREG)
                     and 0 < info.file_size <= maximum and 0 < info.compress_size <= len(raw)
                     and len(info.extra) <= 4096 and not info.comment,
                     'RELAY_ARTIFACT_MEMBER_ALLOWLIST')
            with archive.open(info) as stream:
                payload = stream.read(maximum + 1)
                _require(len(payload) == info.file_size and len(payload) <= maximum
                         and not stream.read(1), 'RELAY_ARTIFACT_MEMBER_SIZE_LIMIT')
            return payload
    except ProvenanceError:
        raise
    except Exception:
        raise ProvenanceError('RELAY_ARTIFACT_ZIP_REJECTED') from None


def _pairs(items):
    result = {}
    for key, value in items:
        _require(key not in result, 'RELAY_RECEIPT_DUPLICATE_KEY')
        result[key] = value
    return result


def _constant(_):
    raise ProvenanceError('RELAY_RECEIPT_INVALID_JSON')


def _receipt(raw, ciphertext, expected):
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_constant)
    except ProvenanceError:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise ProvenanceError('RELAY_RECEIPT_INVALID_JSON') from None
    _require(type(value) is dict and set(value) == RECEIPT_KEYS, 'RELAY_RECEIPT_SCHEMA_MISMATCH')
    fixed = {'schema': 'football-king-private-response-relay-v1', 'operation': 'encrypt',
             'relay_status': 'ENCRYPTED', 'source_sha': expected.source_sha,
             'run_id': expected.run_id, 'attempt': expected.attempt,
             'recipient_sha256': expected.recipient_sha256,
             'encryption': 'age-v1.3.2-native-pq', 'production_recommendations': 'DISABLED',
             'status': 'HOLD'}
    _require(all(type(value[key]) is str and value[key] == item for key, item in fixed.items()),
             'RELAY_RECEIPT_CONTEXT_MISMATCH')
    _require(all(value[key] is False for key in FALSE_FLAGS)
             and type(value['certified_case_count']) is int and value['certified_case_count'] == 0,
             'RELAY_RECEIPT_CERTIFICATION_CLAIM_REJECTED')
    _require(all(_hash(value[key]) for key in
                 ('manifest_sha256', 'archive_sha256', 'ciphertext_sha256', 'recipient_sha256'))
             and _positive_int(value['archive_bytes'], MAX_ARCHIVE_BYTES)
             and _positive_int(value['ciphertext_bytes'], MAX_CIPHERTEXT_BYTES)
             and value['archive_bytes'] < value['ciphertext_bytes']
             and _positive_int(value['capture_count'], 7), 'RELAY_RECEIPT_PIN_OR_SIZE_REJECTED')
    _require(value['ciphertext_bytes'] == len(ciphertext)
             and value['ciphertext_sha256'] == hashlib.sha256(ciphertext).hexdigest(),
             'RELAY_CIPHERTEXT_PIN_MISMATCH')
    return value


def verify_bundle(run_metadata, cipher_artifact_metadata, cipher_artifact_zip,
                  receipt_artifact_metadata, receipt_artifact_zip, *, expected):
    """Return external producer pins plus ciphertext after strict same-run checks.

    Metadata fetch authentication is the caller's responsibility. Neither these
    dictionaries nor the returned report are reusable independent proof.
    """
    _require(type(expected) is ExpectedRun, 'INVALID_RELAY_EXPECTED_CONTEXT')
    _run(run_metadata, expected)
    _artifact(cipher_artifact_metadata, cipher_artifact_zip, expected, 'ciphertext',
              MAX_CIPHERTEXT_ARTIFACT_BYTES)
    _artifact(receipt_artifact_metadata, receipt_artifact_zip, expected, 'receipt',
              MAX_RECEIPT_ARTIFACT_BYTES)
    _require(cipher_artifact_metadata['id'] != receipt_artifact_metadata['id'],
             'RELAY_ARTIFACT_IDENTITIES_NOT_DISTINCT')
    ciphertext = _single_member(cipher_artifact_zip, CIPHERTEXT_MEMBER, MAX_CIPHERTEXT_BYTES)
    receipt = _receipt(_single_member(receipt_artifact_zip, RECEIPT_MEMBER, MAX_RECEIPT_BYTES),
                       ciphertext, expected)
    report = {'schema': 'football-king-private-relay-github-binding-v1',
              'github_metadata_and_digest_bound': True, 'authenticated_github_fetch_required': True,
              'source_sha': expected.source_sha, 'run_id': expected.run_id, 'attempt': expected.attempt,
              'workflow_path': expected.workflow_path, 'head_branch': expected.head_branch,
              'ciphertext_artifact_id': cipher_artifact_metadata['id'],
              'receipt_artifact_id': receipt_artifact_metadata['id'],
              'manifest_sha256': receipt['manifest_sha256'], 'archive_sha256': receipt['archive_sha256'],
              'ciphertext_sha256': receipt['ciphertext_sha256'],
              'recipient_sha256': expected.recipient_sha256,
              'raw_source_authenticated': False, 'capture_time_authenticated': False,
              'durable_archive_verified': False, 'certified_case_count': 0,
              'production_recommendations': 'DISABLED', 'status': 'HOLD'}
    return ProvenanceResult(receipt=receipt, ciphertext=ciphertext, report=report)
