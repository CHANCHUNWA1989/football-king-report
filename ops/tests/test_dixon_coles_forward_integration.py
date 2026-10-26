"""Capture a new research stream without editing existing forecast records."""
import copy
import gzip
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from archive_prepare import prepare
from model_ab import apply as add_b
from model_dixon_coles_forward import MODEL, TOP_KEY, publish
from shadow_forecast import poisson_1x2


NOW = datetime(2026, 10, 26, 10, tzinfo=timezone.utc)


def shadow_document():
    source = NOW - timedelta(minutes=5)
    p = poisson_1x2(1.2, .9)
    result = {
        "schema": "football-king-uncalibrated-shadow-1",
        "as_of_utc": source.isoformat(), "status": "SHADOW_ONLY",
        "predictions_count": 1, "production_recommendations": "DISABLED",
        "model_calibrated": False, "market_odds_available": False,
        "independently_verified_results": False,
        "sources": [{"league": "epl", "status": "RESEARCH_ONLY"}],
        "predictions": [{
            "league": "epl", "event_id": "source-event-123",
            "home": "Internal home identifier", "away": "Internal away identifier",
            "kickoff_utc": (NOW + timedelta(hours=2)).isoformat(),
            "prediction_utc": source.isoformat(),
            "model": "poisson-shrinkage-unvalidated-v4.1",
            "training_games": 50, "training_cutoff_local_day": "2026-10-25",
            "training_observations_sha256": "a" * 64,
            "p_home": p[0], "p_draw": p[1], "p_away": p[2],
            "expected_home_goals": 1.2, "expected_away_goals": .9,
            "calibrated": False, "verified_market_odds": False,
            "schedule_utc_source": "original_fixture_gateway",
            "production_recommendations": "DISABLED",
        }],
    }
    add_b(result)
    return result


class DixonColesForwardIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = shadow_document()
        self.path = self.root / "shadow.json"
        self.path.write_text(json.dumps(self.source, ensure_ascii=False) + "\n")

    def test_publisher_changes_only_new_stream_and_uses_actual_candidate_clock(self):
        original = copy.deepcopy(self.source)
        publish(self.root, now=NOW)
        updated = json.loads(self.path.read_text())
        candidate = updated.pop(TOP_KEY)
        self.assertEqual(updated, original)
        self.assertEqual(candidate["model_id"], MODEL)
        self.assertEqual(candidate["predictions_count"], 1)
        row = candidate["predictions"][0]
        self.assertEqual(row["prediction_utc"], NOW.isoformat())
        self.assertEqual(row["source_prediction_utc"], original["as_of_utc"])
        self.assertEqual(row["original"], [original["predictions"][0][k]
                                         for k in ("p_home", "p_draw", "p_away")])
        self.assertFalse(candidate["automatic_model_promotion"])
        self.assertEqual(candidate["production_recommendations"], "DISABLED")

    def test_existing_archive_keeps_candidate_inside_exact_shadow_bytes(self):
        publish(self.root, now=NOW)
        raw = self.path.read_bytes()
        for name in ("asof", "paired"):
            (self.root / (name + ".json")).write_text('{"production_recommendations":"DISABLED"}')
        destination = self.root / "destination"
        destination.mkdir()
        paths = prepare(self.root, destination, "123", "1", day="2026/10/26")
        shadow_path = next(p for p in paths if p.startswith("shadow/"))
        self.assertEqual(gzip.decompress((destination / shadow_path).read_bytes()), raw)
        self.assertEqual(prepare(self.root, destination, "123", "1", day="2026/10/26"), [])
        # Candidate bytes follow the existing full-shadow subject. This test
        # is serialization/archival evidence, never cryptographic verification.
        from forecast_provenance_audit import SUBJECT_NAMES
        from archive_forecast_provenance import FILES
        self.assertEqual(SUBJECT_NAMES, ("shadow.json", "paired.json", "slate.json"))
        self.assertEqual(len(FILES), 10)

    def test_second_publication_cannot_replace_an_earlier_candidate(self):
        publish(self.root, now=NOW)
        first = self.path.read_bytes()
        with self.assertRaises(ValueError):
            publish(self.root, now=NOW + timedelta(minutes=1))
        self.assertEqual(self.path.read_bytes(), first)


if __name__ == "__main__":
    unittest.main()
