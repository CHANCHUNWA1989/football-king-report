"""Red/green J1 cross-provider 1X2 matching: no asymmetric first-win.

Derived vectors and fixture clocks are SYNTHETIC. Not bookmaker raw quotes,
authenticated fixture IDs, live executable odds or positive-EV evidence.
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from japan_free_market import crosscheck


UTC = timezone.utc
T = datetime(2026, 11, 23, 6, 0, tzinfo=UTC)
A = (.38, .27, .35)
B = (.42, .26, .32)


def key(minute=0, *, home="fixture-home", away="fixture-away"):
    return home, away, T + timedelta(minutes=minute)


def diagnostic(a, b):
    result = crosscheck(a, b)
    assert result["independent_venue_quote_verified"] is False
    assert result["api_provider_count_is_not_independent_bookmaker_count"] is True
    return result


class J1CrossApiSymmetricIdentityTests(unittest.TestCase):
    def test_one_unique_two_provider_pair_is_coverage_only(self):
        d = diagnostic({key(): A}, {key(): B})
        self.assertEqual(d["same_fixture_two_api_observations"], 1)
        self.assertAlmostEqual(d["median_abs_home_probability_delta"], .04)
        self.assertFalse(d["independent_venue_quote_verified"])

    def test_two_a_candidates_one_b_cannot_first_win(self):
        d = diagnostic({key(): A, key(5): A}, {key(2): B})
        self.assertEqual(d["same_fixture_two_api_observations"], 0)
        self.assertIsNone(d["median_abs_home_probability_delta"])

    def test_two_a_candidates_one_b_independent_of_row_order(self):
        forward = {key(): A, key(5): A}
        backward = {key(5): A, key(): A}
        self.assertEqual(diagnostic(forward, {key(2): B}),
                         diagnostic(backward, {key(2): B}))
        self.assertEqual(diagnostic(forward, {key(2): B})[
            "same_fixture_two_api_observations"], 0)

    def test_one_a_two_b_candidates_ambiguous_on_b_side(self):
        d = diagnostic({key(): A}, {key(-2): B, key(2): B})
        self.assertEqual(d["same_fixture_two_api_observations"], 0)
        self.assertIsNone(d["median_abs_home_probability_delta"])

    def test_competing_edges_must_be_rejected_both_directions(self):
        # A1 -> {B1,B2}; A2 -> {B2}. Old implementation skips A1 then
        # mistakenly accepts A2/B2 despite B2 being claimed by two A rows.
        d = diagnostic(
            {key(): A, key(45): A},
            {key(0): B, key(20): B},
        )
        self.assertEqual(d["same_fixture_two_api_observations"], 0)
        self.assertIsNone(d["median_abs_home_probability_delta"])

    def test_distinct_nonoverlapping_fixtures_remain_two_observations(self):
        d = diagnostic(
            {key(0): A, key(120): A},
            {key(0): B, key(120): B},
        )
        self.assertEqual(d["same_fixture_two_api_observations"], 2)
        self.assertAlmostEqual(d["median_abs_home_probability_delta"], .04)

    def test_one_conflicted_fixture_does_not_contaminate_independent_one(self):
        d = diagnostic(
            {key(0): A, key(5): A, key(120): A},
            {key(2): B, key(120): B},
        )
        self.assertEqual(d["same_fixture_two_api_observations"], 1)
        self.assertAlmostEqual(d["median_abs_home_probability_delta"], .04)

    def test_different_team_ids_are_never_matched(self):
        d = diagnostic(
            {key(home="home-id-1"): A},
            {key(home="home-id-2"): B},
        )
        self.assertEqual(d["same_fixture_two_api_observations"], 0)

    def test_swapped_home_away_order_is_never_fuzzy_matched(self):
        d = diagnostic(
            {key(home="A",away="B"): A},
            {key(home="B",away="A"): B},
        )
        self.assertEqual(d["same_fixture_two_api_observations"], 0)

    def test_kickoff_30min_boundary_remains_coverage_not_authentication(self):
        d = diagnostic({key(0): A}, {key(30): B})
        self.assertEqual(d["same_fixture_two_api_observations"], 1)
        self.assertFalse(d["independent_venue_quote_verified"])

    def test_31min_kickoff_difference_rejected(self):
        d = diagnostic({key(0): A}, {key(31): B})
        self.assertEqual(d["same_fixture_two_api_observations"], 0)

    def test_empty_provider_returns_zero_without_fabricated_delta(self):
        self.assertEqual(diagnostic({}, {key(): B})[
            "same_fixture_two_api_observations"], 0)
        self.assertIsNone(diagnostic({key(): A}, {})[
            "median_abs_home_probability_delta"])


if __name__ == "__main__":
    unittest.main()
