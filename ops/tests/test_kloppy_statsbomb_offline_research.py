"""No-data, no-Kloppy tests of the historical StatsBomb offline source gate.

The *actual* upstream JSON and installed Kloppy 3.19.1 native loader were
separately exercised in an isolated external research sandbox.
"""
import hashlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from ops import kloppy_statsbomb_offline_research as adapter


class StatsBombVerifiedOfflineResearchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.events = self.root / "events.json"
        self.lineups = self.root / "lineups.json"

    def test_official_exact_match_identity_and_checksums_are_pinned(self):
        self.assertEqual(adapter.MATCH_ID, "3788741")
        self.assertEqual(adapter.UPSTREAM_REPO, "hudl/open-data")
        self.assertEqual(len(adapter.UPSTREAM_COMMIT), 40)
        self.assertEqual(adapter.EVENTS_BYTES, 3208593)
        self.assertEqual(adapter.LINEUPS_BYTES, 19491)
        self.assertEqual(len(adapter.EVENTS_SHA256), 64)
        self.assertEqual(len(adapter.LINEUPS_SHA256), 64)

    def test_small_synthetic_local_file_can_be_checked_without_kloppy(self):
        self.events.write_bytes(b"test")
        digest = hashlib.sha256(b"test").hexdigest()
        self.assertEqual(adapter._read_fixed_file(self.events, 4, digest), b"test")

    def test_modified_same_length_file_never_matches_expected_digest(self):
        self.events.write_bytes(b"test")
        with self.assertRaisesRegex(ValueError, "OFFICIAL_SAMPLE_SHA256_MISMATCH"):
            adapter._read_fixed_file(self.events, 4, hashlib.sha256(b"evil").hexdigest())

    def test_wrong_file_size_and_missing_file_are_rejected(self):
        self.events.write_bytes(b"test")
        with self.assertRaisesRegex(ValueError, "OFFICIAL_SAMPLE_SIZE_MISMATCH"):
            adapter._read_fixed_file(self.events, 5, hashlib.sha256(b"test").hexdigest())
        with self.assertRaisesRegex(ValueError, "SOURCE_MUST_BE_LOCAL_REGULAR_FILE"):
            adapter._read_fixed_file(self.lineups, 4, hashlib.sha256(b"test").hexdigest())

    def test_symlink_is_rejected_even_when_target_has_matching_bytes(self):
        self.events.write_bytes(b"test")
        self.lineups.symlink_to(self.events)
        with self.assertRaisesRegex(ValueError, "SOURCE_MUST_BE_LOCAL_REGULAR_FILE"):
            adapter._read_fixed_file(self.lineups, 4, hashlib.sha256(b"test").hexdigest())

    def test_real_official_file_is_required_before_optional_package_import(self):
        self.events.write_bytes(b"wrong local bytes")
        self.lineups.write_bytes(b"wrong local bytes")
        with self.assertRaisesRegex(ValueError, "OFFICIAL_SAMPLE_SIZE_MISMATCH"):
            adapter.summarize_verified_statsbomb_open_data(self.events, self.lineups)
        self.assertNotIn("kloppy", sys.modules)

    def _fake_loader(self, native_id=None):
        from enum import Enum
        from types import SimpleNamespace as NS

        class EventType(Enum):
            PASS = "PASS"

        home, away = NS(team_id="909"), NS(team_id="914")
        record = NS(event_id="synthetic", event_name="pass", event_type=EventType.PASS, team=home)
        dataset = NS(metadata=NS(game_id=native_id, teams=[home, away]), events=[record])
        record.dataset = dataset
        events_arg = []

        def load(**kwargs):
            assert kwargs["event_data"].read() == b"fake-events"
            assert kwargs["lineup_data"].read() == b"fake-lineups"
            assert "additional_metadata" not in kwargs
            events_arg.append(kwargs)
            return dataset

        return dataset, load, events_arg

    def test_local_loader_preserves_record_parent_without_additional_metadata(self):
        dataset, load, args = self._fake_loader()
        module = types.ModuleType("kloppy")
        module.statsbomb = types.SimpleNamespace(load=load)
        with patch.object(adapter, "_read_fixed_file",
                          side_effect=[b"fake-events", b"fake-lineups"]):
            with patch.dict(sys.modules, {"kloppy": module}):
                result = adapter.summarize_verified_statsbomb_open_data(
                    self.events, self.lineups)
        self.assertEqual(dataset.metadata.game_id, adapter.MATCH_ID)
        self.assertIs(dataset.events[0].dataset, dataset)
        self.assertEqual(len(args), 1)
        self.assertEqual(result["data_use_scope"], "HISTORICAL_PUBLIC_RESEARCH_ONLY")
        self.assertFalse(result["commercial_data_rights_verified"])
        self.assertFalse(result["positive_ev_verified"])
        self.assertFalse(result["source_event_capture_independently_verified"])
        self.assertFalse(result["source_data_rights_independently_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_mismatched_original_native_match_id_is_rejected(self):
        _, load, _ = self._fake_loader(native_id="foreign-match")
        module = types.ModuleType("kloppy")
        module.statsbomb = types.SimpleNamespace(load=load)
        with patch.object(adapter, "_read_fixed_file",
                          side_effect=[b"fake-events", b"fake-lineups"]):
            with patch.dict(sys.modules, {"kloppy": module}):
                with self.assertRaisesRegex(ValueError, "MISMATCHED_NATIVE_MATCH_ID"):
                    adapter.summarize_verified_statsbomb_open_data(self.events, self.lineups)


if __name__ == "__main__":
    unittest.main()
