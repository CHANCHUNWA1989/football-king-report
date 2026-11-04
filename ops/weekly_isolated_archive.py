"""PR-14 weekly report archive: fixed research branch, immutable per-HK-day files.

No provider network access or extra market quota. This tool never writes main,
never promotes any model, and cannot authorize live betting or positive EV.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

REPO = "CHANCHUNWA1989/football-king-report"
BRANCH = "research/weekly-report-archive"
PREFIX = "reports/weekly/"
MAX_BYTES = 24_000
MAX_REPLY = 64_000
HKT = timezone(timedelta(hours=8))
GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
DATE_IN_REPORT = re.compile(r"(?m)^- 統計截止（UTC）：([^\n]+)$")
EXPECTED_ROWS = ("英超", "英冠", "德甲", "西甲", "意甲", "法甲")
FIXED_HEAD = "# 足球王者 V4.1｜每週研究可靠性報告\n\n> 只供研究，並非投注建議；模型未獨立證實有市場優勢。\n"
MANDATORY = (
    "- 正式投注建議：**HOLD / DISABLED**",
    "## 六大聯賽上週樣本外研究",
    "| 聯賽 | 已結算樣本 | 模型Log Loss | 市場Log Loss |",
    "## 保留意見／風險", "## 研究採納判準",
    "新模型只能進入 Shadow Mode；須有同場同時嘅A/B、足量前瞻樣本",
)
BANNED = (
    "TIPSME_API_KEY", "BSD_FREE_API_TOKEN", "GH_TOKEN", "Authorization:",
    "authKey", "bookmaker_quotes", "raw_quotes", "positive_ev_verified",
    "production_recommendations=ENABLED", "立即投注", "<script", "<iframe",
)


class ArchiveHold(ValueError):
    """Reject unverifiable archive data without silently writing main."""


def _parse_unique(raw):
    def unique(items):
        obj = {}
        for name, value in items:
            if name in obj:
                raise ArchiveHold("DUPLICATE_GITHUB_RESPONSE_KEY")
            obj[name] = value
        return obj
    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (TypeError, ValueError) as exc:
        if type(exc) is ArchiveHold:
            raise
        raise ArchiveHold("INVALID_GITHUB_RESPONSE_JSON") from exc


def _git_blob_sha(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def validate_report(raw, *, day, now):
    """Validate existing fixed weekly_digest report, not arbitrary Markdown."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise ArchiveHold("INVALID_WEEKLY_REPORT_SIZE")
    if type(day) is not str or not DAY.fullmatch(day):
        raise ArchiveHold("INVALID_WEEKLY_REPORT_DATE")
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ArchiveHold("INVALID_ARCHIVE_CLOCK")
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise ArchiveHold("INVALID_WEEKLY_REPORT_ENCODING") from exc
    if (not text.startswith(FIXED_HEAD) or
            any(text.count(marker) != 1 for marker in MANDATORY) or
            any(text.count("| " + team + " |") != 1 for team in EXPECTED_ROWS) or
            any(forbidden in text for forbidden in BANNED) or
            any(ord(x) < 32 and x not in "\n\t" for x in text)):
        raise ArchiveHold("UNSAFE_OR_UNRECOGNIZED_WEEKLY_REPORT")
    match = DATE_IN_REPORT.findall(text)
    if len(match) != 1:
        raise ArchiveHold("MISSING_WEEKLY_CAPTURE_TIME")
    try:
        captured = datetime.fromisoformat(match[0].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArchiveHold("INVALID_WEEKLY_CAPTURE_TIME") from exc
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ArchiveHold("UNZONED_WEEKLY_CAPTURE_TIME")
    captured = captured.astimezone(timezone.utc)
    clock = now.astimezone(timezone.utc)
    # A current archive must be a fresh script-generated report, not
    # a report from a different scheduled week or a future report.
    if not clock - timedelta(hours=24) <= captured <= clock + timedelta(minutes=5):
        raise ArchiveHold("STALE_OR_FUTURE_WEEKLY_REPORT")
    if captured.astimezone(HKT).date().isoformat() != day:
        raise ArchiveHold("HK_WEEKLY_DATE_MISMATCH")
    return {
        "date_hkt": day, "captured_utc": captured.isoformat().replace("+00:00", "Z"),
        "sha256": hashlib.sha256(raw).hexdigest(), "path": PREFIX + day + ".md",
    }


def archive_report(raw, *, day, store, now):
    verified = validate_report(raw, day=day, now=now)
    store.verify_branch()
    path = verified["path"]
    current = store.get(path)
    if current is not None:
        if current[0] != raw:
            raise ArchiveHold("SAME_WEEKLY_DATE_CONTENT_CONFLICT")
        state = "EXISTING_IDENTICAL_WEEKLY_REPORT"
    else:
        # GitHub Contents PUT without SHA can only create, not overwrite.
        # A concurrent create returns 409/422 => explicit HOLD.
        store.put(path, raw)
        state = "NEW_ISOLATED_WEEKLY_REPORT"
    return {
        "status": "RESEARCH_ONLY_ARCHIVED",
        "reason": state, "archive_branch": BRANCH,
        "archive_path": path, "report_sha256": verified["sha256"],
        "legacy_main_report_unchanged": True,
        "source_independence_verified": False,
        "oos_improvement_verified": False,
        "positive_ev_verified": False,
        "can_execute_bet": False,
        "production_recommendations": "DISABLED",
    }


class GithubWeeklyStore:
    """Fixed-host, fixed-ref, fixed-prefix read/create-only GitHub Contents API."""

    def __init__(self, token):
        if type(token) is not str or not token.strip():
            raise ArchiveHold("ARCHIVE_GITHUB_TOKEN_UNAVAILABLE")
        self.token = token

    def _api(self, method, path, *, data=None, missing_ok=False):
        if not (path == "git/ref/heads/" + BRANCH
                or path.startswith("contents/" + PREFIX)):
            raise ArchiveHold("UNAUTHORIZED_ARCHIVE_ENDPOINT")
        if method not in ("GET", "PUT"):
            raise ArchiveHold("ARCHIVE_HTTP_METHOD_NOT_ALLOWED")
        if method == "PUT" and (not path.startswith("contents/" + PREFIX)
                                or type(data) is not dict
                                or data.get("branch") != BRANCH
                                or "sha" in data):
            raise ArchiveHold("MAIN_OR_OVERWRITE_WRITE_FORBIDDEN")
        url = "https://api.github.com/repos/" + REPO + "/" + path
        if method == "GET" and path.startswith("contents/"):
            url += "?ref=" + quote(BRANCH, safe="")
        payload = json.dumps(data, separators=(",", ":")).encode("utf-8") if data else None
        req = Request(url, data=payload, method=method, headers={
            "Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "football-king-weekly-isolated-archive",
        })
        try:
            with urlopen(req, timeout=12) as response:
                response_bytes = response.read(MAX_REPLY + 1)
        except HTTPError as exc:
            if missing_ok and exc.code == 404:
                return None
            if method == "PUT" and exc.code in (409, 422):
                raise ArchiveHold("CONCURRENT_OR_EXISTING_WEEKLY_FILE") from exc
            raise ArchiveHold("ARCHIVE_GITHUB_API_DENIED_OR_UNAVAILABLE") from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise ArchiveHold("ARCHIVE_GITHUB_API_DENIED_OR_UNAVAILABLE") from exc
        if not response_bytes or len(response_bytes) > MAX_REPLY:
            raise ArchiveHold("UNSAFE_GITHUB_ARCHIVE_RESPONSE_SIZE")
        try:
            result = _parse_unique(response_bytes.decode("utf-8"))
        except UnicodeError as exc:
            raise ArchiveHold("UNSAFE_GITHUB_ARCHIVE_ENCODING") from exc
        if type(result) is not dict:
            raise ArchiveHold("INVALID_GITHUB_ARCHIVE_RESPONSE")
        return result

    def verify_branch(self):
        obj = self._api("GET", "git/ref/heads/" + BRANCH)
        target = obj.get("object")
        if (obj.get("ref") != "refs/heads/" + BRANCH
                or type(target) is not dict
                or target.get("type") != "commit"
                or type(target.get("sha")) is not str
                or GIT_SHA.fullmatch(target["sha"]) is None):
            raise ArchiveHold("ISOLATED_BRANCH_IDENTITY_UNVERIFIED")

    def get(self, path):
        if not re.fullmatch(r"reports/weekly/[0-9]{4}-[0-9]{2}-[0-9]{2}\.md", path):
            raise ArchiveHold("UNEXPECTED_WEEKLY_FILE_PATH")
        data = self._api("GET", "contents/" + path, missing_ok=True)
        if data is None:
            return None
        if (data.get("type") != "file" or data.get("path") != path
                or data.get("name") != path.rsplit("/", 1)[1]
                or data.get("encoding") != "base64"
                or type(data.get("sha")) is not str
                or GIT_SHA.fullmatch(data["sha"]) is None
                or type(data.get("size")) is not int
                or type(data.get("content")) is not str):
            raise ArchiveHold("MISMATCHED_WEEKLY_BLOB_IDENTITY")
        try:
            raw = base64.b64decode("".join(data["content"].split()), validate=True)
        except (ValueError, TypeError) as exc:
            raise ArchiveHold("INVALID_WEEKLY_BLOB_BASE64") from exc
        if (not 0 < len(raw) <= MAX_BYTES or len(raw) != data["size"]
                or _git_blob_sha(raw) != data["sha"]):
            raise ArchiveHold("WEEKLY_BLOB_INTEGRITY_MISMATCH")
        return raw, data["sha"]

    def put(self, path, raw):
        if not re.fullmatch(r"reports/weekly/[0-9]{4}-[0-9]{2}-[0-9]{2}\.md", path):
            raise ArchiveHold("UNEXPECTED_WEEKLY_FILE_PATH")
        payload = {
            "branch": BRANCH,
            "message": "Archive weekly HOLD-only research status on isolated branch",
            "content": base64.b64encode(raw).decode("ascii"),
        }
        out = self._api("PUT", "contents/" + path, data=payload)
        commit = out.get("commit")
        if (type(commit) is not dict
                or type(commit.get("sha")) is not str
                or GIT_SHA.fullmatch(commit["sha"]) is None):
            raise ArchiveHold("WEEKLY_ARCHIVE_COMMIT_UNVERIFIED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--day", required=True)
    args = parser.parse_args()
    try:
        raw = Path(args.input).read_bytes()
        status = archive_report(
            raw, day=args.day,
            store=GithubWeeklyStore(os.getenv("GH_TOKEN", "")),
            now=datetime.now(timezone.utc))
    except (ArchiveHold, OSError, ValueError, OverflowError) as exc:
        code = str(exc) if type(exc) is ArchiveHold else "WEEKLY_ARCHIVE_FAILURE"
        print("HOLD: " + code, file=sys.stderr)
        return 1
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
