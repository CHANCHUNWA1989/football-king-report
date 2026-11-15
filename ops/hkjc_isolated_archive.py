"""PR-12: fail-closed, metadata-only HKJC archive on a dedicated research branch.

GitHub Contents PUT is ALWAYS scoped to the exact archive branch. The source
metadata is not licensed raw market data, a tradable quote, a time witness or
permission to bet. Main never receives a write from this module.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from hkjc_free_research import validate

REPO = "CHANCHUNWA1989/football-king-report"
BRANCH = "research/hkjc-free-metadata-archive"
ROOT = "sources/hkjc_free_metadata_archive"
LATEST = ROOT + "/latest.json"
SOURCE = "https://tipsme.hk/zh-HK/developers/docs/odds"
MAX_BYTES = 8192
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
ALLOWED_FIELDS = frozenset({
    "schema", "captured_utc", "provider", "not_direct_hkjc_official_api",
    "status", "reason", "configured", "requests_attempted", "max_requests",
    "free_only", "quota_remaining", "upcoming_hkjc_fixtures_identified",
    "hkjc_boards_checked", "fresh_had_events", "fresh_handicap_events",
    "fresh_totals_events", "fresh_corners_events", "coverage_by_league",
    "source", "external_license_redistribution_verified",
    "raw_quotes_published", "bookmaker_names_published",
    "independent_market_model_calibrated", "not_executable_odds",
    "not_hkjc_account_connected", "can_execute_bet",
    "automatic_model_change", "production_recommendations",
})
ALLOWED_REASONS = frozenset({
    "SET_TIPSME_API_KEY", "NO_ELIGIBLE_HKJC_BOARD",
    "SCHEDULE_LOOKUP_FAILED", "FREE_DAILY_QUOTA_RESERVE",
    "FREE_SCOPE_DENIED_OR_AUTH_REJECTED", "AUTH_REJECTED",
    "RATE_LIMITED", "FRESH_READ_ONLY_THIRD_PARTY_HKJC_RESEARCH",
})


class ArchiveHold(ValueError):
    pass


def _clock(value):
    if type(value) is not str or len(value) > 55:
        raise ArchiveHold("INVALID_CAPTURE_CLOCK")
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArchiveHold("INVALID_CAPTURE_CLOCK") from exc
    if d.tzinfo is None or d.utcoffset() is None:
        raise ArchiveHold("UNZONED_CAPTURE_CLOCK")
    return d.astimezone(timezone.utc)


def _canonical(item):
    try:
        raw = (json.dumps(item, ensure_ascii=False, sort_keys=True,
                          allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")
    except (ValueError, TypeError, OverflowError) as exc:
        raise ArchiveHold("INVALID_METADATA_JSON") from exc
    if not 0 < len(raw) <= MAX_BYTES:
        raise ArchiveHold("METADATA_TOO_LARGE")
    return raw


def _sanitized(document):
    if type(document) is not dict or set(document) != ALLOWED_FIELDS:
        raise ArchiveHold("UNRECOGNIZED_OR_MISSING_METADATA_FIELDS")
    try:
        validate(document)
    except (ValueError, TypeError, KeyError) as exc:
        raise ArchiveHold("UNSAFE_HKJC_METADATA") from exc
    if (document["source"] != SOURCE
            or type(document["reason"]) is not str
            or document["reason"] not in ALLOWED_REASONS
            or type(document["configured"]) is not bool
            or (document["quota_remaining"] is not None and (
                type(document["quota_remaining"]) is not int
                or not 0 <= document["quota_remaining"] <= 10**8))):
        raise ArchiveHold("UNVERIFIED_METADATA_OR_SOURCE")
    return _canonical(document)


def _id(value, name):
    if type(value) is not int or not 1 <= value < 10**15:
        raise ArchiveHold("INVALID_" + name)
    return value


def _parse_unique(text):
    def no_duplicate(pairs):
        d = {}
        for key, value in pairs:
            if key in d:
                raise ArchiveHold("DUPLICATE_JSON_KEY")
            d[key] = value
        return d
    try:
        return json.loads(text, object_pairs_hook=no_duplicate,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              ArchiveHold("NONFINITE_JSON")))
    except ArchiveHold:
        raise
    except (TypeError, ValueError) as exc:
        raise ArchiveHold("INVALID_JSON") from exc


def archive(document, *, run_id, attempt, store, now):
    """Preserve immutable run history, then compare-and-swap isolated latest."""
    run_id, attempt = _id(run_id, "RUN_ID"), _id(attempt, "RUN_ATTEMPT")
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ArchiveHold("INVALID_ARCHIVE_CLOCK")
    timestamp = _clock(document.get("captured_utc") if type(document) is dict else None)
    right_now = now.astimezone(timezone.utc)
    if not right_now - timedelta(hours=24) <= timestamp <= right_now + timedelta(minutes=5):
        raise ArchiveHold("STALE_OR_FUTURE_ARCHIVE")
    raw = _sanitized(document)
    digest = hashlib.sha256(raw).hexdigest()
    store.verify_branch()
    key = (timestamp.strftime("%Y/%m/%d/%Y%m%dT%H%M%S%fZ")
           + f"-run{run_id}-attempt{attempt}.json")
    history = ROOT + "/history/" + key

    existing = store.get(history)
    if existing is None:
        store.put(history, raw, sha=None)
    elif existing[0] != raw:
        raise ArchiveHold("HISTORICAL_RUN_IDENTITY_CONFLICT")

    latest_result = "UNCHANGED"
    for _ in range(4):
        prior = store.get(LATEST)
        if prior is not None:
            try:
                old = _parse_unique(prior[0].decode("utf-8"))
                old_time = _clock(old["captured_utc"])
                _sanitized(old)
            except (ValueError, UnicodeError, KeyError, TypeError) as exc:
                raise ArchiveHold("PREVIOUS_METADATA_CORRUPT") from exc
            if old_time > timestamp:
                latest_result = "NEWER_LATEST_PRESERVED"
                break
            if old_time == timestamp:
                if prior[0] != raw:
                    raise ArchiveHold("SAME_CAPTURE_DIFFERENT_METADATA")
                latest_result = "IDENTICAL_LATEST_PRESERVED"
                break
        try:
            store.put(LATEST, raw, sha=None if prior is None else prior[1])
            latest_result = "LATEST_UPDATED"
            break
        except ArchiveHold as exc:
            if str(exc) != "CONCURRENT_WRITE_CONFLICT":
                raise
    else:
        raise ArchiveHold("LATEST_CAS_RETRY_EXHAUSTED")
    return {
        "status": "RESEARCH_ARCHIVED_ISOLATED",
        "archive_branch": BRANCH,
        "history_path": history,
        "history_sha256": digest,
        "latest_result": latest_result,
        "real_source_rights_verified": False,
        "independent_market_verified": False,
        "can_execute_bet": False,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }


class GitHubArchiveStore:
    """Only fixed GitHub Contents routes; all PUT bodies pin research branch."""

    def __init__(self, token):
        if type(token) is not str or not token.strip():
            raise ArchiveHold("GITHUB_ARCHIVE_TOKEN_MISSING")
        self._token = token

    def _request(self, method, path, *, payload=None, allow_404=False):
        if type(path) is not str or not (
            path == "git/ref/heads/" + BRANCH
            or path.startswith("contents/" + ROOT + "/")
        ):
            raise ArchiveHold("UNAUTHORIZED_GITHUB_ARCHIVE_PATH")
        data = None
        if payload is not None:
            if (method != "PUT" or not path.startswith("contents/" + ROOT + "/")
                    or payload.get("branch") != BRANCH):
                raise ArchiveHold("UNAUTHORIZED_GITHUB_ARCHIVE_WRITE")
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        url = "https://api.github.com/repos/" + REPO + "/" + path
        if method == "GET" and path.startswith("contents/"):
            url += "?ref=" + quote(BRANCH, safe="")
        req = Request(url, data=data, method=method, headers={
            "Authorization": "Bearer " + self._token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "football-king-isolated-hkjc-archive",
        })
        try:
            with urlopen(req, timeout=15) as response:
                raw = response.read(96_001)
        except HTTPError as exc:
            if allow_404 and exc.code == 404:
                return None
            if method == "PUT" and exc.code in (409, 422):
                raise ArchiveHold("CONCURRENT_WRITE_CONFLICT") from exc
            raise ArchiveHold("GITHUB_ARCHIVE_API_UNAVAILABLE") from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise ArchiveHold("GITHUB_ARCHIVE_API_UNAVAILABLE") from exc
        if not raw or len(raw) > 96_000:
            raise ArchiveHold("INVALID_GITHUB_API_REPLY")
        out = _parse_unique(raw.decode("utf-8"))
        if type(out) is not dict:
            raise ArchiveHold("INVALID_GITHUB_API_REPLY")
        return out

    def verify_branch(self):
        ref = self._request("GET", "git/ref/heads/" + BRANCH)
        target = ref.get("object") if type(ref) is dict else None
        if (ref.get("ref") != "refs/heads/" + BRANCH
                or type(target) is not dict or target.get("type") != "commit"
                or type(target.get("sha")) is not str
                or SHA40.fullmatch(target["sha"]) is None):
            raise ArchiveHold("ISOLATED_ARCHIVE_BRANCH_UNVERIFIED")

    def get(self, name):
        if type(name) is not str or not name.startswith(ROOT + "/"):
            raise ArchiveHold("INVALID_ARCHIVE_FILE")
        item = self._request("GET", "contents/" + name, allow_404=True)
        if item is None:
            return None
        sha = item.get("sha")
        if (type(sha) is not str or SHA40.fullmatch(sha) is None
                or type(item.get("content")) is not str
                or item.get("encoding") != "base64"):
            raise ArchiveHold("INVALID_ARCHIVE_BLOB_RESPONSE")
        try:
            raw = base64.b64decode(item["content"], validate=False)
        except (ValueError, TypeError) as exc:
            raise ArchiveHold("INVALID_ARCHIVE_BLOB_BASE64") from exc
        if not 0 < len(raw) <= MAX_BYTES:
            raise ArchiveHold("INVALID_ARCHIVE_BLOB_SIZE")
        return raw, sha

    def put(self, name, raw, *, sha=None):
        if (type(name) is not str or not name.startswith(ROOT + "/")
                or ".." in name or type(raw) is not bytes
                or not 0 < len(raw) <= MAX_BYTES
                or sha is not None and (type(sha) is not str
                                        or SHA40.fullmatch(sha) is None)):
            raise ArchiveHold("INVALID_ARCHIVE_WRITE")
        body = {
            "branch": BRANCH,
            "message": "Archive isolated HKJC research metadata only (no main write)",
            "content": base64.b64encode(raw).decode("ascii"),
        }
        if sha is not None:
            body["sha"] = sha
        result = self._request("PUT", "contents/" + name, payload=body)
        commit = result.get("commit") if type(result) is dict else None
        if (type(commit) is not dict or type(commit.get("sha")) is not str
                or SHA40.fullmatch(commit["sha"]) is None):
            raise ArchiveHold("ARCHIVE_COMMIT_NOT_VERIFIED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--attempt", required=True, type=int)
    opts = parser.parse_args()
    try:
        with open(opts.input, "rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if not 0 < len(raw) <= MAX_BYTES:
            raise ArchiveHold("UNSAFE_ARCHIVE_INPUT_SIZE")
        doc = _parse_unique(raw.decode("utf-8"))
        status = archive(
            doc, run_id=opts.run_id, attempt=opts.attempt,
            store=GitHubArchiveStore(os.environ.get("GH_TOKEN", "")),
            now=datetime.now(timezone.utc),
        )
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        print("HOLD: isolated archive failed: " +
              (str(exc) if type(exc) is ArchiveHold else "UNVERIFIED_ARCHIVE"),
              file=sys.stderr)
        return 1
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
