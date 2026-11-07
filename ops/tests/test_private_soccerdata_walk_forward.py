import unittest
from ops.private_soccerdata_walk_forward import make_walk_forward_folds


def record(i, day):
    return {"source": "soccerdata.MatchHistory", "source_index": str(i),
            "source_local_match_datetime": day + "T15:00:00",
            "kickoff_time_verified": False, "pre_match_features_verified": False,
            "outcome": "H"}


class WalkForwardTests(unittest.TestCase):
    def test_only_earlier_days_train(self):
        rows = [record(1, "2026-01-01"), record(2, "2026-01-01"),
                record(3, "2026-01-02"), record(4, "2026-01-03")]
        report = make_walk_forward_folds(rows, min_train=2, test_days=1)
        self.assertEqual(report["fold_count"], 2)
        self.assertEqual(report["folds"][0]["train_ids"], ["1", "2"])
        self.assertEqual(report["folds"][0]["test_ids"], ["3"])
        self.assertFalse(report["models_fitted"])

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            make_walk_forward_folds([record(1, "2026-01-01"), record(1, "2026-01-02")])

    def test_fake_verified_timestamp_rejected(self):
        row = record(1, "2026-01-01")
        row["kickoff_time_verified"] = True
        with self.assertRaises(ValueError):
            make_walk_forward_folds([row])

    def test_timezone_claim_rejected(self):
        row = record(1, "2026-01-01")
        row["source_local_match_datetime"] += "+00:00"
        with self.assertRaises(ValueError):
            make_walk_forward_folds([row])


if __name__ == "__main__":
    unittest.main()
