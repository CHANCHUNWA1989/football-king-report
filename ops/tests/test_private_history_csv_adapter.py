import unittest
from ops.private_history_csv_adapter import convert

CSV_HEADER = "Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n"
ROWS = "".join(f"01/{(i % 28) + 1:02d}/2026,Home,Away,2,1,H\n" for i in range(30))


class HistoryCSVTests(unittest.TestCase):
    def setUp(self):
        self.raw = (CSV_HEADER + ROWS).encode()
        self.kwargs = {"league": "epl", "season": "2025-26",
                       "crosswalk": {"Home": "Arsenal", "Away": "Chelsea"},
                       "recorded_utc": "2026-04-01T00:00:00+00:00",
                       "source": "manual_vetted_football_data_csv"}

    def test_valid_csv(self):
        self.assertEqual(len(convert(self.raw, **self.kwargs)["matches"]), 30)

    def test_missing_crosswalk(self):
        self.kwargs["crosswalk"].pop("Away")
        with self.assertRaises(ValueError):
            convert(self.raw, **self.kwargs)

    def test_mismatched_result(self):
        with self.assertRaises(ValueError):
            convert(self.raw.replace(b",2,1,H", b",2,1,A"), **self.kwargs)

    def test_duplicate_fixture(self):
        with self.assertRaises(ValueError):
            convert((CSV_HEADER + ROWS.splitlines(keepends=True)[0] * 30).encode(), **self.kwargs)

    def test_unavailable_future_result(self):
        self.kwargs["recorded_utc"] = "2026-01-01T00:00:00+00:00"
        with self.assertRaises(ValueError):
            convert(self.raw, **self.kwargs)

    def test_missing_columns(self):
        with self.assertRaises(ValueError):
            convert(b"Date,HomeTeam\n01/01/2026,Home\n", **self.kwargs)


if __name__ == "__main__":
    unittest.main()
