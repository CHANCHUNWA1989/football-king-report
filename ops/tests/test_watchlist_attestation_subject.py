"""No-network tests for digest-only, pre-recorded-kickoff witness preparation."""
import unittest
from datetime import datetime, timezone, timedelta
from ops.watchlist_attestation_subject import subject

NOW = datetime(2026, 11, 7, 9, tzinfo=timezone.utc)


class AttestationSubjectTests(unittest.TestCase):
    def test_valid_subject_contains_only_sha_digest(self):
        result = subject("a"*64, "2026-11-07T09:30:00Z", now=NOW)
        self.assertEqual(result, ("a"*64+"\n").encode("ascii"))
        self.assertNotIn(b"quote", result)

    def test_boundary_requires_more_than_ten_minutes(self):
        for when in ("2026-11-07T09:10:00Z", "2026-11-07T09:09:59Z",
                     "2026-11-07T08:00:00Z"):
            with self.subTest(time=when), self.assertRaisesRegex(
                    ValueError, "NOT_EARLY_ENOUGH"):
                subject("b"*64, when, now=NOW)

    def test_invalid_and_malicious_digest_rejected(self):
        for value in (None, "x"*64, "A"*64, "a"*63, "a"*65,
                      "a"*64+"\nsecret=abc", True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                subject(value, "2026-11-07T10:00:00Z", now=NOW)

    def test_naive_or_invalid_kickoff_rejected(self):
        for value in ("2026-11-07T10:00:00", "garbage", None, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                subject("b"*64, value, now=NOW)

    def test_equivalent_hk_time_allowed(self):
        self.assertEqual(
            subject("a"*64, "2026-11-07T17:30:00+08:00", now=NOW),
            subject("a"*64, "2026-11-07T09:30:00Z", now=NOW))


if __name__ == "__main__":
    unittest.main()
