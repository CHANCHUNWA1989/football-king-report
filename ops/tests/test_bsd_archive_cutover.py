"""Offline producer/consumer tests for the optional BSD archive cutover."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bsd_archive_reader import FILES, inspect_archive, main
from bsd_free import collect
from bsd_overlay import publish

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 3, 0, tzinfo=timezone.utc)


class BSDArchiveCutoverTests(unittest.TestCase):
    def make_checkout(self, tmp):
        root = Path(tmp) / "bsd-research-archive"
        (root / "sources").mkdir(parents=True)
        return root

    def test_present_research_files_are_untrusted_and_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_checkout(tmp)
            blob = b'{"status":"NOT_CONFIGURED"}\n'
            file_path = root / "sources" / FILES[0]
            file_path.write_bytes(blob)
            result = inspect_archive(root)
            self.assertEqual(result["files"][FILES[0]],
                             "PRESENT_UNTRUSTED_UNTIL_VENDOR_VALIDATED")
            self.assertEqual(result["files"][FILES[1]], "MISSING_OPTIONAL")
            self.assertFalse(result["archive_immutable"])
            self.assertFalse(result["source_authenticity_independently_verified"])
            self.assertEqual(result["production_recommendations"], "DISABLED")
            self.assertEqual(file_path.read_bytes(), blob)

    def test_symlinked_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_checkout(tmp)
            target = Path(tmp) / "outside.txt"
            target.write_text("do not read me", encoding="utf-8")
            (root / "sources" / FILES[0]).symlink_to(target)
            with self.assertRaisesRegex(ValueError, "NONREGULAR"):
                inspect_archive(root)
            self.assertEqual(target.read_text(encoding="utf-8"), "do not read me")

    def test_oversize_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_checkout(tmp)
            (root / "sources" / FILES[0]).write_bytes(b"x" * (1024 * 1024 + 1))
            with self.assertRaisesRegex(ValueError, "OVERSIZE"):
                inspect_archive(root)

    def test_symlinked_checkout_source_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bsd-research-archive"
            root.mkdir()
            outside = Path(tmp) / "other"
            outside.mkdir()
            (root / "sources").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "DIRECTORY_UNSAFE"):
                inspect_archive(root)

    def test_missing_checkout_cli_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(["--root", str(Path(tmp) / "missing")])
            self.assertEqual(rc, 2)
            obj = json.loads(out.getvalue())
            self.assertEqual(obj["status"], "HOLD")
            self.assertEqual(obj["production_recommendations"], "DISABLED")

    def test_optional_missing_market_research_stays_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_checkout(tmp)
            site = Path(tmp) / "site"
            site.mkdir()
            (site / "shadow.json").write_text(
                json.dumps({"status": "SHADOW_ONLY", "predictions": [],
                            "production_recommendations": "DISABLED"}),
                encoding="utf-8",
            )
            (root / "sources" / FILES[0]).write_text(
                json.dumps(collect(now=NOW, token="")), encoding="utf-8")
            self.assertEqual(inspect_archive(root)["files"][FILES[1]],
                             "MISSING_OPTIONAL")
            result = publish(
                site, str(root / "sources" / FILES[1]),
                str(root / "sources" / FILES[0]))
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["source_state"], "NOT_CONFIGURED")
            self.assertEqual(result["time_valid_shadow_pairs"], 0)
            self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_workflow_writes_only_to_pinned_archive_branch(self):
        text = (ROOT / ".github/workflows/football-king-bsd-free.yml").read_text(
            encoding="utf-8")
        segment = text.split("\n  archive:\n", 1)[1].split(
            "\n  report_failure:\n", 1)[0]
        self.assertIn("BSD_ARCHIVE_REF: archive/bsd-free-research-v1", segment)
        self.assertIn("git/ref/heads/$BSD_ARCHIVE_REF", segment)
        self.assertEqual(segment.count("contents/$target?ref=$BSD_ARCHIVE_REF"), 2)
        self.assertEqual(segment.count('-f branch="$BSD_ARCHIVE_REF"'), 2)
        self.assertNotIn('contents/$target" --jq', segment)
        self.assertIn("BSD_ARCHIVE_REF_UNAVAILABLE", segment)

    def test_iphone_workflow_reads_separate_branch_and_never_main_bsd(self):
        text = (ROOT / ".github/workflows/football-king-iphone.yml").read_text(
            encoding="utf-8")
        self.assertIn("ref: archive/bsd-free-research-v1", text)
        self.assertIn("path: bsd-research-archive", text)
        self.assertIn("sparse-checkout-cone-mode: false", text)
        self.assertIn("python ops/bsd_archive_reader.py --root bsd-research-archive", text)
        self.assertIn(
            "--input bsd-research-archive/sources/bsd_market_latest.json "
            "--status bsd-research-archive/sources/bsd_status_latest.json", text)
        self.assertNotIn("--input sources/bsd_market_latest.json --status", text)
        self.assertIn("production_recommendations", (ROOT / "ops/bsd_overlay.py").read_text(
            encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
