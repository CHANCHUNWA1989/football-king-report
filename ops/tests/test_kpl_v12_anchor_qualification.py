"""Only synthetic KPL V12 records: no network, trusted witness, real matches or wagering."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research.kpl_v11_forecast_archive import archive_forecast, _digest
from research.kpl_v12_anchor_qualification import (
    build_anchor_request, inspect_anchor_receipt, screen_holdout_qualification)


BASE = datetime(2026, 10, 1, tzinfo=timezone.utc)


def ts(x):
    return x.isoformat().replace("+00:00", "Z")


def synthetic_forecast(series=0, game=1):
    start = BASE + timedelta(days=3 * series, hours=game * 4)
    predicted = start - timedelta(minutes=20)
    cutoff = predicted - timedelta(minutes=1)
    return {
        "prediction_id": f"sim-{series}-{game}", "series_id": f"simseries-{series}",
        "game_number": game, "team_ids": ["a", "b"], "predicted_team_id": "a",
        "probability": 0.55, "model_version": "sim-v1", "phase": "PRE_GAME",
        "info_cutoff_at": ts(cutoff), "forecast_at": ts(predicted),
        "game_start_at": ts(start), "status": "RESEARCH_ONLY",
        "evidence": [{"source_id": f"simulation-{series}-{game}",
                      "kind": "team_form", "subject_game": 0,
                      "published_at": ts(cutoff - timedelta(minutes=2)),
                      "captured_at": ts(cutoff - timedelta(minutes=1))}]}


def synthetic_result(forecast):
    start = datetime.fromisoformat(forecast["game_start_at"].replace("Z", "+00:00"))
    end = start + timedelta(minutes=23)
    return {"prediction_id": forecast["prediction_id"], "series_id": forecast["series_id"],
            "game_number": forecast["game_number"], "winner_team_id": "a",
            "game_end_at": ts(end), "observed_at": ts(end + timedelta(minutes=3)),
            "source_id": "sim-settlement", "verified": True}


def make_archive(directory, n_series=4, games=2):
    path = Path(directory) / "sim.jsonl"
    rows = []
    receipts = []
    for series in range(n_series):
        for game in range(1, games + 1):
            row = synthetic_forecast(series, game)
            archive_forecast(path, row)
            rows.append(row)
            index = len(rows)
            # Simulated witness receipt only, NOT a trusted timestamp.
            req = build_anchor_request(
                path, index,
                requested_at=ts(datetime.fromisoformat(row["forecast_at"].replace("Z", "+00:00"))
                                + timedelta(minutes=1)))
            receipts.append({"record_index": req["record_index"],
                             "head_hash": req["head_hash"],
                             "prediction_id": req["prediction_id"],
                             "issuer_id": "simulated-witness",
                             "anchor_target": req["anchor_target"],
                             "received_at": req["requested_at"]})
    return path, rows, [synthetic_result(x) for x in rows], receipts


class V12AnchorTests(unittest.TestCase):
    def test_request_for_earliest_record(self):
        with tempfile.TemporaryDirectory() as d:
            path, rows, _, receipts = make_archive(d)
            requested = receipts[0]["received_at"]
            r = build_anchor_request(path, 1, requested_at=requested)
            self.assertEqual(r["record_index"], 1)
            self.assertEqual(r["prediction_id"], rows[0]["prediction_id"])
            self.assertFalse(r["submitted_to_external_provider"])
            self.assertEqual(r["status"], "PENDING_EXTERNAL_WITNESS")

    def test_request_after_game_start_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, rows, _, _ = make_archive(d)
            with self.assertRaisesRegex(ValueError, "after game start"):
                build_anchor_request(path, 1, requested_at=rows[0]["game_start_at"])

    def test_invalid_index(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, _ = make_archive(d)
            with self.assertRaisesRegex(ValueError, "record index"):
                build_anchor_request(path, 0, requested_at=ts(BASE))

    def test_missing_archive(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "missing archive"):
                build_anchor_request(Path(d) / "missing.jsonl", 1, requested_at=ts(BASE))

    def test_consistent_receipt_still_hold(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, receipts = make_archive(d)
            r = inspect_anchor_receipt(path, receipts[0])
            self.assertTrue(r["structural_consistency_passed"])
            self.assertFalse(r["external_witness_authenticated"])
            self.assertEqual(r["status"], "HOLD")

    def test_wrong_hash_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, receipts = make_archive(d)
            receipt = dict(receipts[0])
            receipt["head_hash"] = "a" * 64
            self.assertIn("ANCHOR_HEAD_MISMATCH", inspect_anchor_receipt(path, receipt)["reasons"])

    def test_receipt_after_start_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, rows, _, receipts = make_archive(d)
            receipt = dict(receipts[0])
            receipt["received_at"] = rows[0]["game_start_at"]
            self.assertIn("ANCHOR_NOT_PRE_GAME", inspect_anchor_receipt(path, receipt)["reasons"])

    def test_receipt_before_forecast_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, rows, _, receipts = make_archive(d)
            receipt = dict(receipts[0])
            receipt["received_at"] = ts(BASE)
            self.assertIn("ANCHOR_BEFORE_FORECAST", inspect_anchor_receipt(path, receipt)["reasons"])

    def test_claimed_verification_flag_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, receipts = make_archive(d)
            receipt = dict(receipts[0])
            receipt["verified"] = True
            self.assertIn("INVALID_RECEIPT_FIELDS", inspect_anchor_receipt(path, receipt)["reasons"])

    def test_missing_issuer_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, receipts = make_archive(d)
            receipt = dict(receipts[0])
            receipt["issuer_id"] = ""
            self.assertIn("INVALID_RECEIPT_IDENTITY", inspect_anchor_receipt(path, receipt)["reasons"])

    def test_wrong_prediction_id_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, receipts = make_archive(d)
            receipt = dict(receipts[0])
            receipt["prediction_id"] = "other-prediction"
            self.assertIn("ANCHOR_PREDICTION_MISMATCH", inspect_anchor_receipt(path, receipt)["reasons"])

    def test_missing_receipts_fail_screen(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, results, _ = make_archive(d)
            r = screen_holdout_qualification(path, results, [], min_test=2)
            self.assertIn("ANCHOR_RECEIPT_COVERAGE_INCOMPLETE", r["reasons"])
            self.assertFalse(r["technical_preflight_passed"])

    def test_good_synthetic_screen_still_hold(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, results, receipts = make_archive(d)
            r = screen_holdout_qualification(path, results, receipts, min_test=2, train_fraction=0.5)
            self.assertTrue(r["technical_preflight_passed"])
            self.assertEqual(r["train_count"], 4)
            self.assertEqual(r["test_count"], 4)
            self.assertEqual(r["status"], "HOLD")
            self.assertEqual(r["production_recommendations"], "DISABLED")
            self.assertFalse(r["external_witness_authenticated"])

    def test_duplicate_receipt_fails_screen(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, results, receipts = make_archive(d)
            r = screen_holdout_qualification(path, results, receipts + receipts[:1], min_test=2)
            self.assertIn("DUPLICATE_OR_INVALID_RECEIPT_INDEX", r["reasons"])

    def test_wrong_result_source_claim_fails(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, results, receipts = make_archive(d)
            results[0]["verified"] = False
            r = screen_holdout_qualification(path, results, receipts, min_test=2)
            self.assertIn("HOLDOUT_TEMPORAL_OR_RESULT_INVALID", r["reasons"])
            self.assertFalse(r["technical_preflight_passed"])

    def test_too_small_holdout_fails(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, results, receipts = make_archive(d)
            r = screen_holdout_qualification(path, results, receipts, min_test=30)
            self.assertIn("HOLDOUT_TEMPORAL_OR_RESULT_INVALID", r["reasons"])

    def test_backfilled_train_outcome_fails(self):
        with tempfile.TemporaryDirectory() as d:
            path, rows, results, receipts = make_archive(d)
            results[0]["observed_at"] = rows[4]["forecast_at"]
            r = screen_holdout_qualification(path, results, receipts, min_test=2, train_fraction=0.5)
            self.assertIn("HOLDOUT_TEMPORAL_OR_RESULT_INVALID", r["reasons"])

    def test_rewrite_entire_chain_changes_previously_captured_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, receipts = make_archive(d, n_series=2)
            entries = [json.loads(line) for line in path.read_text().splitlines()]
            entries[0]["forecast"]["probability"] = 0.97
            prev = "0" * 64
            for entry in entries:
                entry["previous_hash"] = prev
                entry["entry_hash"] = _digest(prev, entry["forecast"])
                prev = entry["entry_hash"]
            path.write_text("".join(json.dumps(item) + "\n" for item in entries))
            self.assertIn("ANCHOR_HEAD_MISMATCH",
                          inspect_anchor_receipt(path, receipts[0])["reasons"])

    def test_self_rewritten_receipt_cannot_be_independently_authenticated(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, results, receipts = make_archive(d)
            for receipt in receipts:
                receipt["issuer_id"] = "allegedly-official"
            r = screen_holdout_qualification(path, results, receipts, min_test=2)
            self.assertTrue(r["technical_preflight_passed"])
            self.assertFalse(r["external_witness_authenticated"])
            self.assertIn("EXTERNAL_WITNESS_TRUST_UNVERIFIED", r["reasons"])

    def test_receipt_replay_wrong_index_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, receipts = make_archive(d)
            receipt = dict(receipts[0])
            receipt["record_index"] = 2
            self.assertIn("ANCHOR_HEAD_MISMATCH", inspect_anchor_receipt(path, receipt)["reasons"])

    def test_bad_receipt_clock(self):
        with tempfile.TemporaryDirectory() as d:
            path, _, _, receipts = make_archive(d)
            receipt = dict(receipts[0])
            receipt["received_at"] = "2026-10-01T00:00:00"
            self.assertIn("INVALID_RECEIPT_CLOCK", inspect_anchor_receipt(path, receipt)["reasons"])


if __name__ == "__main__":
    unittest.main()
