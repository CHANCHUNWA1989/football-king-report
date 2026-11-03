"""Read-only path preflight for the dedicated optional BSD archive checkout.

This does not authenticate the provider, source clocks, historical retention,
or branch authorship. The existing BSD overlay separately validates vendor
contents and safely produces HOLD for unavailable or stale optional inputs.
"""
import argparse
import json
import stat
from pathlib import Path

MAX_RESEARCH_BYTES = 1024 * 1024
FILES = ("bsd_status_latest.json", "bsd_market_latest.json")


def inspect_archive(root: Path) -> dict:
    root = Path(root)
    source = root / "sources"
    for directory in (root, source):
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise ValueError("BSD_ARCHIVE_DIRECTORY_UNSAFE")
    report = {}
    for name in FILES:
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = inspect_archive(args.root)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc),
                          "production_recommendations": "DISABLED"}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
