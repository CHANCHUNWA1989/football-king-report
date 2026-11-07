"""Fail closed for pre-match evidence output files (synthetic offline cases)."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from ops.research_watchlist_review import main as review_main
from ops.watchlist_witness import main as witness_main


def iso(dt):
    return dt.isoformat()


def synthetic_manifest():
    now = datetime.now(timezone.utc)
    return [{
        "selection_id": "synthetic-one", "fixture_id": "fixture-synthetic-one",
        "competition": "synthetic", "model_version": "research",
        "market": "asian_handicap", "selection": "away", "line": "1.25",
        "decimal_odds": "2.10", "bookmaker": "synthetic",
        "quote_updated_at_utc": iso(now - timedelta(minutes=3)),
        "captured_at_utc": iso(now - timedelta(minutes=2)),
        "registered_at_utc": iso(now - timedelta(minutes=1)),
        "kickoff_at_utc": iso(now + timedelta(hours=2)),
        "decision": "PRIORITY_RESEARCH",
    }]


class OutputIntegrityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.watchlist = self.root / "watchlist.json"
        self.watchlist.write_text(json.dumps(synthetic_manifest()), encoding="utf-8")
        self.pin = self.root / "local-pin.json"
        self.results = self.root / "results.json"
        self.results.write_text("[]", encoding="utf-8")

    def review_args(self, output):
        return ["--watchlist", str(self.watchlist), "--results", str(self.results),
                "--checked-at-utc", iso(datetime.now(timezone.utc)),
                "--output", str(output)]

    def seal_args(self, output):
        return ["--seal-only", "--watchlist", str(self.watchlist),
                "--output", str(output)]

    def witness_args(self, output):
        return ["--watchlist", str(self.watchlist), "--pin", str(self.pin),
                "--proof-dir", str(self.root / "signed-proof"),
                "--source-sha", "a"*40, "--workflow-sha", "b"*40,
                "--run-id", "123456789", "--attempt", "1", "--output", str(output)]

    def test_seal_creates_private_new_file(self):
        output = self.root / "new-pin.json"
        self.assertFalse(output.exists())
        self.assertEqual(review_main(self.seal_args(output)), 0)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["selection_count"], 1)
        self.assertFalse(payload["external_attestation_verified"])
        self.assertEqual(payload["production_recommendations"], "DISABLED")
        if os.name == "posix":
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_seal_never_overwrites_previous_pin_or_source(self):
        old = self.root / "sealed-previous.json"
        old.write_text('{"original":"do-not-modify"}', encoding="utf-8")
        before = old.read_bytes()
        for target in (old, self.watchlist):
            with self.subTest(path=str(target)), self.assertRaises(OSError):
                review_main(self.seal_args(target))
        self.assertEqual(old.read_bytes(), before)
        self.assertIn(b"synthetic-one", self.watchlist.read_bytes())

    def test_seal_rejects_symlink_and_hardlink_outputs(self):
        protected = self.root / "protected.txt"
        protected.write_text("immutable-input", encoding="utf-8")
        symlink = self.root / "pin-symlink.json"
        symlink.symlink_to(protected)
        hardlink = self.root / "pin-hardlink.json"
        os.link(protected, hardlink)
        for target in (symlink, hardlink):
            with self.subTest(path=str(target)), self.assertRaises(OSError):
                review_main(self.seal_args(target))
        self.assertEqual(protected.read_text(), "immutable-input")

    def test_review_can_create_new_output_without_overwriting_inputs(self):
        out = self.root / "review-new.json"
        self.assertEqual(review_main(self.review_args(out)), 0)
        payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(payload["predeclared_count"], 1)
        self.assertFalse(payload["prematch_manifest_independently_attested"])
        self.assertEqual(payload["production_recommendations"], "DISABLED")
        if os.name == "posix":
            self.assertEqual(out.stat().st_mode & 0o777, 0o600)

    def test_review_rejects_existing_results_and_symlink_output(self):
        prior = self.results.read_bytes()
        for target in (self.results, self.watchlist):
            with self.subTest(path=str(target)), self.assertRaises(OSError):
                review_main(self.review_args(target))
        target = self.root / "summary-link.json"
        target.symlink_to(self.results)
        with self.assertRaises(OSError):
            review_main(self.review_args(target))
        self.assertEqual(self.results.read_bytes(), prior)

    def test_witness_never_overwrites_pin_or_input_even_when_verification_fails(self):
        self.pin.write_text('{"prior":"preserve"}', encoding="utf-8")
        prior = self.pin.read_bytes()
        proof = self.root / "signed-proof"
        proof.mkdir()
        with patch("ops.watchlist_witness.audit", return_value={
                "status": "HOLD", "production_recommendations": "DISABLED",
                "signature_subject_and_tlog_verified": False}) as check:
            for target in (self.pin, self.watchlist):
                with self.subTest(path=str(target)), self.assertRaises((OSError, SystemExit)):
                    witness_main(self.witness_args(target))
            self.assertEqual(self.pin.read_bytes(), prior)
            self.assertIn(b"synthetic-one", self.watchlist.read_bytes())
            output = self.root / "witness-new.json"
            self.assertEqual(witness_main(self.witness_args(output)), 1)
            self.assertEqual(json.loads(output.read_text())["status"], "HOLD")
            self.assertEqual(check.call_count, 1)
            if os.name == "posix":
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_witness_rejects_existing_report_and_symlink_alias(self):
        self.pin.write_text('{"prior":"preserve"}', encoding="utf-8")
        proof = self.root / "signed-proof"
        proof.mkdir()
        prior = self.root / "previous-review.json"
        prior.write_text('{"must":"stay"}', encoding="utf-8")
        link = self.root / "witness-link.json"
        link.symlink_to(prior)
        with patch("ops.watchlist_witness.audit", return_value={
                "status": "HOLD", "signature_subject_and_tlog_verified": False}):
            for target in (prior, link):
                with self.subTest(path=str(target)), self.assertRaises((OSError, SystemExit)):
                    witness_main(self.witness_args(target))
        self.assertEqual(prior.read_text(), '{"must":"stay"}')


if __name__ == "__main__":
    unittest.main()
