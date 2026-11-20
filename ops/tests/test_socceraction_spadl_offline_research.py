"""Pure standard-library SPADL research gate tests; no external pip modules.

The real Socceraction 1.5.3 StatsBomb sample conversion runs separately in
an isolated research environment, never in production or GitHub default CI.
"""
from copy import deepcopy
import unittest
from unittest.mock import patch

from ops import socceraction_spadl_offline_research as research


class SocceractionSPADLResearchGateTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"game_id": 3788741, "action_id": 0, "team_id": 909,
             "period_id": 1, "time_seconds": 0.878, "start_x": 52.4,
             "start_y": 34.0, "end_x": 28.3, "end_y": 43.5,
             "type_name": "pass"},
            {"game_id": 3788741, "action_id": 1, "team_id": 914,
             "period_id": 1, "time_seconds": 1.5, "start_x": 31.0,
             "start_y": 33.0, "end_x": 34.0, "end_y": 32.0,
             "type_name": "shot"},
        ]

    def evaluate(self):
        return research.summarize_spadl_rows(self.rows)

    def test_verified_shape_returns_descriptive_counts_only(self):
        x = self.evaluate()
        self.assertEqual(x["action_count"], 2)
        self.assertEqual(x["action_type_counts"], {"pass": 1, "shot": 1})
        self.assertEqual(x["team_action_counts"], {"909": 1, "914": 1})
        self.assertNotIn("xT", x)
        self.assertNotIn("EV", x)

    def test_cross_match_id_rejected(self):
        self.rows[0]["game_id"] = 999
        with self.assertRaisesRegex(ValueError, "CROSS_MATCH_SPADL_ACTION"):
            self.evaluate()

    def test_unknown_team_rejected(self):
        self.rows[0]["team_id"] = 111
        with self.assertRaisesRegex(ValueError, "UNKNOWN_SPADL_TEAM"):
            self.evaluate()

    def test_single_team_suspicious_sample_rejected(self):
        self.rows[1]["team_id"] = 909
        with self.assertRaisesRegex(ValueError, "BOTH_TEAMS_MUST_HAVE"):
            self.evaluate()

    def test_missing_action_id_or_repeated_id_rejected(self):
        for bad in (None, 0, 3):
            with self.subTest(bad=bad):
                self.rows[1]["action_id"] = bad
                with self.assertRaisesRegex(ValueError, "SPADL_ACTION_INDEX_MISMATCH"):
                    self.evaluate()

    def test_time_reversal_or_period_backwards_rejected(self):
        self.rows[1]["time_seconds"] = 0.1
        with self.assertRaisesRegex(ValueError, "SPADL_ACTIONS_OUT_OF_ORDER"):
            self.evaluate()
        self.rows[0]["period_id"] = 2
        self.rows[1]["period_id"] = 1
        with self.assertRaisesRegex(ValueError, "SPADL_ACTIONS_OUT_OF_ORDER"):
            self.evaluate()

    def test_invalid_time_nan_inf_negative_bool_rejected(self):
        for bad in (float("nan"), float("inf"), -1, True, "bad"):
            with self.subTest(bad=bad):
                self.rows[0]["time_seconds"] = bad
                with self.assertRaisesRegex(ValueError, "INVALID_SPADL_CLOCK"):
                    self.evaluate()

    def test_outside_pitch_nan_inf_boolean_coords_rejected(self):
        for axis, bad in (("start_x", -0.1), ("end_x", 105.1),
                          ("start_y", 68.1), ("end_y", float("nan")),
                          ("end_x", float("inf")), ("start_x", True)):
            with self.subTest(axis=axis, bad=bad):
                copied = deepcopy(self.rows)
                copied[0][axis] = bad
                with self.assertRaisesRegex(ValueError, "INVALID_SPADL_COORDINATES"):
                    research.summarize_spadl_rows(copied)

    def test_invalid_action_type_rejected(self):
        for bad in (None, "", " shot", "a" * 65, 123):
            with self.subTest(bad=bad):
                self.rows[0]["type_name"] = bad
                with self.assertRaisesRegex(ValueError, "INVALID_SPADL_ACTION_TYPE"):
                    self.evaluate()

    def test_empty_or_oversized_action_sequence_fails(self):
        with self.assertRaisesRegex(ValueError, "INVALID_SPADL_ACTION_COUNT"):
            research.summarize_spadl_rows([])
        with self.assertRaisesRegex(ValueError, "INVALID_SPADL_ACTION_COUNT"):
            research.summarize_spadl_rows([None] * (research.MAX_ACTIONS + 1))

    def test_invalid_period_or_unstructured_rows_rejected(self):
        self.rows[0]["period_id"] = 3
        with self.assertRaisesRegex(ValueError, "INVALID_SPADL_PERIOD"):
            self.evaluate()
        with self.assertRaisesRegex(ValueError, "INVALID_SPADL_ACTION_ROW"):
            research.summarize_spadl_rows([123, self.rows[1]])

    def test_optional_dependency_versions_are_exact(self):
        from importlib import metadata
        with patch.object(research.metadata, "version",
                          side_effect=lambda name: {"socceraction": "1.5.3",
                                                     "pandera": "0.17.2",
                                                     "multimethod": "1.12"}[name]):
            self.assertEqual(research._ensure_optional_package_versions(),
                             research.REQUIRED_INSTALLED_VERSIONS)
        with patch.object(research.metadata, "version",
                          side_effect=lambda name: "999.0"):
            with self.assertRaisesRegex(ValueError, "UNVERIFIED_RESEARCH_PACKAGE_VERSION"):
                research._ensure_optional_package_versions()
        with patch.object(research.metadata, "version",
                          side_effect=metadata.PackageNotFoundError("socceraction")):
            with self.assertRaisesRegex(ValueError, "RESEARCH_PACKAGE_NOT_INSTALLED"):
                research._ensure_optional_package_versions()

    def test_source_hash_validation_is_before_optional_package_import(self):
        with patch.object(research, "_read_fixed_file",
                          side_effect=ValueError("OFFICIAL_SAMPLE_SHA256_MISMATCH")):
            with patch.object(research, "_ensure_optional_package_versions") as versions:
                with self.assertRaisesRegex(ValueError, "OFFICIAL_SAMPLE_SHA256_MISMATCH"):
                    research.summarize_verified_historical_spadl("/bad", "/bad")
                versions.assert_not_called()


if __name__ == "__main__":
    unittest.main()
