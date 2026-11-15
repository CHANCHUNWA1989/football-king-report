"""Offline synthetic contract tests; not an upstream-package integration test."""
import unittest
from types import SimpleNamespace as Obj

from ops.optional_kloppy_event_research import (
    MAX_EVENTS, SCHEMA, summarize_local_event_dataset,
)


class KloppyLocalEventResearchTests(unittest.TestCase):
    def setUp(self):
        self.home = Obj(team_id="src-H")
        self.away = Obj(team_id="src-A")
        self.dataset = Obj(
            metadata=Obj(game_id="fixture-123", teams=[self.home, self.away]),
            events=[
                Obj(event_id="ev-1", event_name="PASS", team=self.home),
                Obj(event_id="ev-2", event_name="SHOT", team=self.away),
                Obj(event_id="ev-3", event_name="GENERIC", team=None),
            ],
        )
        self.manifest = {
            "schema": SCHEMA,
            "source_namespace": "licensed_history_test",
            "source_event_id": "fixture-123",
            "rights_reference_url": "https://example.org/terms",
            "source_available_utc": "2026-10-01T18:30:00Z",
            "target_as_of_utc": "2026-11-01T10:00:00Z",
        }

    def evaluate(self):
        return summarize_local_event_dataset(self.dataset, self.manifest)

    def test_historical_kloppy_shaped_dataset_only_returns_descriptive_counts(self):
        result = self.evaluate()
        self.assertEqual(result["events_recorded"], 3)
        self.assertEqual(result["team_event_counts"]["src-H"], {"pass": 1, "shot": 0})
        self.assertEqual(result["team_event_counts"]["src-A"], {"pass": 0, "shot": 1})
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["positive_ev_verified"])
        self.assertFalse(result["pre_match_features_approved"])
        self.assertFalse(result["source_data_rights_independently_verified"])
        self.assertFalse(result["source_event_capture_independently_verified"])
        self.assertFalse(result["native_match_identity_independently_verified"])
        self.assertFalse(result["results_independently_verified"])
        self.assertFalse(result["automatic_bets"])
        self.assertNotIn("p_home", result)
        self.assertNotIn("predicted_xg", result)

    def test_rejects_native_match_id_mismatch(self):
        self.dataset.metadata.game_id = "another-game"
        with self.assertRaisesRegex(ValueError, "MISMATCHED_NATIVE_MATCH_ID"):
            self.evaluate()

    def test_rejects_duplicate_or_missing_team_ids(self):
        self.dataset.metadata.teams[1].team_id = "src-H"
        with self.assertRaisesRegex(ValueError, "DUPLICATE_NATIVE_TEAM_ID"):
            self.evaluate()
        self.dataset.metadata.teams = [self.home]
        with self.assertRaisesRegex(ValueError, "TWO_NATIVE_TEAMS_REQUIRED"):
            self.evaluate()

    def test_rejects_cross_source_unknown_event_team(self):
        self.dataset.events[0].team = Obj(team_id="another-feed-A")
        with self.assertRaisesRegex(ValueError, "UNKNOWN_EVENT_TEAM"):
            self.evaluate()

    def test_rejects_duplicate_event_identifiers(self):
        self.dataset.events[1].event_id = "ev-1"
        with self.assertRaisesRegex(ValueError, "DUPLICATE_NATIVE_EVENT_ID"):
            self.evaluate()

    def test_rejects_wrong_cutoff_or_naive_observation_time(self):
        for available, cutoff in (
            ("2026-11-02T00:00:00Z", "2026-11-01T10:00:00Z"),
            ("2026-11-01T10:00:00Z", "2026-11-01T10:00:00Z"),
            ("2026-10-01T18:30:00", "2026-11-01T10:00:00Z"),
            ("2026-10-01T18:30:00Z", "2026-11-01T10:00:00"),
        ):
            with self.subTest(available=available, cutoff=cutoff):
                self.manifest["source_available_utc"] = available
                self.manifest["target_as_of_utc"] = cutoff
                with self.assertRaises(ValueError):
                    self.evaluate()

    def test_rejects_missing_rights_reference_or_non_https(self):
        for url in ("", "http://example.org/terms", "file:///terms",
                    "https://", "https://user:secret@example.org/terms"):
            with self.subTest(url=url):
                self.manifest["rights_reference_url"] = url
                with self.assertRaisesRegex(ValueError, "RIGHTS_REFERENCE_REQUIRED"):
                    self.evaluate()

    def test_manifest_cannot_assert_certified_or_production_status(self):
        self.manifest["results_independently_verified"] = True
        with self.assertRaisesRegex(ValueError, "INVALID_KLOPPY_MANIFEST"):
            self.evaluate()

    def test_invalid_source_identity_is_rejected(self):
        for namespace in ("StatsBomb Open", "../x", "", "data\npass"):
            with self.subTest(namespace=namespace):
                self.manifest["source_namespace"] = namespace
                with self.assertRaises(ValueError):
                    self.evaluate()

    def test_empty_or_malformed_events_fail_closed(self):
        self.dataset.events = []
        with self.assertRaisesRegex(ValueError, "NO_EVENTS"):
            self.evaluate()
        self.dataset.events = "forged event data"
        with self.assertRaisesRegex(ValueError, "EVENTS_NOT_ITERABLE"):
            self.evaluate()

    def test_unrecognized_event_type_is_not_renamed_into_shot(self):
        self.dataset.events[0].event_name = "OWN_GOAL"
        self.dataset.events[1].event_name = "GENERIC"
        result = self.evaluate()
        self.assertEqual(sum(v["shot"] for v in result["team_event_counts"].values()), 0)

    def test_event_limit_is_bounded(self):
        self.dataset.events = (
            Obj(event_id="ev-" + str(i), event_name="GENERIC", team=None)
            for i in range(MAX_EVENTS + 1)
        )
        with self.assertRaisesRegex(ValueError, "EVENT_LIMIT_EXCEEDED"):
            self.evaluate()


if __name__ == "__main__":
    unittest.main()
