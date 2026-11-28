import gzip
import json
import unittest
from pathlib import Path
from ops.model_divergence_archive import ARCHIVE_PATH
from ops.model_divergence_statistics import summarize_archive, _diagnose


class StatisticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=(Path(__file__).resolve().parents[2]/ARCHIVE_PATH).read_bytes()

    def document(self):
        return json.loads(gzip.decompress(self.data))

    def test_actual_four_model_statistics(self):
        r=summarize_archive(self.data)
        self.assertTrue(r["archive_diagnostics_valid"])
        self.assertEqual(r["complete_count"],49)
        self.assertEqual(r["categories"],{"direction_conflict":5,"large_gap":10,
                                          "no_large_disagreement":34})
        self.assertAlmostEqual(r["max_gap"],.1751624,places=6)
        self.assertEqual(len(r["pairwise"]),6)
        self.assertEqual(r["pairwise"]["AC"]["direction_conflicts"],5)
        self.assertTrue(all(x["n"]==49 for x in r["pairwise"].values()))

    def test_no_promotion_or_authentication(self):
        r=summarize_archive(self.data)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        for k in ("can_recommend_bets","source_authenticated","independent_model_evidence",
                  "model_calibrated","threshold_calibrated"):
            self.assertIs(r[k],False)
        self.assertEqual(r["certified_outcomes"],0)
        self.assertEqual(r["qualified_external_pairs"],0)
        self.assertNotIn("Ipswich",str(r))

    def test_tampered_bytes(self):
        r=summarize_archive(self.data[:-1]+bytes([self.data[-1]^1]))
        self.assertFalse(r["archive_diagnostics_valid"])
        self.assertEqual(r["complete_count"],0)

    def test_missing_challenger_retained_as_incomplete(self):
        d=self.document()
        c=d["opponent_adjusted_forward_challenger"]
        c["predictions"].pop()
        c["predictions_count"]-=1
        r=_diagnose(d)
        self.assertEqual(r["complete_count"],48)
        self.assertEqual(r["categories"]["incomplete"],1)

    def test_duplicate_or_out_of_scope(self):
        for duplicate in (True,False):
            d=self.document()
            c=d["opponent_adjusted_forward_challenger"]["predictions"]
            if duplicate:
                c[1]=dict(c[0])
            else:
                c[0]["event_id"]="not_in_archive"
            with self.assertRaises(ValueError):
                _diagnose(d)

    def test_identity_clock_and_vector_mismatch(self):
        for k,v in (("home","wrong"),("kickoff_utc","2026-12-01T12:00:00Z"),
                    ("original_prediction_utc","2026-11-01T12:00:00Z"),
                    ("original",[1,0,0]),("p",[True,0,0])):
            d=self.document()
            d["opponent_adjusted_forward_challenger"]["predictions"][0][k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):
                _diagnose(d)

    def test_deterministic(self):
        self.assertEqual(summarize_archive(self.data),summarize_archive(self.data))
