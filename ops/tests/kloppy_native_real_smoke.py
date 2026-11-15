"""Real Kloppy 3.19.1 installed-package smoke; fully synthetic native objects.

Run ONLY on an explicitly approved isolated local runner. No actual event files,
website, network data sources, credentials, betting market or predictions.
"""
import unittest
from datetime import timedelta
from importlib.metadata import version

from kloppy.domain import (
    DatasetFlag, EventDataset, GenericEvent, Ground, Metadata, Orientation,
    PassEvent, PassResult, Period, Provider, ShotEvent, ShotResult, Team,
)
from ops.optional_kloppy_event_research import SCHEMA, summarize_local_event_dataset


class InstalledKloppyNativeContract(unittest.TestCase):
    def setUp(self):
        period = Period(
            id=1, start_timestamp=timedelta(0),
            end_timestamp=timedelta(minutes=45),
        )
        home = Team(team_id="synthetic-H", name="Synthetic Home", ground=Ground.HOME)
        away = Team(team_id="synthetic-A", name="Synthetic Away", ground=Ground.AWAY)
        metadata = Metadata(
            periods=[period], teams=[home, away],
            coordinate_system=None, pitch_dimensions=None,
            orientation=Orientation.NOT_SET, flags=DatasetFlag(0),
            provider=Provider.KLOPPY, game_id="synthetic-match-1",
        )

        def event(cls, event_id, team, **kwargs):
            return cls(
                event_id=event_id, period=period,
                timestamp=timedelta(minutes=1), statistics=[],
                ball_owning_team=team, ball_state=None, team=team,
                player=None, coordinates=None, raw_event=None,
                state={}, related_event_ids=[], freeze_frame=None,
                **kwargs,
            )

        self.dataset = EventDataset(
            records=[
                event(PassEvent, "synthetic-pass-1", home,
                      result=PassResult.COMPLETE, qualifiers=[]),
                event(ShotEvent, "synthetic-shot-1", away,
                      result=ShotResult.OFF_TARGET, qualifiers=[]),
                # This is a real GenericEvent, which may carry a provider
                # event_name resembling a shot; must NOT count as a typed Shot.
                event(GenericEvent, "synthetic-generic-1", home,
                      event_name="shot", result=None, qualifiers=None),
            ],
            metadata=metadata,
        )
        self.manifest = {
            "schema": SCHEMA,
            "source_namespace": "synthetic_kloppy_native",
            "source_event_id": "synthetic-match-1",
            "rights_reference_url": "https://example.org/synthetic-test-only",
            "source_available_utc": "2026-10-01T00:00:00Z",
            "target_as_of_utc": "2026-10-02T00:00:00Z",
        }

    def test_native_package_version_is_pinned(self):
        self.assertEqual(version("kloppy"), "3.19.1")

    def test_native_installed_package_counts_only_typed_events(self):
        self.assertIsInstance(self.dataset, EventDataset)
        self.assertIsInstance(self.dataset.events[0], PassEvent)
        self.assertIsInstance(self.dataset.events[1], ShotEvent)
        self.assertIsInstance(self.dataset.events[2], GenericEvent)
        result = summarize_local_event_dataset(self.dataset, self.manifest)
        self.assertEqual(result["events_recorded"], 3)
        self.assertEqual(result["team_event_counts"]["synthetic-H"]["pass"], 1)
        self.assertEqual(result["team_event_counts"]["synthetic-H"]["shot"], 0)
        self.assertEqual(result["team_event_counts"]["synthetic-A"]["shot"], 1)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertIs(result["source_data_rights_independently_verified"], False)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertNotIn("p_home", result)


if __name__ == "__main__":
    unittest.main()
