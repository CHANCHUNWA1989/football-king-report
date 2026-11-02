"""No-network, no-provider-credit tests for private raw quote receipts."""
import copy
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_quote_snapshot_receipt import (
    ReceiptError, create_receipt, verify_receipt, main)


CAPTURE = "2026-11-02T05:00:00Z"


def raw_response():
    # Synthetic fixture only; prices are not copied to the receipt.
    payload = [{
        "id": "synthetic-fixture-1", "sport_key": "soccer_epl",
        "home_team": "Private Home", "away_team": "Private Away",
        "commence_time": "2026-11-02T08:00:00Z",
        "bookmakers": [{
            "key": "private-book-XYZ",
            "markets": [
                {"key": "h2h", "last_update": "2026-11-02T04:59:30Z",
                 "outcomes": [
                     {"name": "Private Home", "price": 2.12345},
                     {"name": "Draw", "price": 3.45678},
                     {"name": "Private Away", "price": 4.56789}]},
                {"key": "spreads", "last_update": "2026-11-02T04:59:30Z",
                 "outcomes": [
                     {"name": "Private Home", "point": -0.25, "price": 1.95},
                     {"name": "Private Away", "point": 0.25, "price": 1.91}]},
                {"key": "totals", "last_update": "2026-11-02T04:59:30Z",
                 "outcomes": [
                     {"name": "Over", "point": 2.75, "price": 1.92},
                     {"name": "Under", "point": 2.75, "price": 1.96}]},
            ]}]}]
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode()


class PrivateQuoteSnapshotReceiptTests(unittest.TestCase):
    def test_three_complete_markets_digest_and_safe_receipt(self):
        raw = raw_response()
        receipt = create_receipt(raw, CAPTURE)
        self.assertEqual(receipt["raw_response_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(receipt["raw_response_bytes"], len(raw))
        self.assertEqual(receipt["complete_prematch_bookmaker_lines_by_market"],
                         {"h2h": 1, "spreads": 1, "totals": 1})
        self.assertEqual(receipt["status"], "RESEARCH_ONLY")
        self.assertEqual(receipt["production_recommendations"], "DISABLED")
        self.assertFalse(receipt["publisher_independently_authenticated"])
        self.assertFalse(receipt["capture_clock_independently_authenticated"])
        self.assertFalse(receipt["digest_anchored_in_immutable_store"])
        self.assertFalse(receipt["executable_quote_verified"])
        serialized = json.dumps(receipt, ensure_ascii=False)
        for private in ("Private Home", "Private Away", "private-book-XYZ",
                        "2.12345", "3.45678", "4.56789",
                        '"outcomes"', '"bookmakers"', '"decimal_odds"'):
            self.assertNotIn(private, serialized)

    def test_bytes_roundtrip_only_not_external_provenance(self):
        raw = raw_response()
        result = verify_receipt(raw, create_receipt(raw, CAPTURE))
        self.assertTrue(result["bytes_and_semantics_replayed"])
        self.assertFalse(result["publisher_independently_authenticated"])
        self.assertFalse(result["capture_clock_independently_authenticated"])
        self.assertFalse(result["digest_anchored_in_immutable_store"])
        self.assertFalse(result["eligible_for_model_promotion"])
        self.assertEqual(result["status"], "HOLD")

    def test_even_a_supplied_expected_digest_is_not_independent_attestation(self):
        raw = raw_response()
        receipt = create_receipt(raw, CAPTURE, expected_sha256=hashlib.sha256(raw).hexdigest())
        self.assertTrue(receipt["caller_supplied_expected_digest_matched"])
        self.assertFalse(receipt["publisher_independently_authenticated"])
        self.assertFalse(receipt["digest_anchored_in_immutable_store"])
        self.assertTrue(verify_receipt(raw, receipt)["bytes_and_semantics_replayed"])

    def test_one_byte_changed_cannot_replay(self):
        raw = raw_response()
        receipt = create_receipt(raw, CAPTURE)
        for changed in (raw + b" ", raw.replace(b"2.12345", b"2.12346"),
                        raw.replace(b"synthetic-fixture-1", b"synthetic-fixture-2")):
            with self.subTest(changed=changed[-20:]):
                with self.assertRaisesRegex(ReceiptError, "RAW_SHA256_MISMATCH"):
                    verify_receipt(changed, receipt)

    def test_wrong_expected_digest_and_wrong_digest_format_rejected(self):
        raw = raw_response()
        for bad in ("0"*64, "AAAA", None, 0, True):
            with self.subTest(value=bad):
                if bad is None:
                    continue  # None explicitly selects unanchored mode.
                with self.assertRaises(ReceiptError):
                    create_receipt(raw, CAPTURE, expected_sha256=bad)

    def test_forged_counts_flags_and_extra_receipt_fields_do_not_replay(self):
        raw = raw_response()
        original = create_receipt(raw, CAPTURE)
        for key, value in (
            ("events_matched", 88),
            ("complete_prematch_bookmaker_lines_by_market",
             {"h2h": 1, "spreads": 9, "totals": 9}),
            ("production_recommendations", "ENABLED"),
            ("publisher_independently_authenticated", True),
            ("digest_anchored_in_immutable_store", True),
            ("capture_clock_independently_authenticated", True),
            ("raw_response_bytes_exported", True),
            ("missing_markets", []),
        ):
            with self.subTest(field=key):
                receipt = copy.deepcopy(original)
                receipt[key] = value
                with self.assertRaisesRegex(ReceiptError, "RECEIPT_REPLAY_MISMATCH"):
                    verify_receipt(raw, receipt)
        extra = dict(original, fabricated_signature=True)
        with self.assertRaises(ReceiptError):
            verify_receipt(raw, extra)

    def test_capture_time_not_forged_by_bool_naive_or_offset_clock(self):
        raw = raw_response()
        for bad in (None, True, "", "2026-11-02T05:00:00", "2026-11-02T13:00:00+08:00",
                    "invalid", [], {}):
            with self.subTest(capture=repr(bad)):
                with self.assertRaises(ReceiptError):
                    create_receipt(raw, bad)

    def test_capture_time_mutation_requires_full_replay(self):
        raw = raw_response()
        receipt = create_receipt(raw, CAPTURE)
        receipt["captured_utc_claimed_by_caller"] = "2026-11-02T05:00:01+00:00"
        with self.assertRaises(ReceiptError):
            verify_receipt(raw, receipt)

    def test_missing_or_wrong_market_pair_is_not_invented(self):
        source = json.loads(raw_response())
        bad = copy.deepcopy(source)
        bad[0]["bookmakers"][0]["markets"][2]["outcomes"].pop()
        report = create_receipt(json.dumps(bad).encode(), CAPTURE)
        self.assertEqual(report["complete_prematch_bookmaker_lines_by_market"]["totals"], 0)
        self.assertIn("totals", report["missing_markets"])
        self.assertFalse(report["executable_quote_verified"])
        bad = copy.deepcopy(source)
        bad[0]["bookmakers"][0]["markets"][1]["outcomes"][1]["point"] = -0.25
        report = create_receipt(json.dumps(bad).encode(), CAPTURE)
        self.assertEqual(report["complete_prematch_bookmaker_lines_by_market"]["spreads"], 0)
        self.assertIn("spreads", report["missing_markets"])

    def test_stale_quote_and_inplay_quote_never_count(self):
        source = json.loads(raw_response())
        for mutation in ("stale", "inplay"):
            with self.subTest(mutation=mutation):
                bad = copy.deepcopy(source)
                if mutation == "stale":
                    bad[0]["bookmakers"][0]["markets"][1]["last_update"] = "2026-11-02T04:50:00Z"
                    missing = "spreads"
                else:
                    bad[0]["commence_time"] = "2026-11-02T04:00:00Z"
                    missing = "totals"
                report = create_receipt(json.dumps(bad).encode(), CAPTURE)
                self.assertIn(missing, report["missing_markets"])
                self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_duplicate_key_and_nonfinite_price_rejected_before_audit(self):
        for raw in (b'[{"id":"x","id":"y"}]',
                    b'[{"price":NaN}]', b'[{"price":Infinity}]',
                    b'[] trailing', b'\xff', b'{"not":"an array"}'):
            with self.subTest(raw=raw):
                with self.assertRaises(ReceiptError):
                    create_receipt(raw, CAPTURE)

    def test_size_and_type_bounded(self):
        for bad in ("text", b"", b"x" * 2_000_001, bytearray(b"[]")):
            with self.subTest(kind=type(bad).__name__):
                with self.assertRaises(ReceiptError):
                    create_receipt(bad, CAPTURE)

    def test_empty_response_is_hold_not_a_fake_market(self):
        result = create_receipt(b"[]", CAPTURE)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["missing_markets"], ["h2h", "spreads", "totals"])
        self.assertEqual(result["events_matched"], 0)

    def test_cli_private_owner_only_receipt_and_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "raw-private.json"
            receipt = root / "private-receipt.json"
            verification = root / "replay.json"
            source.write_bytes(raw_response())
            with redirect_stdout(io.StringIO()) as stream:
                rc = main(["--input", str(source), "--captured-utc", CAPTURE,
                           "--output", str(receipt)])
            self.assertEqual(rc, 0)
            self.assertNotIn("private-book-XYZ", stream.getvalue())
            self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)
            self.assertTrue(verify_receipt(raw_response(), json.loads(receipt.read_text()))[
                "bytes_and_semantics_replayed"])
            with redirect_stdout(io.StringIO()):
                rc = main(["--input", str(source), "--verify-receipt", str(receipt),
                           "--output", str(verification)])
            self.assertEqual(rc, 0)
            self.assertEqual(stat.S_IMODE(verification.stat().st_mode), 0o600)
            self.assertEqual(json.loads(verification.read_text())["status"], "HOLD")

    def test_cli_wont_overwrite_source_or_existing_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            rawfile = Path(folder) / "raw.json"
            rawfile.write_bytes(raw_response())
            before = rawfile.read_bytes()
            with redirect_stdout(io.StringIO()):
                rc = main(["--input", str(rawfile), "--captured-utc", CAPTURE,
                           "--output", str(rawfile)])
            self.assertEqual(rc, 1)
            self.assertEqual(rawfile.read_bytes(), before)
            receipt = Path(folder) / "receipt.json"
            receipt.write_text("protected")
            with redirect_stdout(io.StringIO()):
                rc = main(["--input", str(rawfile), "--captured-utc", CAPTURE,
                           "--output", str(receipt)])
            self.assertEqual(rc, 1)
            self.assertEqual(receipt.read_text(), "protected")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "POSIX nofollow protection")
    def test_cli_rejects_symlink_raw_and_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "private-raw.json"
            source.write_bytes(raw_response())
            symlink = root / "symlink.json"
            symlink.symlink_to(source)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--input", str(symlink), "--captured-utc", CAPTURE,
                                       "--output", str(root / "out.json")]), 1)
            self.assertFalse((root / "out.json").exists())
            target = root / "target.json"
            target.write_text("protected")
            destination = root / "link.json"
            destination.symlink_to(target)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--input", str(source), "--captured-utc", CAPTURE,
                                       "--output", str(destination)]), 1)
            self.assertEqual(target.read_text(), "protected")


if __name__ == "__main__":
    unittest.main()
