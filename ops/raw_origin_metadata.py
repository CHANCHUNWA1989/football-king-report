"""Structurally replay controlled API receipts; never authenticate result truth.

Original raw bytes, content checks and authenticated capture provenance remain
separate obligations. Historical v1 manifests cannot acquire missing receipts.
"""
from datetime import datetime, timezone
import re

if __package__:
    from .shadow_raw_source_collector import (ERROR_CODES, ERROR_TYPES, MAX_BYTES,
                                             allowed_media_types, source_urls)
else:
    from shadow_raw_source_collector import (ERROR_CODES, ERROR_TYPES, MAX_BYTES,
                                            allowed_media_types, source_urls)

SCHEMA = 'football-king-raw-ft-source-candidates-v2'
LEGACY_SCHEMA = 'football-king-raw-ft-source-candidates-v1'
UTC_TIME = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)\Z')


def utc(value):
    if not isinstance(value, str) or not UTC_TIME.fullmatch(value):
        raise ValueError('INVALID_RAW_ORIGIN_UTC')
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('INVALID_RAW_ORIGIN_UTC') from exc


def validate_manifest(manifest, *, now, before=None):
    """Check exact v2 keys, endpoints, disjoint receipts and serial UTC bounds.

    Success means structural consistency only. It does not authenticate HTTP
    metadata, source identity, original bytes, upstream independence or scores.
    """
    if (not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None
            or (before is not None and (not isinstance(before, datetime)
                or before.tzinfo is None or before.utcoffset() is None))):
        raise ValueError('INVALID_RAW_ORIGIN_CLOCK')
    now = now.astimezone(timezone.utc)
    bound = min(now, before.astimezone(timezone.utc)) if before is not None else now
    keys = {'schema', 'captured_utc', 'season_start', 'status', 'independently_verified',
            'eligible_for_model_scoring', 'production_recommendations', 'sources'}
    if (not isinstance(manifest, dict) or set(manifest) != keys
            or manifest.get('schema') != SCHEMA or manifest.get('status') != 'HOLD'
            or manifest.get('independently_verified') is not False
            or manifest.get('eligible_for_model_scoring') is not False
            or manifest.get('production_recommendations') != 'DISABLED'):
        raise ValueError('INVALID_RAW_ORIGIN_MANIFEST')
    try:
        urls = source_urls(manifest['season_start'])
    except ValueError as exc:
        raise ValueError('INVALID_RAW_ORIGIN_SEASON') from exc
    sources = manifest['sources']
    if (not isinstance(sources, list) or len(sources) != 2
            or any(not isinstance(source, dict) for source in sources)
            or [source.get('provider') for source in sources] != list(urls)):
        raise ValueError('INVALID_RAW_ORIGIN_PROVIDER_ORDER')
    previous = utc(manifest['captured_utc'])
    if previous > bound:
        raise ValueError('INVALID_RAW_ORIGIN_CHRONOLOGY')
    base = {'provider', 'source_url', 'status', 'requested_utc', 'completed_utc',
            'redirect_policy', 'final_url'}
    for source in sources:
        provider = source['provider']
        if source.get('source_url') != urls[provider] or source.get('redirect_policy') != 'DENY_ALL':
            raise ValueError('INVALID_RAW_ORIGIN_ENDPOINT')
        requested, completed = utc(source.get('requested_utc')), utc(source.get('completed_utc'))
        if not previous <= requested <= completed <= bound:
            raise ValueError('INVALID_RAW_ORIGIN_CHRONOLOGY')
        previous = completed
        if source.get('status') == 'ERROR':
            if (set(source) != base | {'http_status', 'error_type', 'error_code'}
                    or source.get('final_url') is not None
                    or not isinstance(source.get('error_type'), str)
                    or source['error_type'] not in ERROR_TYPES
                    or not isinstance(source.get('error_code'), str)
                    or source['error_code'] not in ERROR_CODES
                    or (source.get('http_status') is not None and (
                        type(source['http_status']) is not int or not 100 <= source['http_status'] <= 599))):
                raise ValueError('INVALID_RAW_ORIGIN_ERROR_RECEIPT')
            continue
        if (set(source) != base | {'raw_file', 'raw_sha256', 'bytes', 'http_status', 'content_type'}
                or source.get('status') != 'FETCHED_UNVERIFIED'
                or source.get('final_url') != urls[provider]
                or source.get('raw_file') != provider.lower() + '.json'
                or not isinstance(source.get('raw_sha256'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', source['raw_sha256'])
                or type(source.get('bytes')) is not int or not 0 < source['bytes'] <= MAX_BYTES
                or type(source.get('http_status')) is not int or source['http_status'] != 200
                or source.get('content_type') not in allowed_media_types(provider)):
            raise ValueError('INVALID_RAW_ORIGIN_SUCCESS_RECEIPT')
