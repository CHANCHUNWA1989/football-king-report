"""Offline structural tests for the CPython 3.11 Linux x86_64 Kloppy lock.

These do not download wheels or claim to audit their suppliers or licenses.
"""
from pathlib import Path
import re
import unittest


LOCK_PATH = (
    Path(__file__).resolve().parents[1] / "research_locks"
    / "kloppy-3.19.1-cp311-linux-x86_64.txt"
)
NAMES = frozenset({
    "aiohappyeyeballs", "aiohttp", "aiosignal", "attrs", "frozenlist",
    "fsspec", "idna", "kloppy", "lxml", "multidict", "propcache",
    "python-dateutil", "pytz", "sortedcontainers",
    "typing_extensions", "tzdata", "yarl",
})
PIN = re.compile(r"([a-z0-9][a-z0-9_-]*)==([a-zA-Z0-9][a-zA-Z0-9._+-]*) --hash=sha256:([a-f0-9]{64})")


def parse_lock(source):
    lines = [line.strip() for line in source.splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if not lines or lines.pop(0) != "--only-binary=:all:":
        raise ValueError("UNSAFE_KLOPPY_LOCK_DIRECTIVE")
    entries = {}
    for line in lines:
        match = PIN.fullmatch(line)
        if match is None:
            raise ValueError("UNPINNED_OR_UNHASHED_KLOPPY_PACKAGE")
        name, version, checksum = match.groups()
        normalized = name.replace("_", "-")
        if normalized in entries:
            raise ValueError("DUPLICATE_KLOPPY_PACKAGE")
        entries[normalized] = (version, checksum)
    return entries


class KloppyResearchWheelLockTests(unittest.TestCase):
    def test_all_seventeen_wheels_are_explicitly_pinned_and_hashed(self):
        data = parse_lock(LOCK_PATH.read_text(encoding="utf-8"))
        self.assertEqual(set(data), {name.replace("_", "-") for name in NAMES})
        self.assertEqual(len(data), 17)
        self.assertEqual(data["kloppy"], (
            "3.19.1",
            "bdb468cc7b23a6c58276fdd8dbdb9c331e8cf4be8b721fdb97b7ec69d186b5ba",
        ))

    def test_implicit_network_index_or_unhashed_dependency_is_rejected(self):
        for bad in (
            "kloppy==3.19.1",
            "kloppy>=3.19",
            "-i https://pypi.org/simple",
            "--extra-index-url https://example.com",
            "-e ./some-local-dir",
        ):
            with self.subTest(line=bad):
                with self.assertRaises(ValueError):
                    parse_lock("--only-binary=:all:\n" + bad)

    def test_duplicate_package_is_rejected(self):
        entry = "kloppy==3.19.1 --hash=sha256:" + "a" * 64
        with self.assertRaisesRegex(ValueError, "DUPLICATE_KLOPPY_PACKAGE"):
            parse_lock("--only-binary=:all:\n" + entry + "\n" + entry)

    def test_directive_is_mandatory(self):
        entry = "kloppy==3.19.1 --hash=sha256:" + "a" * 64
        with self.assertRaisesRegex(ValueError, "UNSAFE_KLOPPY_LOCK_DIRECTIVE"):
            parse_lock(entry)

    def test_platform_scope_is_explicit_in_lock(self):
        header = "\n".join(LOCK_PATH.read_text(encoding="utf-8").splitlines()[:7])
        self.assertIn("CPython 3.11 Linux x86_64", header)
        self.assertIn("NOT for Windows/macOS", header)
        self.assertIn("research-only", header)


if __name__ == "__main__":
    unittest.main()
