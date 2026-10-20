"""Retain controlled, bounded JSON responses as unverified research candidates.

Receipts record transport observations; they do not authenticate a publisher,
upstream independence, kickoff, or a regulation-time result.
"""
import argparse
import hashlib
import json
import math
import os
import stat
from datetime import datetime, timezone
from datetime import datetime as _DateTime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

URLS = {
    "OpenLigaDB": "https://api.openligadb.de/getmatchdata/bl1/{year}",
    "OpenFootball": "https://raw.githubusercontent.com/openfootball/football.json/master/{year}-{short_next_year}/de.1.json",
}
MAX_BYTES = 3_000_000
REQUEST_TIMEOUT = 15
ERROR_CODES = frozenset({
    'INVALID_SOURCE_URL', 'INVALID_HTTP_STATUS', 'NON_200_RESPONSE',
    'UNEXPECTED_FINAL_URL', 'NON_JSON_RESPONSE', 'EMPTY_OR_INVALID_BODY',
    'SOURCE_TOO_LARGE', 'INVALID_FETCH_RESULT', 'INVALID_JSON',
    'UNEXPECTED_OPENLIGADB_SCHEMA', 'UNEXPECTED_OPENFOOTBALL_SCHEMA',
    'HTTP_REDIRECT_REJECTED', 'HTTP_ERROR', 'SOURCE_TIMEOUT',
    'SOURCE_NETWORK_ERROR', 'SOURCE_OS_ERROR', 'SOURCE_TYPE_ERROR',
    'SOURCE_VALUE_ERROR', 'SOURCE_ERROR',
})
ERROR_TYPES = frozenset({
    'FetchValidationError', 'HTTPError', 'URLError', 'TimeoutError', 'OSError',
    'TypeError', 'ValueError', 'RuntimeError', 'FileExistsError',
    'FileNotFoundError', 'PermissionError', 'ConnectionError',
    'ConnectionResetError', 'BrokenPipeError', 'Exception',
})


def source_urls(year):
    """The exact two endpoints, in their fixed request order."""
    if type(year) is not int or not 2000 <= year <= 2100:
        raise ValueError('INVALID_SEASON')
    return {provider: template.format(year=year, short_next_year=str(year + 1)[-2:])
            for provider, template in URLS.items()}


_ENDPOINTS = {url: provider for year in range(2000, 2101)
              for provider, url in source_urls(year).items()}


class FetchValidationError(ValueError):
    """Finite local reason; never arbitrary source text or redirect targets."""
    def __init__(self, code, http_status=None):
        if code not in ERROR_CODES:
            raise ValueError('INVALID_LOCAL_ERROR_CODE')
        super().__init__(code)
        self.code = code
        self.http_status = _http_status(http_status)


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _http_status(value):
    return value if type(value) is int and 100 <= value <= 599 else None


def _provider_for_url(url):
    if type(url) is not str or url not in _ENDPOINTS:
        raise FetchValidationError('INVALID_SOURCE_URL')
    return _ENDPOINTS[url]


def allowed_media_types(provider):
    # GitHub's raw JSON endpoint serves text/plain. This exception is restricted
    # to that exact provider and exact endpoint, never the API endpoint.
    return ('application/json', 'text/plain') if provider == 'OpenFootball' else ('application/json',)


def _no_duplicate_keys(pairs):
    value = {}
    for key, entry in pairs:
        if key in value:
            raise ValueError('DUPLICATE_JSON_KEY')
        value[key] = entry
    return value


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('NON_FINITE_JSON_NUMBER')
    return result


def _no_constant(value):
    raise ValueError('NON_FINITE_JSON_NUMBER')


def strict_json_loads(raw):
    """Read strict UTF-8 JSON, rejecting duplicate keys and nonfinite numbers."""
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_no_duplicate_keys,
                      parse_float=_finite_float, parse_constant=_no_constant)


def validate_json_body(raw, provider):
    """Validate the provider's container shape, without certifying any row."""
    try:
        parsed = strict_json_loads(raw)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise FetchValidationError('INVALID_JSON') from exc
    if provider == 'OpenLigaDB' and not isinstance(parsed, list):
        raise FetchValidationError('UNEXPECTED_OPENLIGADB_SCHEMA')
    if provider == 'OpenFootball' and (not isinstance(parsed, dict)
                                     or not isinstance(parsed.get('matches'), list)):
        raise FetchValidationError('UNEXPECTED_OPENFOOTBALL_SCHEMA')
    if provider not in URLS:
        raise FetchValidationError('INVALID_SOURCE_URL')
    return parsed


def _validated_response(raw, status, media, final_url, expected_url):
    """Recheck urllib and dependency-injected results before saving bytes."""
    provider = _provider_for_url(expected_url)
    if _http_status(status) is None:
        raise FetchValidationError('INVALID_HTTP_STATUS')
    if status != 200:
        raise FetchValidationError('NON_200_RESPONSE', status)
    if type(final_url) is not str or final_url != expected_url:
        raise FetchValidationError('UNEXPECTED_FINAL_URL', status)
    if type(media) is not str:
        raise FetchValidationError('NON_JSON_RESPONSE', status)
    normalized = media.split(';', 1)[0].strip().lower()
    if normalized not in allowed_media_types(provider):
        raise FetchValidationError('NON_JSON_RESPONSE', status)
    if type(raw) is not bytes or not raw:
        raise FetchValidationError('EMPTY_OR_INVALID_BODY', status)
    if len(raw) > MAX_BYTES:
        raise FetchValidationError('SOURCE_TOO_LARGE', status)
    try:
        validate_json_body(raw, provider)
    except FetchValidationError as exc:
        raise FetchValidationError(exc.code, status) from exc
    return raw, status, normalized, final_url


def fetch(url, opener=None):
    """One bounded GET to an exact season endpoint, with all redirects denied."""
    provider = _provider_for_url(url)
    request = Request(url, method='GET', headers={
        'User-Agent': 'football-king-shadow-research/1.0',
        'Accept': ','.join(allowed_media_types(provider)),
    })
    open_request = build_opener(_NoRedirects()).open if opener is None else opener
    with open_request(request, timeout=REQUEST_TIMEOUT) as response:
        status = getattr(response, 'status', None)
        if _http_status(status) is None:
            raise FetchValidationError('INVALID_HTTP_STATUS')
        if status != 200:
            raise FetchValidationError('NON_200_RESPONSE', status)
        final_url = response.geturl()
        if type(final_url) is not str or final_url != url:
            raise FetchValidationError('UNEXPECTED_FINAL_URL', status)
        media = response.headers.get('Content-Type', '')
        if type(media) is not str or media.split(';', 1)[0].strip().lower() not in allowed_media_types(provider):
            raise FetchValidationError('NON_JSON_RESPONSE', status)
        return _validated_response(response.read(MAX_BYTES + 1), status, media, final_url, url)


def _checked_path(value):
    path = Path(value).absolute()
    if '..' in path.parts:
        raise ValueError('INVALID_COLLECTOR_OUTPUT_PATH')
    for candidate in reversed((path, *path.parents)):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError('SYMLINK_COLLECTOR_OUTPUT_PATH')
    return path


def _output_directory(value):
    folder = _checked_path(value)
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise ValueError('OUTPUT_DIRECTORY_MUST_BE_FRESH_AND_EMPTY')
    folder.mkdir(parents=True, exist_ok=True)
    return _checked_path(folder)


def _open_directory(folder):
    """Open every directory component without following a symlink."""
    path = _checked_path(folder)
    flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path.anchor, flags)
    try:
        for part in path.parts[1:]:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _write_new(folder, filename, raw):
    if Path(filename).name != filename or filename in ('', '.', '..'):
        raise ValueError('INVALID_COLLECTOR_OUTPUT_PATH')
    directory = _open_directory(folder)
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(filename, flags, 0o600, dir_fd=directory)
        info = os.fstat(fd)
        try:
            with os.fdopen(fd, 'wb') as stream:
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError('INVALID_COLLECTOR_OUTPUT_FILE')
                stream.write(raw)
        except BaseException:
            current = os.stat(filename, dir_fd=directory, follow_symlinks=False)
            if (current.st_dev, current.st_ino) == (info.st_dev, info.st_ino):
                os.unlink(filename, dir_fd=directory)
            raise
        return info.st_dev, info.st_ino
    finally:
        os.close(directory)


def _cleanup_created(folder, created):
    # A fatal filesystem or clock error must not publish a partial capture.
    # Only unlink our own exclusive creations; preserve any replacement file.
    try:
        directory = _open_directory(folder)
    except OSError:
        return
    except ValueError:
        return
    try:
        for filename, identity in reversed(created):
            try:
                info = os.stat(filename, dir_fd=directory, follow_symlinks=False)
                if (info.st_dev, info.st_ino) == identity:
                    os.unlink(filename, dir_fd=directory)
            except FileNotFoundError:
                pass
    finally:
        os.close(directory)


def _utc_now(fixed):
    current = datetime.now(timezone.utc) if fixed is None else fixed
    if (not isinstance(current, _DateTime) or current.tzinfo is None
            or current.utcoffset() is None):
        raise ValueError('INVALID_CAPTURE_TIME')
    return current.astimezone(timezone.utc)


def _error_record(exc):
    status = None
    if isinstance(exc, FetchValidationError):
        code, status = exc.code, exc.http_status
    elif isinstance(exc, HTTPError):
        status = _http_status(exc.code)
        code = 'HTTP_REDIRECT_REJECTED' if status in {301, 302, 303, 307, 308} else 'HTTP_ERROR'
    elif isinstance(exc, TimeoutError):
        code = 'SOURCE_TIMEOUT'
    elif isinstance(exc, URLError):
        code = 'SOURCE_TIMEOUT' if isinstance(exc.reason, TimeoutError) else 'SOURCE_NETWORK_ERROR'
    elif isinstance(exc, OSError):
        code = 'SOURCE_OS_ERROR'
    elif isinstance(exc, TypeError):
        code = 'SOURCE_TYPE_ERROR'
    elif isinstance(exc, ValueError):
        code = 'SOURCE_VALUE_ERROR'
    else:
        code = 'SOURCE_ERROR'
    kind = type(exc).__name__
    return {'error_type': kind if kind in ERROR_TYPES else 'Exception',
            'error_code': code, 'http_status': status}


def collect(year, outdir, getter=fetch, now=None):
    urls = source_urls(year)
    current = _utc_now(now)
    folder = _output_directory(outdir)
    manifest = {'schema': 'football-king-raw-ft-source-candidates-v2',
                'captured_utc': current.isoformat(), 'season_start': year,
                'status': 'HOLD', 'independently_verified': False,
                'eligible_for_model_scoring': False,
                'production_recommendations': 'DISABLED', 'sources': []}
    created = []
    try:
        for provider, url in urls.items():
            requested = _utc_now(now)
            if requested < current:
                raise ValueError('COLLECTOR_CLOCK_MOVED_BACKWARDS')
            entry = {'provider': provider, 'source_url': url, 'status': 'ERROR',
                     'requested_utc': requested.isoformat(), 'completed_utc': None,
                     'redirect_policy': 'DENY_ALL', 'final_url': None}
            try:
                value = getter(url)
                if type(value) is not tuple or len(value) != 4:
                    raise FetchValidationError('INVALID_FETCH_RESULT')
                body, http_status, content_type, final_url = _validated_response(*value, url)
            except Exception as exc:
                entry.update(_error_record(exc))
            else:
                filename = provider.lower() + '.json'
                identity = _write_new(folder, filename, body)
                created.append((filename, identity))
                entry.update(status='FETCHED_UNVERIFIED', raw_file=filename,
                             raw_sha256=hashlib.sha256(body).hexdigest(), bytes=len(body),
                             http_status=http_status, content_type=content_type, final_url=final_url)
            current = _utc_now(now)
            if current < requested:
                raise ValueError('COLLECTOR_CLOCK_MOVED_BACKWARDS')
            entry['completed_utc'] = current.isoformat()
            manifest['sources'].append(entry)
        raw_manifest = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        identity = _write_new(folder, 'manifest.json', raw_manifest)
        created.append(('manifest.json', identity))
        return manifest
    except BaseException:
        _cleanup_created(folder, created)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--year', type=int, required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    print(json.dumps(collect(args.year, args.output_dir), ensure_ascii=False))


if __name__ == '__main__':
    main()
