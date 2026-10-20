"""Collect raw public match-result evidence without claiming score verification.

A source fetch is evidence of bytes received, not independent score attestation.
No parsed result from this collector is eligible for model scoring.
"""
import argparse
import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from datetime import datetime as _DateTime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

SOURCES = {
    "DFB": "https://datencenter.dfb.de/de/competitions/bundesliga/seasons/2026-2027/matchday/current",
    "NDR": "https://www.ndr.de/sport/ergebnisse/Alle-Ergebnisse-Fussball-Bundesliga-2026-2027%2Cfussballmaenner-486.html",
}
MAX_BYTES = 3_000_000
REQUEST_TIMEOUT = 15
HTML_MEDIA_TYPES = frozenset({'text/html', 'application/xhtml+xml'})
ERROR_CODES = frozenset({
    'INVALID_SOURCE_URL', 'INVALID_HTTP_STATUS', 'NON_200_RESPONSE',
    'UNEXPECTED_FINAL_URL', 'NON_HTML_RESPONSE', 'EMPTY_OR_INVALID_BODY',
    'SOURCE_TOO_LARGE', 'INVALID_FETCH_RESULT', 'HTTP_REDIRECT_REJECTED',
    'HTTP_ERROR', 'SOURCE_TIMEOUT', 'SOURCE_NETWORK_ERROR', 'SOURCE_OS_ERROR',
    'SOURCE_TYPE_ERROR', 'SOURCE_VALUE_ERROR', 'SOURCE_ERROR',
})


class FetchValidationError(ValueError):
    """A fixed local reason with a typed status, never arbitrary source text."""
    def __init__(self, code, http_status=None):
        if code not in ERROR_CODES:
            raise ValueError('INVALID_LOCAL_ERROR_CODE')
        super().__init__(code)
        self.code = code
        self.http_status = _http_status(http_status)


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # urllib raises HTTPError without requesting the redirect destination.
        return None


def _http_status(value):
    return value if type(value) is int and 100 <= value <= 599 else None


def _validated_response(raw, status, media, final_url, expected_url):
    """Recheck both urllib and dependency-injected results before saving bytes."""
    if _http_status(status) is None:
        raise FetchValidationError('INVALID_HTTP_STATUS')
    if status != 200:
        raise FetchValidationError('NON_200_RESPONSE', status)
    if type(final_url) is not str or final_url != expected_url:
        raise FetchValidationError('UNEXPECTED_FINAL_URL', status)
    if type(media) is not str:
        raise FetchValidationError('NON_HTML_RESPONSE', status)
    normalized = media.split(';', 1)[0].strip().lower()
    if normalized not in HTML_MEDIA_TYPES:
        raise FetchValidationError('NON_HTML_RESPONSE', status)
    if type(raw) is not bytes or not raw:
        raise FetchValidationError('EMPTY_OR_INVALID_BODY', status)
    if len(raw) > MAX_BYTES:
        raise FetchValidationError('SOURCE_TOO_LARGE', status)
    return raw, status, normalized, final_url


def fetch(url, opener=None):
    """One bounded GET to an exact fixed URL, denying every redirect."""
    if type(url) is not str or url not in SOURCES.values():
        raise FetchValidationError('INVALID_SOURCE_URL')
    request = Request(url, method='GET', headers={
        'User-Agent': 'football-king-shadow-research/1.0',
        'Accept': 'text/html,application/xhtml+xml',
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
        if type(media) is not str or media.split(';', 1)[0].strip().lower() not in HTML_MEDIA_TYPES:
            raise FetchValidationError('NON_HTML_RESPONSE', status)
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


def _write_new(folder, filename, raw):
    target = _checked_path(folder / filename)
    if target.parent != folder:
        raise ValueError('INVALID_COLLECTOR_OUTPUT_PATH')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(target, flags, 0o600)
    info = os.fstat(fd)
    try:
        with os.fdopen(fd, 'wb') as stream:
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('INVALID_COLLECTOR_OUTPUT_FILE')
            stream.write(raw)
    except Exception:
        # Delete only the file this invocation exclusively created, never an
        # old file or a replacement link introduced by another writer.
        current = target.lstat()
        if (current.st_dev, current.st_ino) == (info.st_dev, info.st_ino):
            target.unlink()
        raise


def _utc_now(fixed):
    current = datetime.now(timezone.utc) if fixed is None else fixed
    if (not isinstance(current, _DateTime) or current.tzinfo is None
            or current.utcoffset() is None or current.utcoffset().total_seconds() != 0):
        raise ValueError('INVALID_CURRENT_UTC_TIME')
    return current


def _error_record(exc):
    # Safe finite codes are separate from arbitrary exception messages and URLs.
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
    allowed_types = {'FetchValidationError', 'HTTPError', 'URLError', 'TimeoutError',
                     'OSError', 'TypeError', 'ValueError', 'RuntimeError',
                     'FileExistsError', 'FileNotFoundError', 'PermissionError',
                     'ConnectionError', 'ConnectionResetError', 'BrokenPipeError'}
    kind = type(exc).__name__
    return {'error_type': kind if kind in allowed_types else 'Exception',
            'error_code': code, 'http_status': status}

def collect(outdir, getter=fetch, now=None):
    current = _utc_now(now)
    folder = _output_directory(outdir)
    captured = current.isoformat()
    manifest = {"schema": "football-king-external-raw-evidence-v2",
                "captured_utc": captured, "status": "HOLD",
                "independently_verified": False,
                "eligible_for_model_scoring": False,
                "production_recommendations": "DISABLED", "sources": []}
    for provider, url in SOURCES.items():
        requested = _utc_now(now)
        if requested < current:
            raise ValueError('COLLECTOR_CLOCK_MOVED_BACKWARDS')
        entry = {"provider": provider, "source_url": url, "status": "ERROR",
                 "requested_utc": requested.isoformat(), "completed_utc": None,
                 "redirect_policy": "DENY_ALL", "final_url": None}
        try:
            value = getter(url)
            if type(value) is not tuple or len(value) != 4:
                raise FetchValidationError('INVALID_FETCH_RESULT')
            body, http_status, content_type, final_url = _validated_response(*value, url)
            filename = provider.lower() + ".html"
            _write_new(folder, filename, body)
            entry.update(status="FETCHED_UNVERIFIED", raw_file=filename,
                         raw_sha256=hashlib.sha256(body).hexdigest(),
                         bytes=len(body), http_status=http_status,
                         content_type=content_type, final_url=final_url)
        except Exception as exc:
            entry.update(_error_record(exc))
        current = _utc_now(now)
        if current < requested:
            raise ValueError('COLLECTOR_CLOCK_MOVED_BACKWARDS')
        entry['completed_utc'] = current.isoformat()
        manifest["sources"].append(entry)
    _write_new(folder, 'manifest.json',
               (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    return manifest

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    print(json.dumps(collect(args.output_dir), ensure_ascii=False))

if __name__ == "__main__":
    main()
