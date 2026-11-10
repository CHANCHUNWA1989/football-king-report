"""Read-only path preflight for the dedicated optional BSD archive checkout.

This does not authenticate the provider, source clocks, historical retention,
or branch authorship. The existing BSD overlay separately validates vendor
contents and safely produces HOLD for unavailable or stale optional inputs.
"""
import argparse
import json
import re
import stat
from pathlib import Path

MAX_RESEARCH_BYTES = 1024 * 1024
FILES = ("bsd_status_latest.json", "bsd_market_latest.json")


def inspect_archive(root: Path) -> dict:
    root = Path(root)
    source = root / "sources"
    # The checkout root must exist and be a regular directory. Its
    # sources/ directory is OPTIONAL on a newly created, empty data branch.
    # A missing optional directory is not a reason to fail the main website.
    # Symlinks, files replacing directories, and broken links still fail.
    if not stat.S_ISDIR(root.lstat().st_mode):
        raise ValueError("BSD_ARCHIVE_DIRECTORY_UNSAFE")
    try:
        source_info = source.lstat()
    except FileNotFoundError:
        source_present = False
    else:
        if not stat.S_ISDIR(source_info.st_mode):
            raise ValueError("BSD_ARCHIVE_DIRECTORY_UNSAFE")
        source_present = True
    report = {}
    for name in FILES:
        if not source_present:
            report[name] = "MISSING_OPTIONAL"
            continue
        path = source / name
        try:
            info = path.lstat()
        except FileNotFoundError:
            # BSD is optional. Its existing overlay must display HOLD rather
            # than falling back to stale copies from main.
            report[name] = "MISSING_OPTIONAL"
            continue
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("BSD_ARCHIVE_NONREGULAR_SOURCE")
        if info.st_size > MAX_RESEARCH_BYTES:
            raise ValueError("BSD_ARCHIVE_SOURCE_OVERSIZE")
        report[name] = "PRESENT_UNTRUSTED_UNTIL_VENDOR_VALIDATED"
    return {
        "schema": "football-king-bsd-archive-read-preflight-v1",
        "files": report,
        "source_authenticity_independently_verified": False,
        "archive_immutable": False,
        "production_recommendations": "DISABLED",
    }


def inspect_history_target(root: Path, relative: str) -> None:
    """Reject any archive history path that can traverse or follow symlinks."""
    if not re.fullmatch(
        r"sources/bsd_history/[0-9]{4}/[0-9]{2}/[0-9]{2}/[0-9]+-[0-9]+[.]json[.]gz",
        relative,
    ):
        raise ValueError("BSD_ARCHIVE_HISTORY_TARGET_INVALID")
    root = Path(root)
    if not stat.S_ISDIR(root.lstat().st_mode):
        raise ValueError("BSD_ARCHIVE_DIRECTORY_UNSAFE")
    components = Path(relative).parts
    node = root
    for component in components[:-1]:
        node = node / component
        try:
            item = node.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(item.st_mode):
            raise ValueError("BSD_ARCHIVE_HISTORY_PATH_UNSAFE")
    target = root / relative
    try:
        existing = target.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(existing.st_mode):
        raise ValueError("BSD_ARCHIVE_HISTORY_TARGET_NONREGULAR")
    if existing.st_size > MAX_RESEARCH_BYTES:
        raise ValueError("BSD_ARCHIVE_HISTORY_OVERSIZE")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--history-target", default=None)
    args = parser.parse_args(argv)
    try:
        report = inspect_archive(args.root)
        if args.history_target is not None:
            inspect_history_target(args.root, args.history_target)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc),
                          "production_recommendations": "DISABLED"}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
