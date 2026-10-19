"""Collect at most three fixed NDR detail pages as quarantined display evidence.

The index manifest and bytes are revalidated and reparsed locally before any
HTTP request. An explicit completed display remains a single-source observation,
never independent result authentication or model-scoring evidence.
"""
import argparse
import hashlib
import json
import os
import re
import stat
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ops.ndr_completion_observations import parse_detail
from ops.ndr_result_observations import FIXTURE_PATH, _checked_path, observe

MAX_REQUESTS = 3
MAX_BYTES = 3_000_000
REQUEST_TIMEOUT = 15
SAFE_REASON = re.compile(r'[A-Z][A-Z0-9_]{1,95}\Z')
PROVIDER_ID = re.compile(r'[1-9][0-9]{0,9}\Z')


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # urllib raises HTTPError for redirects without sending a second GET.
        return None


def fetch_detail(url):
    """One bounded GET, preserving only an exact allowlisted HTML response."""
    if not isinstance(url, str) or not FIXTURE_PATH.fullmatch(url):
        raise ValueError('INVALID_NDR_DETAIL_URL')
    request = Request(url, method='GET', headers={
        'User-Agent': 'football-king-shadow-research/1.0',
        'Accept': 'text/html,application/xhtml+xml',
    })
    with build_opener(_NoRedirects()).open(request, timeout=REQUEST_TIMEOUT) as response:
        status = getattr(response, 'status', None)
        if type(status) is not int or status != 200:
            raise ValueError('NON_200_NDR_DETAIL_RESPONSE')
        final_url = response.geturl()
        if final_url != url:
            raise ValueError('UNEXPECTED_NDR_DETAIL_FINAL_URL')
        content_type = response.headers.get('Content-Type', '')
        if not isinstance(content_type, str):
            raise ValueError('NON_HTML_NDR_DETAIL_RESPONSE')
        media_type = content_type.split(';', 1)[0].strip().lower()
        if media_type not in {'text/html', 'application/xhtml+xml'}:
            raise ValueError('NON_HTML_NDR_DETAIL_RESPONSE')
        raw = response.read(MAX_BYTES + 1)
        if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
            raise ValueError('INVALID_OR_OVERSIZED_NDR_DETAIL_RESPONSE')
    return raw, status, media_type, final_url


def _safe_report(captured):
    return {
        'schema': 'football-king-ndr-completion-observations-v1',
        'captured_utc': captured, 'status': 'HOLD',
        'production_recommendations': 'DISABLED', 'candidate_only': True,
        'independently_verified': False, 'eligible_for_model_scoring': False,
        'source_available': False, 'input_rejected': False,
        'max_requests': MAX_REQUESTS, 'requests_attempted': 0, 'attempt_count': 0,
        'source_index': None, 'sources': [], 'observations': [],
        'observation_count': 0, 'rejections': [], 'fetch_errors': [],
        'limitations': [
            'NDR_COMPLETED_DISPLAY_IS_SINGLE_SOURCE_OBSERVATION_ONLY',
            'SOURCE_IDENTITY_AND_CAPTURE_TIME_NOT_INDEPENDENTLY_AUTHENTICATED',
            'REGULATION_TIME_AND_REAL_KICKOFF_NOT_INDEPENDENTLY_AUTHENTICATED',
            'NO_LINK_TO_SEALED_FORECAST_IDENTITIES_OR_MODEL_SCORING',
        ],
    }


def _output_directory(raw_dir, output_dir):
    output = _checked_path(output_dir)
    lexical_raw = Path(raw_dir).absolute()
    resolved_raw = lexical_raw.resolve(strict=False)
    for source in (lexical_raw, resolved_raw):
        if output == source or source in output.parents:
            raise ValueError('OUTPUT_MUST_NOT_MODIFY_RAW_EVIDENCE')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('OUTPUT_DIRECTORY_MUST_BE_FRESH_AND_EMPTY')
    # Validate parent chains before creation; nested symlinks are never followed.
    output.mkdir(parents=True, exist_ok=True)
    return _checked_path(output)


def _write_new(folder, filename, raw):
    # Fixed filenames, exclusive creation and nofollow prevent old evidence from
    # being replaced or a newly introduced link from becoming a write target.
    target = _checked_path(folder / filename)
    if target.parent != folder:
        raise ValueError('INVALID_COLLECTOR_OUTPUT_PATH')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(target, flags, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('INVALID_COLLECTOR_OUTPUT_FILE')
        stream.write(raw)


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def _write_reports(folder, report):
    manifest = {
        'schema': 'football-king-ndr-completion-raw-evidence-v1',
        'captured_utc': report['captured_utc'], 'status': 'HOLD',
        'production_recommendations': 'DISABLED', 'independently_verified': False,
        'eligible_for_model_scoring': False, 'source_index': report['source_index'],
        'max_requests': MAX_REQUESTS, 'requests_attempted': report['requests_attempted'],
        'sources': report['sources'],
    }
    _write_new(folder, 'manifest.json', _json_bytes(manifest))
    _write_new(folder, 'report.json', _json_bytes(report))


def _validated_rows(report):
    """Check the complete recomputed cohort before selecting any network target."""
    rows = report.get('observations')
    if not isinstance(rows, list) or type(report.get('observation_count')) is not int or report['observation_count'] != len(rows):
        raise ValueError('INVALID_RECOMPUTED_NDR_ROWS')
    seen_ids, seen_matches = set(), set()
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError('INVALID_RECOMPUTED_NDR_ROW')
        fixture_id, url = item.get('provider_fixture_id'), item.get('fixture_url')
        if not isinstance(fixture_id, str) or not PROVIDER_ID.fullmatch(fixture_id) or not isinstance(url, str):
            raise ValueError('INVALID_RECOMPUTED_NDR_IDENTITY')
        match = FIXTURE_PATH.fullmatch(url)
        if not match or match.group(1) != fixture_id or item.get('provider') != 'NDR':
            raise ValueError('INVALID_RECOMPUTED_NDR_IDENTITY')
        home, away = item.get('home_provider_team_id'), item.get('away_provider_team_id')
        if not all(isinstance(value, str) and PROVIDER_ID.fullmatch(value) for value in (home, away)) or home == away:
            raise ValueError('INVALID_RECOMPUTED_NDR_TEAM_IDENTITY')
        local_date = item.get('date_local')
        if not isinstance(local_date, str) or date.fromisoformat(local_date).isoformat() != local_date:
            raise ValueError('INVALID_RECOMPUTED_NDR_DATE')
        score = item.get('display_score')
        if not isinstance(score, dict) or set(score) != {'home', 'away'} or any(type(value) is not int or not 0 <= value <= 30 for value in score.values()):
            raise ValueError('INVALID_RECOMPUTED_NDR_SCORE')
        if item.get('candidate_only') is not True or item.get('independently_verified') is not False or item.get('eligible_for_model_scoring') is not False:
            raise ValueError('UNSAFE_RECOMPUTED_NDR_ROW')
        identity = (local_date, *sorted((home, away)))
        if fixture_id in seen_ids or identity in seen_matches:
            raise ValueError('DUPLICATE_RECOMPUTED_NDR_IDENTITY')
        seen_ids.add(fixture_id)
        seen_matches.add(identity)
    return rows


def _reason(exc, fallback):
    # HTML, URLs, exception messages and arbitrary response headers are never logs.
    message = str(exc) if isinstance(exc, ValueError) else ''
    return message if SAFE_REASON.fullmatch(message) else fallback


def collect(raw_dir, output_dir, limit=MAX_REQUESTS, now=None):
    """Fetch row-derived pages serially; invalid index integrity makes zero GETs."""
    if type(limit) is not int or not 1 <= limit <= MAX_REQUESTS:
        raise ValueError('INVALID_NDR_DETAIL_REQUEST_LIMIT')
    current = datetime.now(timezone.utc) if now is None else now
    if (not isinstance(current, datetime) or current.tzinfo is None
            or current.utcoffset() is None or current.utcoffset().total_seconds() != 0):
        raise ValueError('INVALID_CURRENT_UTC_TIME')
    folder = _output_directory(raw_dir, output_dir)
    report = _safe_report(current.isoformat())
    try:
        index = observe(raw_dir, now=current)
        rows = _validated_rows(index)
    except (OSError, ValueError, TypeError, RecursionError):
        report.update(input_rejected=True, error='NDR_COMPLETION_SOURCE_INPUT_REJECTED')
        _write_reports(folder, report)
        return report
    report['source_available'] = index.get('source_available') is True
    report['source_index'] = index.get('source')
    if not report['source_available']:
        report['source_unavailable_reason'] = 'NDR_SOURCE_NOT_AVAILABLE'
        _write_reports(folder, report)
        return report
    # Ordering is deliberately inherited from the strictly parsed source table.
    for item in rows[:limit]:
        fixture_id, url = item['provider_fixture_id'], item['fixture_url']
        report['requests_attempted'] += 1
        report['attempt_count'] = report['requests_attempted']
        source = {'provider': 'NDR', 'provider_fixture_id': fixture_id,
                  'source_url': url, 'status': 'ERROR', 'final_url': None,
                  'requested_utc': (now or datetime.now(timezone.utc)).isoformat(),
                  'capture_time_independently_authenticated': False,
                  'source_identity_independently_authenticated': False}
        report['sources'].append(source)
        try:
            raw, status, content_type, final_url = fetch_detail(url)
        except (OSError, ValueError, TypeError, TimeoutError, HTTPError, URLError) as exc:
            reason = _reason(exc, 'NDR_DETAIL_FETCH_FAILED')
            source['error'] = reason
            if isinstance(exc, HTTPError) and type(exc.code) is int and 100 <= exc.code <= 599:
                source['http_status'] = exc.code
            report['fetch_errors'].append({'provider_fixture_id': fixture_id, 'reason': reason})
            continue
        source.update(status='FETCHED_UNVERIFIED', final_url=final_url,
                      captured_utc=(now or datetime.now(timezone.utc)).isoformat(),
                      raw_file=f'ndr-detail-{fixture_id}.html',
                      raw_sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw),
                      http_status=status, content_type=content_type)
        # Keep the successful bounded response even when its display contradicts
        # the index, so the quarantine decision remains inspectable.
        _write_new(folder, source['raw_file'], raw)
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
            report['rejections'].append({'provider_fixture_id': fixture_id,
                                         'reason': _reason(exc, 'NDR_DETAIL_DISPLAY_REJECTED')})
            continue
        observation = dict(observation, status='HOLD', production_recommendations='DISABLED',
                           candidate_only=True, independently_verified=False,
                           eligible_for_model_scoring=False, detail_source=dict(source))
        report['observations'].append(observation)
    report['observation_count'] = len(report['observations'])
    _write_reports(folder, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--limit', type=int, default=MAX_REQUESTS, choices=range(1, MAX_REQUESTS + 1))
    args = parser.parse_args()
    try:
        report = collect(args.raw_dir, args.output_dir, limit=args.limit)
    except (OSError, ValueError, TypeError, RecursionError):
        print(json.dumps({'status': 'HOLD', 'production_recommendations': 'DISABLED',
                          'eligible_for_model_scoring': False,
                          'error': 'NDR_COMPLETION_OUTPUT_OR_CONFIGURATION_REJECTED'}))
        return 1
    print(json.dumps({'status': 'HOLD', 'production_recommendations': 'DISABLED',
                      'eligible_for_model_scoring': False,
                      'requests_attempted': report['requests_attempted'],
                      'observation_count': report['observation_count'],
                      'rejection_count': len(report['rejections']),
                      'fetch_error_count': len(report['fetch_errors'])}))
    return 1 if report['input_rejected'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
