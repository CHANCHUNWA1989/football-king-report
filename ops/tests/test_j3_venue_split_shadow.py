"""Synthetic J3 as-of venue split diagnostics, never real betting advice."""
import copy
import unittest

from ops.j3_venue_split_shadow import audit


AS_OF = "2026-11-15T08:00:00+00:00"
TARGET = {
    "league": "j3", "season": "2026-27", "event_id": "j3-shiga-osaka-1115",
    "home_id": "reilac-shiga", "away_id": "fc-osaka",
    "kickoff_utc": "2026-11-15T09:00:00+00:00",
}


def match(n, home, away, score, day):
    return {
        "league": "j3", "season": "2026-27",
        "event_id": "synthetic-fixture-" + str(n),
        "home_id": home, "away_id": away,
        "kickoff_utc": f"2026-10-{day:02}T08:00:00+00:00",
        "final_observed_utc": f"2026-10-{day:02}T10:30:00+00:00",
        "archived_utc": f"2026-10-{day:02}T11:00:00+00:00",
        "match_status": "FT", "home_goals": score[0], "away_goals": score[1],
    }


def history():
    return [
        match(1, "reilac-shiga", "rival-a", (1, 0), 1),  # home win
        match(2, "reilac-shiga", "rival-b", (0, 1), 3),  # home loss
        match(3, "reilac-shiga", "rival-c", (1, 1), 5),  # home draw
        match(4, "reilac-shiga", "rival-d", (2, 2), 7),  # home draw
        match(5, "rival-e", "fc-osaka", (0, 1), 9),      # away win
        match(6, "rival-f", "fc-osaka", (1, 1), 11),     # away draw
        match(7, "rival-g", "fc-osaka", (2, 0), 13),     # away loss
        match(8, "rival-h", "fc-osaka", (2, 2), 15),     # away draw
        match(9, "rival-a", "rival-z", (4, 1), 17),     # unrelated
    ]


class J3VenueSplitShadowTests(unittest.TestCase):

    def test_true_home_away_venue_splits_not_all_form(self):
        out = audit(TARGET, history(), as_of_utc=AS_OF)
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(out["history_rows_inspected"], 9)
        self.assertEqual(out["target_home_at_home"]["matches"], 4)
        self.assertEqual(out["target_home_at_home"]["wins"], 1)
        self.assertEqual(out["target_home_at_home"]["draws"], 2)
        self.assertEqual(out["target_home_at_home"]["losses"], 1)
        self.assertAlmostEqual(out["target_home_at_home"]["draw_fraction_unverified"], .5)
        self.assertEqual(out["target_away_away"]["matches"], 4)
        self.assertEqual(out["target_away_away"]["wins"], 1)
        self.assertEqual(out["target_away_away"]["draws"], 2)
        self.assertEqual(out["target_away_away"]["losses"], 1)
        self.assertAlmostEqual(out["target_away_away"]["draw_fraction_unverified"], .5)
        self.assertTrue(out["as_of_metadata_only_not_authenticated"])
        self.assertEqual(out["independently_certified_history_cases"], 0)
        self.assertFalse(out["venue_form_independently_verified"])
        self.assertFalse(out["calibrated_draw_probability_available"])
        self.assertFalse(out["positive_ev_verified"])
        self.assertIsNone(out["bookmaker_odds"])
        self.assertIsNone(out["recommended_stake"])
        self.assertEqual(out["production_recommendations"], "DISABLED")

    def test_no_rows_cannot_invent_venue_form(self):
        out = audit(TARGET, [], as_of_utc=AS_OF)
        self.assertEqual(out["target_home_at_home"]["matches"], 0)
        self.assertEqual(out["target_away_away"]["matches"], 0)
        self.assertIsNone(out["target_away_away"]["draw_fraction_unverified"])
        self.assertFalse(out["j3_market_or_model_coverage_verified"])

    def test_future_ft_and_after_asof_archival_are_rejected(self):
        for field, val in (
            ("kickoff_utc", "2026-11-15T09:00:00+00:00"),
            ("final_observed_utc", "2026-11-15T08:05:00+00:00"),
            ("archived_utc", "2026-11-15T08:05:00+00:00"),
            ("final_observed_utc", "2026-10-01T07:59:00+00:00"),
        ):
            rows = history()
            rows[0][field] = val
            with self.subTest(field=field, val=val):
                with self.assertRaises(ValueError):
                    audit(TARGET, rows, as_of_utc=AS_OF)

    def test_live_cancelled_and_unknown_scores_cannot_become_ft(self):
        for status in ("LIVE", "POSTPONED", "ABANDONED", "HT", None):
            rows = history()
            rows[0]["match_status"] = status
            with self.subTest(status=status), self.assertRaises(ValueError):
                audit(TARGET, rows, as_of_utc=AS_OF)
        for v in (True, "1", -1, 99, None):
            rows = history()
            rows[0]["home_goals"] = v
            with self.subTest(goal=v), self.assertRaises(ValueError):
                audit(TARGET, rows, as_of_utc=AS_OF)

    def test_duplicate_provider_id_and_duplicated_fixture_are_quarantined(self):
        for edit in ("same_id", "same_fixture"):
            rows = history()
            duplicate = copy.deepcopy(rows[0])
            if edit == "same_fixture":
                duplicate["event_id"] = "different-id"
            rows.append(duplicate)
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                audit(TARGET, rows, as_of_utc=AS_OF)

    def test_cannot_learn_from_target_fixture_result(self):
        rows = history()
        row = copy.deepcopy(rows[0])
        row.update(event_id=TARGET["event_id"])
        rows.append(row)
        with self.assertRaises(ValueError):
            audit(TARGET, rows, as_of_utc=AS_OF)

    def test_wrong_league_season_or_team_identity_fails_closed(self):
        for key, val in (("league", "j1"), ("season", "2025"),
                         ("home_id", "fc-osaka"), ("event_id", "")):
            target = dict(TARGET)
            target[key] = val
            with self.subTest(key=key, val=val), self.assertRaises(ValueError):
                audit(target, history(), as_of_utc=AS_OF)
        for key, val in (("league", "j1"), ("season", "2025"),
                         ("away_id", "reilac-shiga")):
            rows = history()
            rows[0][key] = val
            with self.subTest(key=key), self.assertRaises(ValueError):
                audit(TARGET, rows, as_of_utc=AS_OF)

    def test_invalid_cutoff_and_history_bounds_rejected(self):
        for cutoff in ("invalid", "2026-11-15T08:00:00", "2026-11-15T10:00:00+00:00"):
            with self.subTest(cutoff=cutoff), self.assertRaises(ValueError):
                audit(TARGET, history(), as_of_utc=cutoff)
        with self.assertRaises(ValueError):
            audit(TARGET, history() * 200, as_of_utc=AS_OF)


    def test_same_japan_matchday_different_provider_id_kickoff_drift_rejected(self):
        # Exact timestamp dedupe is insufficient: a second provider may
        # give the same match a different ID and a 30 minute kickoff shift.
        rows = history()
        alias = copy.deepcopy(rows[0])
        alias.update(event_id="other-provider-fixture-1",
                     kickoff_utc="2026-10-01T08:30:00+00:00",
                     final_observed_utc="2026-10-01T11:00:00+00:00",
                     archived_utc="2026-10-01T11:30:00+00:00")
        rows.append(alias)
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS_LOCAL_MATCHDAY"):
            audit(TARGET, rows, as_of_utc=AS_OF)

    def test_same_team_two_j3_matches_in_same_japan_day_quarantined(self):
        # Even with a new rival, no J3 club should be counted twice
        # on one Japan-local matchday; otherwise venue form is inflated.
        rows = history()
        second = copy.deepcopy(rows[1])  # Shiga home versus a different rival
        second.update(kickoff_utc="2026-10-01T10:00:00+00:00",
                      final_observed_utc="2026-10-01T12:30:00+00:00",
                      archived_utc="2026-10-01T13:00:00+00:00")
        rows[1] = second
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS_LOCAL_MATCHDAY"):
            audit(TARGET, rows, as_of_utc=AS_OF)

    def test_two_unrelated_teams_same_day_remain_legal_and_no_false_merge(self):
        rows = history()
        unrelated = copy.deepcopy(rows[-1])
        unrelated.update(home_id="rival-u", away_id="rival-v",
                         kickoff_utc="2026-10-01T10:00:00+00:00",
                         final_observed_utc="2026-10-01T12:30:00+00:00",
                         archived_utc="2026-10-01T13:00:00+00:00")
        rows[-1] = unrelated
        result = audit(TARGET, rows, as_of_utc=AS_OF)
        self.assertEqual(result["history_rows_inspected"], 9)
        self.assertEqual(result["target_home_at_home"]["matches"], 4)
        self.assertEqual(result["target_away_away"]["matches"], 4)

    def test_hkt_alias_same_instant_not_new_fixture(self):
        target = dict(TARGET)
        target["kickoff_utc"] = "2026-11-15T17:00:00+08:00"
        out = audit(target, history(), as_of_utc="2026-11-15T16:00:00+08:00")
        self.assertEqual(out["target_away_away"]["draws"], 2)
        self.assertEqual(out["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
