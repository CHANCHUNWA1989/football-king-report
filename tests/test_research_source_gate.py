import unittest
from research_quality.source_gate import validate_source_record, validate_probabilities


class SourceGateTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(source="independent-feed", event_id="match-1",
                        observed_at="2026-10-17T10:00:00Z",
                        event_at="2026-10-17T13:00:00Z")

    def test_valid_source(self):
        self.assertTrue(validate_source_record(self.row, now_utc="2026-10-17T11:00:00Z"))

    def test_stale_source_rejected(self):
        with self.assertRaisesRegex(ValueError, "STALE_SOURCE"):
            validate_source_record(self.row, now_utc="2026-10-19T11:00:00Z")

    def test_future_source_rejected(self):
        with self.assertRaisesRegex(ValueError, "FUTURE_SOURCE"):
            validate_source_record(self.row, now_utc="2026-10-17T09:00:00Z")

    def test_post_event_rejected(self):
        row = dict(self.row, observed_at="2026-10-17T14:00:00Z")
        with self.assertRaisesRegex(ValueError, "POST_EVENT_SOURCE"):
            validate_source_record(row, now_utc="2026-10-17T15:00:00Z")

    def test_naive_timestamp_rejected(self):
        with self.assertRaisesRegex(ValueError, "TIMEZONE_REQUIRED"):
            validate_source_record(self.row, now_utc="2026-10-17T11:00:00")

    def test_distribution(self):
        self.assertTrue(validate_probabilities([0.3, 0.4, 0.3]))
        for values in ([0.5, 0.6], [float("nan"), 1], [True, False], [0.5]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate_probabilities(values)


if __name__ == "__main__":
    unittest.main()
