"""Offline research-only regression for live quote JSON ingestion.

Tests local parser and CLI safety. Neither vendor provenance nor any live
betting opportunity is certified.
"""
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import live_quote_snapshot_guard as live


class LiveEvidenceReadGateTests(unittest.TestCase):
    def test_valid_small_local_json_still_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sample.json"
            expected = {"quote": {"line": 8.5, "side": "over"}}
            p.write_text(json.dumps(expected), encoding="utf-8")
            self.assertEqual(
                live._read_local_evidence(p, 512_000, "INPUT_TOO_LARGE"),
                expected)

    def test_nested_duplicate_key_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sample.json"
            p.write_text('{"quote":{"line":8.5,"line":9.5}}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "DUPLICATE_EVIDENCE_KEY"):
                live._read_local_evidence(p, 512_000, "INPUT_TOO_LARGE")

    def test_nonfinite_json_tokens_rejected(self):
        for invalid in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "sample.json"
                p.write_text('{"price":' + invalid + "}", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "NONFINITE_EVIDENCE_NUMBER"):
                    live._read_local_evidence(p, 512_000, "INPUT_TOO_LARGE")

    def test_oversize_and_empty_files_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sample.json"
            p.write_bytes(b"x" * 101)
            with self.assertRaisesRegex(ValueError, "INPUT_TOO_LARGE"):
                live._read_local_evidence(p, 100, "INPUT_TOO_LARGE")
            p.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "INPUT_TOO_LARGE"):
                live._read_local_evidence(p, 100, "INPUT_TOO_LARGE")

    def test_symlinked_snapshot_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            source = d / "source.json"
            source.write_text("{}", encoding="utf-8")
            link = d / "linked.json"
            link.symlink_to(source)
            with self.assertRaisesRegex(ValueError, "UNSAFE_EVIDENCE_PATH"):
                live._read_local_evidence(link, 512_000, "INPUT_TOO_LARGE")

    def test_symlinked_ancestor_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            real = d / "evidence"
            real.mkdir()
            (real / "source.json").write_text("{}", encoding="utf-8")
            alias = d / "alias"
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "UNSAFE_EVIDENCE_PATH"):
                live._read_local_evidence(
                    alias / "source.json", 512_000, "INPUT_TOO_LARGE")

    def test_hardlinked_input_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            source = d / "source.json"
            source.write_text("{}", encoding="utf-8")
            hardlink = d / "hardlink.json"
            hardlink.hardlink_to(source)
            with self.assertRaisesRegex(ValueError, "UNSAFE_EVIDENCE_PATH"):
                live._read_local_evidence(hardlink, 512_000, "INPUT_TOO_LARGE")

    def test_cli_duplicate_snapshot_stays_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "snapshot.json"
            p.write_text('{"event_id":"one","event_id":"two"}', encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = live.main([str(p)])
            self.assertEqual(code, 2)
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["status"], "HOLD")
            self.assertIn("DUPLICATE_EVIDENCE_KEY", result["reasons"])
            self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_cli_linked_fixture_manifest_stays_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            snapshot = d / "snapshot.json"
            snapshot.write_text("{}", encoding="utf-8")
            manifest = d / "manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            link = d / "manifest-link.json"
            link.symlink_to(manifest)
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = live.main([str(snapshot), "--fixture-manifest", str(link)])
            self.assertEqual(code, 2)
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["status"], "HOLD")
            self.assertIn("UNSAFE_EVIDENCE_PATH", result["reasons"])

    def test_cli_duplicate_manifest_stays_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            snapshot = d / "snapshot.json"
            snapshot.write_text("{}", encoding="utf-8")
            manifest = d / "manifest.json"
            manifest.write_text('{"source_events":{},"source_events":{}}',
                                encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = live.main([str(snapshot), "--fixture-manifest", str(manifest)])
            self.assertEqual(code, 2)
            self.assertIn("DUPLICATE_EVIDENCE_KEY",
                          json.loads(stdout.getvalue())["reasons"])


if __name__ == "__main__":
    unittest.main()
