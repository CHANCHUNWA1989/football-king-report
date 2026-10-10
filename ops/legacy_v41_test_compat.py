"""Update exactly one obsolete V4.1 test expectation after ZIP hash verification.

The archived source remains immutable. The old test expected an optimistic
download banner even when the generated report timestamp was stale. The new
assertion requires fail-closed HOLD instead. No application code is changed.
"""
import argparse
from pathlib import Path

ORIGINAL = "self.assertIn('資料下載成功但近期賽事不足', content)"
SAFER = "self.assertIn('HOLD：報告產生時間過期或不可信', content)"


def adapt(app):
    target = Path(app) / "tests" / "test_verified.py"
    original = target.read_text(encoding="utf-8")
    if original.count(ORIGINAL) != 1 or SAFER in original:
        raise ValueError("UNEXPECTED_LEGACY_TEST_VERSION")
    target.write_text(original.replace(ORIGINAL, SAFER), encoding="utf-8")
    return str(target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", default="app")
    args = parser.parse_args()
    print("Legacy test compatibility: stale report must be HOLD.", adapt(args.app))
