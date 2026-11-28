import unittest
from pathlib import Path
from ops.model_divergence_archive import (ARCHIVE_PATH, ARCHIVE_SIZE,
                                          inspect_archive, render_archive)


class ArchiveReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = (Path(__file__).resolve().parents[2] / ARCHIVE_PATH).read_bytes()

    def test_actual_pinned_archive(self):
        self.assertEqual(len(self.data), ARCHIVE_SIZE)
        result = inspect_archive(self.data)
        self.assertTrue(result["archive_blob_match"])
        self.assertEqual(result["archived_forecast_count"], 49)
        self.assertEqual(result["qualified_pair_count"], 0)
        self.assertEqual(result["reason"], "NO_VERIFIED_EXTERNAL_XG_PAIR")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        for flag in ("source_authenticated","model_calibrated",
                     "model_input_derivation_verified","external_xg_verified",
                     "can_recommend_bets"):
            self.assertIs(result[flag], False)

    def test_actual_mobile_report(self):
        html = render_archive(self.data)
        for phrase in ("HOLD／DISABLED", "固定歷史封存重播",
                       "原有研究預測場數：49", "合格跨來源模型配對：0",
                       "非即時數據", "viewport"):
            self.assertIn(phrase, html)
        for secret in ("Ipswich Town FC","Aston Villa FC","expected_home_goals",
                       "prediction_utc","<script"):
            self.assertNotIn(secret, html)

    def test_single_byte_replacement(self):
        changed = self.data[:-1] + bytes([self.data[-1] ^ 1])
        self.assertEqual(len(changed), len(self.data))
        result = inspect_archive(changed)
        self.assertFalse(result["archive_blob_match"])
        self.assertEqual(result["archived_forecast_count"], 0)
        self.assertEqual(result["status"], "HOLD")
        self.assertNotIn("原有研究預測場數：49", render_archive(changed))

    def test_missing_truncated_and_wrong_types(self):
        for value in (None, b"", self.data[:-1], self.data+b"x",
                      bytearray(self.data), "not bytes"):
            with self.subTest(kind=type(value).__name__):
                result = inspect_archive(value)
                self.assertEqual(result["reason"], "INVALID_PINNED_ARCHIVE")
                self.assertEqual(result["qualified_pair_count"], 0)
                self.assertFalse(result["archive_blob_match"])
                self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_replay_deterministic_no_mutation(self):
        self.assertEqual(inspect_archive(self.data), inspect_archive(self.data))
        self.assertEqual(render_archive(self.data), render_archive(self.data))
        self.assertEqual(self.data, (Path(__file__).resolve().parents[2] / ARCHIVE_PATH).read_bytes())
