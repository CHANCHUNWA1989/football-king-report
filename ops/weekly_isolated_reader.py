"""Read-only isolated weekly report verification before GitHub Issue notification.

Only checks a fixed archive branch, canonical report path and existing
HOLD-only report bytes. Does not query sports providers, modify GitHub,
enable forecasts or authorize betting.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from weekly_isolated_archive import (
    ArchiveHold,
    BRANCH,
    GithubWeeklyStore,
    REPO,
    _git_blob_sha,
    validate_report,
)


def make_verified_notification(raw: bytes, *, day: str, store, now: datetime) -> dict:
    """Require independently fetched archive bytes identical to the local report.

    Store.get must use GET ?ref=<fixed isolated branch> and verify the
    GitHub-returned file identity, Git blob SHA and base64 content. There is
    deliberately no fallback to main or automatic "repair" write.
    """
    report = validate_report(raw, day=day, now=now)
    store.verify_branch()
    archive = store.get(report["path"])
    if (not isinstance(archive, tuple) or len(archive) != 2 or
            type(archive[0]) is not bytes or
            archive[0] != raw or
            type(archive[1]) is not str or
            archive[1] != _git_blob_sha(raw)):
        raise ArchiveHold("WEEKLY_NOTIFICATION_ARCHIVE_UNVERIFIED")

    sha = hashlib.sha256(raw).hexdigest()
    if sha != report["sha256"]:
        raise ArchiveHold("WEEKLY_NOTIFICATION_SHA256_MISMATCH")
    # Add provenance as a separate, explicit section. We make no claims
    # about true independent sources, OOS performance or positive EV.
    footer = (
        "\n---\n"
        "## 週報封存核對（只供研究）\n\n"
        f"- 香港報告日期：{day}\n"
        f"- 固定封存分支：\x60{BRANCH}\x60\n"
        f"- 固定封存路徑：\x60{report['path']}\x60\n"
        f"- 讀回 Git blob SHA-1：\x60{archive[1]}\x60\n"
        f"- 報告原始 SHA-256：\x60{sha}\x60\n"
        "- 存檔比對：原始 bytes 與 Git blob SHA 相符\n"
        "- 此記錄不構成官方來源認證、外部時間見證或可交易盤口證據。\n"
        "- 正式投注：**HOLD / DISABLED**\n"
    ).encode("utf-8")
    return {
        "body": raw + footer,
        "source_ref": BRANCH,
        "source_path": report["path"],
        "report_sha256": sha,
        "archive_blob_sha": archive[1],
        "approved_for_betting": False,
        "production_recommendations": "DISABLED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--day", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    try:
        # The verified notification is materialized only after a read-only
        # GitHub archive check has succeeded, and never overwrites a prior
        # local notification file or an archive/market/provenance file.
        if (args.input.is_symlink() or not args.input.is_file() or
                args.output.is_symlink() or args.output.exists() or
                args.input.resolve() == args.output.resolve() or
                args.input.stat().st_size > 24_000):
            raise ArchiveHold("UNSAFE_WEEKLY_NOTIFICATION_PATH")
        raw = args.input.read_bytes()
        notice = make_verified_notification(
            raw, day=args.day,
            store=GithubWeeklyStore(os.getenv("GH_TOKEN", "")),
            now=datetime.now(timezone.utc))
        with args.output.open("xb") as target:
            target.write(notice["body"])
    except (ArchiveHold, OSError, ValueError, OverflowError, UnicodeError) as exc:
        reason = str(exc) if type(exc) is ArchiveHold else "WEEKLY_NOTIFICATION_UNVERIFIED"
        print("HOLD: " + reason, file=sys.stderr)
        return 2

    print(json.dumps({
        "status": "RESEARCH_ONLY_NOTIFICATION_VERIFIED",
        "archive_ref": notice["source_ref"],
        "archive_path": notice["source_path"],
        "report_sha256": notice["report_sha256"],
        "production_recommendations": "DISABLED",
        "approved_for_betting": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
