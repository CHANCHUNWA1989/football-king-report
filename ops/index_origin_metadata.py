"""Validate versioned endpoint receipts; never authenticate result truth.

Historical v2 records DFB then NDR requests. New v3 records a fixed policy skip
for DFB and one NDR attempt. Only actual request receipts describe HTTPS
requests with redirects denied; a skip has no fabricated times or response. NDR raw
bytes still need a separate hash/size/content replay; DFB bytes are not in the
NDR capture subject. No receipt establishes publisher or upstream independence.
"""
from datetime import datetime
import re

if __package__:
    from .shadow_external_evidence_collector import (ERROR_CODES, MAX_BYTES, SOURCES,
        POLICY_SCHEMA, DFB_POLICY_REASON, DFB_TERMS_REFERENCE)
else:
    from shadow_external_evidence_collector import (ERROR_CODES, MAX_BYTES, SOURCES,
        POLICY_SCHEMA, DFB_POLICY_REASON, DFB_TERMS_REFERENCE)

SCHEMA = 'football-king-external-raw-evidence-v2'
LEGACY_SCHEMA = 'football-king-external-raw-evidence-v1'
UTC_TIME = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)\Z')


def utc(value):
    if not isinstance(value, str) or not UTC_TIME.fullmatch(value):
        raise ValueError('INVALID_INDEX_ORIGIN_UTC')
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('INVALID_INDEX_ORIGIN_UTC') from exc


def validate_manifest(manifest, *, now, before=None):
    """Validate exact v2 receipts or v3's policy skip and single NDR attempt.

    This routine has no trust flags or policy overrides. Its success only means
    the receipts are structurally consistent; authenticated execution and exact
    original bytes must be checked by the calling capture verifier.
    """
    if (not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None
            or (before is not None and (not isinstance(before, datetime)
                or before.tzinfo is None or before.utcoffset() is None))):
        raise ValueError('INVALID_INDEX_ORIGIN_CLOCK')
    bound = min(now, before) if before is not None else now
    keys = {'schema', 'captured_utc', 'status', 'independently_verified',
            'eligible_for_model_scoring', 'production_recommendations', 'sources'}
    if (not isinstance(manifest, dict) or set(manifest) != keys
            or manifest.get('schema') not in (SCHEMA, POLICY_SCHEMA)
            or manifest.get('status') != 'HOLD'
            or manifest.get('independently_verified') is not False
            or manifest.get('eligible_for_model_scoring') is not False
            or manifest.get('production_recommendations') != 'DISABLED'):
        raise ValueError('INVALID_INDEX_ORIGIN_MANIFEST')
    sources = manifest['sources']
    if (not isinstance(sources, list) or len(sources) != 2
            or any(not isinstance(source, dict) for source in sources)
            or [source.get('provider') for source in sources] != ['DFB', 'NDR']):
        raise ValueError('INVALID_INDEX_ORIGIN_PROVIDER_ORDER')
    previous = utc(manifest['captured_utc'])
    if previous > bound:
        raise ValueError('INVALID_INDEX_ORIGIN_CHRONOLOGY')
    base = {'provider', 'source_url', 'status', 'requested_utc', 'completed_utc',
            'redirect_policy', 'final_url'}
    for source in sources:
        provider = source['provider']
        if manifest['schema'] == POLICY_SCHEMA and provider == 'DFB':
            if (set(source) != base | {'http_status', 'policy_reason', 'terms_reference'}
                    or source.get('source_url') != SOURCES['DFB']
                    or source.get('status') != 'SKIPPED_POLICY'
                    or source.get('policy_reason') != DFB_POLICY_REASON
                    or source.get('terms_reference') != DFB_TERMS_REFERENCE
                    or any(source.get(key) is not None for key in (
                        'requested_utc', 'completed_utc', 'redirect_policy', 'final_url', 'http_status'))):
                raise ValueError('INVALID_INDEX_ORIGIN_POLICY_SKIP')
            continue
        if source.get('source_url') != SOURCES[provider] or source.get('redirect_policy') != 'DENY_ALL':
            raise ValueError('INVALID_INDEX_ORIGIN_ENDPOINT')
        requested, completed = utc(source.get('requested_utc')), utc(source.get('completed_utc'))
        if not previous <= requested <= completed <= bound:
            raise ValueError('INVALID_INDEX_ORIGIN_CHRONOLOGY')
        previous = completed
        if source.get('status') == 'ERROR':
            if (set(source) != base | {'http_status', 'error_type', 'error_code'}
                    or source.get('final_url') is not None
                    or not isinstance(source.get('error_type'), str)
                    or not re.fullmatch(r'[A-Za-z][A-Za-z0-9]{0,63}', source['error_type'])
                    or not isinstance(source.get('error_code'), str) or source['error_code'] not in ERROR_CODES
                    or (source.get('http_status') is not None and (
                        type(source['http_status']) is not int or not 100 <= source['http_status'] <= 599))):
                raise ValueError('INVALID_INDEX_ORIGIN_ERROR_RECEIPT')
            continue
        if (set(source) != base | {'raw_file', 'raw_sha256', 'bytes', 'http_status', 'content_type'}
                or source.get('status') != 'FETCHED_UNVERIFIED'
                or source.get('final_url') != SOURCES[provider]
                or source.get('raw_file') != provider.lower() + '.html'
                or not isinstance(source.get('raw_sha256'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', source['raw_sha256'])
                or type(source.get('bytes')) is not int or not 0 < source['bytes'] <= MAX_BYTES
                or type(source.get('http_status')) is not int or source['http_status'] != 200
                or source.get('content_type') not in ('text/html', 'application/xhtml+xml')):
            raise ValueError('INVALID_INDEX_ORIGIN_SUCCESS_RECEIPT')
