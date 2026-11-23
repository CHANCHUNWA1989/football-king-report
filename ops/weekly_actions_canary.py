"""Verify a synthetic archive canary via Actions GITHUB_TOKEN (GET-only).

This is not a weekly report, evidence source, odds feed, or release gate.
It never asks for a writable token and never calls a non-GitHub provider.
"""
import base64
import hashlib
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPRedirectHandler

REPO = "CHANCHUNWA1989/football-king-report"
ARCHIVE_BRANCH = "research/weekly-report-archive"
TEST_BRANCH = "research/vnext-pr14-isolated-weekly-report-20261104"
CANARY_PATH = "canary/weekly-archive/2026-11-23-hkt-synthetic-readback-01.json"
EXPECTED_BLOB_SHA = "c0535b2026c0c87120caafd27254bf9c948eb90d"
EXPECTED_SHA256 = "f42d229ef86d0463dd0f3046632a4984abf2928bbcef9dca2b6c627a6b1e3b41"
EXPECTED_PAYLOAD = {
    "schema": "football-king.weekly-archive-synthetic-canary.v1",
    "date_hkt": "2026-11-23",
    "mode": "SYNTHETIC_TEST_ONLY",
    "purpose": "Verify GitHub archive branch creation, readback, and integrity without accessing any live football or betting data.",
    "archive_branch": ARCHIVE_BRANCH,
    "expected_path": CANARY_PATH,
    "not_a_weekly_report": True,
    "historical_prediction": False,
    "fixture_records": [],
    "provider_data": [],
    "production_recommendations": "DISABLED",
    "release_status": "HOLD",
    "auto_betting_enabled": False,
    "requires_independent_review": True,
}
ROOT = "https://api.github.com/repos/" + REPO + "/"
REF_URL = ROOT + "git/ref/heads/" + ARCHIVE_BRANCH
FILE_URL = ROOT + "contents/" + CANARY_PATH + "?ref=" + quote(ARCHIVE_BRANCH, safe="")
MAIN_URL = ROOT + "contents/" + CANARY_PATH + "?ref=main"
ALLOWED = frozenset((REF_URL, FILE_URL, MAIN_URL))
SHA = re.compile(r"[0-9a-f]{40}\Z")
MAX_RESPONSE = 16_384


class ArchiveCanaryHold(ValueError):
    """Reject unverifiable GitHub archive evidence without any write."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, *args, **kwargs):
        return None


def _parse(data):
    def unique(pairs):
        output = {}
        for key, value in pairs:
            if key in output:
                raise ArchiveCanaryHold("DUPLICATE_CANARY_JSON_KEY")
            output[key] = value
        return output

    try:
        return json.loads(data, object_pairs_hook=unique)
    except (UnicodeError, ValueError) as error:
        if isinstance(error, ArchiveCanaryHold):
            raise
        raise ArchiveCanaryHold("INVALID_CANARY_GITHUB_JSON") from error


def _get(url, token, opener, *, allow_404=False):
    if url not in ALLOWED:
        raise ArchiveCanaryHold("UNEXPECTED_CANARY_API_URL")
    req = Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "football-king-readonly-weekly-canary",
    }, method="GET")
    try:
        with opener.open(req, timeout=12) as response:
            raw = response.read(MAX_RESPONSE + 1)
    except HTTPError as error:
        if allow_404 and error.code == 404:
            return None
        raise ArchiveCanaryHold("CANARY_GITHUB_GET_FAILED") from error
    except (OSError, URLError, TimeoutError) as error:
        raise ArchiveCanaryHold("CANARY_GITHUB_GET_FAILED") from error
    if not raw or len(raw) > MAX_RESPONSE:
        raise ArchiveCanaryHold("CANARY_GITHUB_RESPONSE_SIZE")
    decoded = _parse(raw)
    if not isinstance(decoded, dict):
        raise ArchiveCanaryHold("CANARY_GITHUB_RESPONSE_NOT_OBJECT")
    return decoded


def probe(*, token, opener=None):
    """Read branch, exact isolated file, and confirm file absent on main."""
    if not isinstance(token, str) or not token.strip():
        raise ArchiveCanaryHold("READ_ONLY_GITHUB_TOKEN_MISSING")
    opener = opener if opener is not None else build_opener(NoRedirect())

    ref = _get(REF_URL, token, opener)
    obj = ref.get("object")
    if (ref.get("ref") != "refs/heads/" + ARCHIVE_BRANCH
            or not isinstance(obj, dict)
            or obj.get("type") != "commit"
            or not isinstance(obj.get("sha"), str)
            or not SHA.fullmatch(obj["sha"])):
        raise ArchiveCanaryHold("CANARY_ARCHIVE_BRANCH_IDENTITY_INVALID")

    f = _get(FILE_URL, token, opener)
    if (f.get("type") != "file"
            or f.get("path") != CANARY_PATH
            or f.get("name") != CANARY_PATH.rsplit("/", 1)[1]
            or f.get("encoding") != "base64"
            or type(f.get("size")) is not int
            or type(f.get("content")) is not str
            or type(f.get("sha")) is not str
            or f["sha"] != EXPECTED_BLOB_SHA):
        raise ArchiveCanaryHold("CANARY_ARCHIVE_FILE_IDENTITY_INVALID")
    try:
        raw = base64.b64decode("".join(f["content"].split()), validate=True)
    except (ValueError, TypeError) as error:
        raise ArchiveCanaryHold("CANARY_ARCHIVE_BASE64_INVALID") from error

    computed_git = hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()
    computed_sha256 = hashlib.sha256(raw).hexdigest()
    if (f["size"] != len(raw)
            or computed_git != f["sha"]
            or computed_sha256 != EXPECTED_SHA256):
        raise ArchiveCanaryHold("CANARY_ARCHIVE_HASH_OR_SIZE_MISMATCH")

    expected_raw = (json.dumps(EXPECTED_PAYLOAD, indent=2,
                               ensure_ascii=False) + "\n").encode("utf-8")
    if raw != expected_raw:
        raise ArchiveCanaryHold("CANARY_ARCHIVE_BYTES_CHANGED")

    on_main = _get(MAIN_URL, token, opener, allow_404=True)
    if on_main is not None:
        raise ArchiveCanaryHold("CANARY_PATH_MUST_NOT_EXIST_ON_MAIN")
    return {
        "status": "READ_ONLY_CANARY_VERIFIED",
        "archive_branch": ARCHIVE_BRANCH,
        "archive_path": CANARY_PATH,
        "git_blob_sha": computed_git,
        "sha256": computed_sha256,
        "write_token_verified": False,
        "issue_notification_verified": False,
        "branch_protection_verified": False,
        "source_independence_verified": False,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }


def main():
    if (os.environ.get("GITHUB_REPOSITORY") != REPO
            or os.environ.get("GITHUB_REF") != "refs/heads/" + TEST_BRANCH
            or os.environ.get("GITHUB_EVENT_NAME") != "push"):
        print("HOLD: CANARY_NOT_RUNNING_ON_PINNED_PUSH", file=sys.stderr)
        return 2
    try:
        receipt = probe(token=os.environ.get("GH_TOKEN", ""))
    except (ArchiveCanaryHold, OSError, ValueError) as error:
        code = str(error) if isinstance(error, ArchiveCanaryHold) else "CANARY_READ_FAILED"
        print("HOLD: " + code, file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
