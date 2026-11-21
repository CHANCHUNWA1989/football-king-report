import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from ops.private_history_pinned import load_pinned
from ops.private_history_intake import SCHEMA


class PinnedHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "history.json"
        matches = []
        for i in range(30):
            matches.append({
                "source_namespace": "the_odds_api_v4",
                "event_id": "history-" + str(i), "league_id": "epl",
                "home_team_id": "Home", "away_team_id": "Away",
                "kickoff_utc": "2026-01-01T12:00:00+00:00",
                "result_recorded_utc": "2026-01-02T12:00:00+00:00",
                "home_goals": 2, "away_goals": 1
            })
        self.path.write_text(json.dumps({
            "schema": SCHEMA, "production_recommendations": "DISABLED",
            "source": "private_vetted_fixture_source", "matches": matches
        }))
        self.digest = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def test_valid_pinned_file(self):
        self.assertEqual(len(load_pinned(self.path, self.digest)), 30)

    def test_mismatched_digest(self):
        with self.assertRaises(ValueError):
            load_pinned(self.path, "0" * 64)

    def test_invalid_digest(self):
        with self.assertRaises(ValueError):
            load_pinned(self.path, "not-a-sha")

    def test_missing_file(self):
        with self.assertRaises(ValueError):
            load_pinned(self.path.with_name("missing.json"), self.digest)

    def test_symlink_rejected(self):
        link = self.path.with_name("linked.json")
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            load_pinned(link, self.digest)


if __name__ == "__main__":
    unittest.main()
