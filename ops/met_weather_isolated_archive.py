"""HOLD-only MET Norway city-weather archive: isolated writer and verified reader.

Fixed GitHub repo/ref/path, append-only per-run gzip, CAS latest, no main PUT.
The iPhone consumer must use this pinned branch, never stale main data.
No external weather API calls, bookmaker quotes, model inputs or predictions.
"""
import argparse
import base64
import gzip
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPRedirectHandler

from met_weather_guard import validate

REPO = "CHANCHUNWA1989/football-king-report"
BRANCH = "research/met-weather-archive"
LATEST = "sources/weather_latest.json"
HISTORY = "sources/weather_history/"
RUN = re.compile(r"[1-9][0-9]{0,15}\Z")
ATTEMPT = re.compile(r"[1-9][0-9]{0,2}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
HISTORY_FILE = re.compile(
    r"sources/weather_history/[0-9]{4}/[0-9]{2}/[0-9]{2}/"
    r"[1-9][0-9]{0,15}-[1-9][0-9]{0,2}\.json\.gz\Z")
MAX_REPORT = 400_000
MAX_GZIP = 300_000
MAX_REPLY = 750_000


class WeatherHold(ValueError):
    """Fail closed; never write the default GitHub branch."""


class NoRedirect(HTTPRedirectHandler):
    """Never pass GitHub bearer tokens or writes across HTTP redirects."""
    def redirect_request(self, request, *args, **kwargs):
        return None


def _blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def _json(raw):
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                raise WeatherHold("DUPLICATE_WEATHER_JSON_KEY")
            obj[k] = v
        return obj
    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError, TypeError) as exc:
        if isinstance(exc, WeatherHold):
            raise
        raise WeatherHold("INVALID_WEATHER_JSON") from exc


def _checked(raw, *, now):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_REPORT:
        raise WeatherHold("INVALID_WEATHER_SOURCE_SIZE")
    data = _json(raw)
    try:
        captured = validate(data, now=now)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise WeatherHold("UNSAFE_WEATHER_SOURCE") from exc
    return captured, data


def _gzip(raw):
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb",
                       compresslevel=6, mtime=0) as file:
        file.write(raw)
    result = buffer.getvalue()
    if len(result) > MAX_GZIP:
        raise WeatherHold("OVERSIZED_WEATHER_GZIP")
    return result


def _history_path(captured, run_id, attempt):
    if (type(run_id) is not str or RUN.fullmatch(run_id) is None or
            type(attempt) is not str or ATTEMPT.fullmatch(attempt) is None):
        raise WeatherHold("INVALID_WEATHER_ARCHIVE_RUN_IDENTITY")
    return (HISTORY + captured.strftime("%Y/%m/%d/") +
            run_id + "-" + attempt + ".json.gz")


def _get_verified(store, path):
    remote = store.get(path)
    if remote is None:
        return None
    if (not isinstance(remote, tuple) or len(remote) != 2 or
            type(remote[0]) is not bytes or type(remote[1]) is not str or
            SHA.fullmatch(remote[1]) is None or _blob(remote[0]) != remote[1]):
        raise WeatherHold("REMOTE_WEATHER_GIT_BLOB_MISMATCH")
    return remote


def _create_readback(store, path, data):
    present = _get_verified(store, path)
    if present is not None:
        if present[0] != data:
            raise WeatherHold("WEATHER_HISTORY_IMMUTABLE_COLLISION")
        return False
    store.put(path, data)
    readback = _get_verified(store, path)
    if readback is None or readback[0] != data:
        raise WeatherHold("WEATHER_HISTORY_READBACK_FAILED")
    return True


def publish(raw, *, run_id, attempt, store, now):
    captured, data = _checked(raw, now=now)
    path = _history_path(captured, run_id, attempt)
    compressed = _gzip(raw)
    store.verify_branch()
    created_history = _create_readback(store, path, compressed)
    current = _get_verified(store, LATEST)
    if current is not None:
        old_captured, old = _checked(current[0], now=now)
        if captured == old_captured and old != data:
            raise WeatherHold("WEATHER_LATEST_CONFLICTING_SAME_CAPTURE")
        if captured <= old_captured:
            status = "NO_NEW_WEATHER_LATEST"
        else:
            store.put(LATEST, raw, sha=current[1])
            new = _get_verified(store, LATEST)
            if new is None or new[0] != raw:
                raise WeatherHold("WEATHER_LATEST_READBACK_FAILED")
            status = "NEWER_WEATHER_LATEST"
    else:
        store.put(LATEST, raw)
        new = _get_verified(store, LATEST)
        if new is None or new[0] != raw:
            raise WeatherHold("WEATHER_LATEST_READBACK_FAILED")
        status = "NEW_WEATHER_LATEST"
    return {
        "status": "RESEARCH_ONLY_ARCHIVED",
        "reason": status,
        "archive_branch": BRANCH,
        "history_path": path,
        "history_created": created_history,
        "report_sha256": hashlib.sha256(raw).hexdigest(),
        "production_recommendations": "DISABLED",
        "positive_ev_verified": False,
        "main_written": False,
    }


def read_latest(*, store, now):
    """Consumer fail closed on stale/missing/modified isolated-branch data."""
    store.verify_branch()
    remote = _get_verified(store, LATEST)
    if remote is None:
        raise WeatherHold("WEATHER_LATEST_NOT_IN_ISOLATED_ARCHIVE")
    captured, _ = _checked(remote[0], now=now)
    age = now.astimezone(timezone.utc) - captured
    if not -timedelta(minutes=5) <= age <= timedelta(hours=36):
        raise WeatherHold("WEATHER_LATEST_STALE")
    return remote[0]


class GitHubWeatherStore:
    def __init__(self, token):
        if type(token) is not str or not token.strip():
            raise WeatherHold("WEATHER_GITHUB_TOKEN_MISSING")
        self.token = token
        self._opener = build_opener(NoRedirect())

    def _api(self, method, path, *, data=None, missing_ok=False):
        if not (path == "git/ref/heads/" + BRANCH
                or path == "contents/" + LATEST
                or (path.startswith("contents/") and
                    HISTORY_FILE.fullmatch(path[len("contents/"):]) is not None)):
            raise WeatherHold("UNAUTHORIZED_WEATHER_ENDPOINT")
        if method not in ("GET", "PUT"):
            raise WeatherHold("UNAUTHORIZED_WEATHER_METHOD")
        if method == "PUT":
            if (not path.startswith("contents/") or
                    type(data) is not dict or
                    data.get("branch") != BRANCH or
                    type(data.get("content")) is not str or
                    ("sha" in data and (type(data["sha"]) is not str or
                                        SHA.fullmatch(data["sha"]) is None))):
                raise WeatherHold("WEATHER_WRITE_MUST_TARGET_ISOLATED_BRANCH")
        url = "https://api.github.com/repos/" + REPO + "/" + path
        if method == "GET" and path.startswith("contents/"):
            url += "?ref=" + quote(BRANCH, safe="")
        payload = (json.dumps(data, separators=(",", ":")).encode()
                   if data is not None else None)
        req = Request(url, method=method, data=payload, headers={
            "Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "football-king-met-weather-archive-isolated",
        })
        try:
            with self._opener.open(req, timeout=12) as response:
                raw = response.read(MAX_REPLY + 1)
        except HTTPError as exc:
            if exc.code == 404 and missing_ok and method == "GET" and path.startswith("contents/"):
                return None
            if method == "PUT" and exc.code in (409, 422):
                raise WeatherHold("CONCURRENT_WEATHER_ARCHIVE_UPDATE") from exc
            raise WeatherHold("WEATHER_GITHUB_API_DENIED") from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise WeatherHold("WEATHER_GITHUB_API_UNAVAILABLE") from exc
        if not 0 < len(raw) <= MAX_REPLY:
            raise WeatherHold("UNSAFE_WEATHER_API_RESPONSE_SIZE")
        result = _json(raw)
        if type(result) is not dict:
            raise WeatherHold("INVALID_WEATHER_API_RESPONSE")
        return result

    def verify_branch(self):
        ref = self._api("GET", "git/ref/heads/" + BRANCH)
        target = ref.get("object")
        if (ref.get("ref") != "refs/heads/" + BRANCH or
                type(target) is not dict or target.get("type") != "commit" or
                type(target.get("sha")) is not str or
                SHA.fullmatch(target["sha"]) is None):
            raise WeatherHold("WEATHER_ARCHIVE_BRANCH_UNVERIFIED")

    def get(self, path):
        if path != LATEST and HISTORY_FILE.fullmatch(path) is None:
            raise WeatherHold("UNAUTHORIZED_WEATHER_ARCHIVE_PATH")
        obj = self._api("GET", "contents/" + path, missing_ok=True)
        if obj is None:
            return None
        if (obj.get("type") != "file" or obj.get("path") != path or
                obj.get("name") != path.rsplit("/", 1)[1] or
                obj.get("encoding") != "base64" or
                type(obj.get("content")) is not str or
                type(obj.get("size")) is not int or
                type(obj.get("sha")) is not str or
                SHA.fullmatch(obj["sha"]) is None):
            raise WeatherHold("WEATHER_FILE_IDENTITY_MISMATCH")
        try:
            result = base64.b64decode("".join(obj["content"].split()), validate=True)
        except (ValueError, TypeError) as exc:
            raise WeatherHold("WEATHER_FILE_INVALID_BASE64") from exc
        limit = MAX_REPORT if path == LATEST else MAX_GZIP
        if not 0 < len(result) <= limit or len(result) != obj["size"] or _blob(result) != obj["sha"]:
            raise WeatherHold("REMOTE_WEATHER_GIT_BLOB_MISMATCH")
        return result, obj["sha"]

    def put(self, path, data, *, sha=None):
        if path != LATEST and HISTORY_FILE.fullmatch(path) is None:
            raise WeatherHold("UNAUTHORIZED_WEATHER_ARCHIVE_PATH")
        if type(data) is not bytes or not 0 < len(data) <= (MAX_REPORT if path == LATEST else MAX_GZIP):
            raise WeatherHold("UNSAFE_WEATHER_ARCHIVE_PUT_SIZE")
        if path != LATEST and sha is not None:
            raise WeatherHold("WEATHER_HISTORY_MUST_BE_APPEND_ONLY")
        payload = {
            "branch": BRANCH,
            "content": base64.b64encode(data).decode("ascii"),
            "message": "Archive attributed MET Norway city weather research only (HOLD)",
        }
        if sha is not None:
            payload["sha"] = sha
        obj = self._api("PUT", "contents/" + path, data=payload)
        meta = obj.get("content")
        commit = obj.get("commit")
        if (type(meta) is not dict or meta.get("sha") != _blob(data)
                or type(commit) is not dict or
                type(commit.get("sha")) is not str or
                SHA.fullmatch(commit["sha"]) is None):
            raise WeatherHold("WEATHER_ARCHIVE_WRITE_RECEIPT_UNVERIFIED")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    pub = sub.add_parser("publish")
    pub.add_argument("--input", required=True, type=Path)
    pub.add_argument("--run-id", required=True)
    pub.add_argument("--attempt", required=True)
    get = sub.add_parser("read")
    get.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if (os.getenv("GITHUB_REPOSITORY") != REPO or
                os.getenv("GITHUB_REF") != "refs/heads/main"):
            raise WeatherHold("UNAUTHORIZED_WEATHER_WORKFLOW_REF")
        store = GitHubWeatherStore(os.getenv("GH_TOKEN", ""))
        now = datetime.now(timezone.utc)
        if args.action == "publish":
            if args.input.is_symlink() or not args.input.is_file():
                raise WeatherHold("UNSAFE_WEATHER_ARCHIVE_INPUT_PATH")
            raw = args.input.read_bytes()
            receipt = publish(raw, run_id=args.run_id,
                              attempt=args.attempt, store=store, now=now)
        else:
            if args.output.is_symlink() or args.output.exists():
                raise WeatherHold("UNSAFE_WEATHER_READ_OUTPUT_PATH")
            raw = read_latest(store=store, now=now)
            with args.output.open("xb") as out:
                out.write(raw)
            receipt = {
                "status": "ISOLATED_WEATHER_VERIFIED",
                "archive_branch": BRANCH,
                "report_sha256": hashlib.sha256(raw).hexdigest(),
                "production_recommendations": "DISABLED",
            }
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
        return 0
    except (WeatherHold, ValueError, OSError, OverflowError) as exc:
        reason = str(exc) if isinstance(exc, WeatherHold) else "WEATHER_ARCHIVE_FAILURE"
        print("HOLD: " + reason, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
