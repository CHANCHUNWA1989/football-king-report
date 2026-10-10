"""Guard six-league research history against raw-quote or mutable replays."""
import unittest
from pathlib import Path

FLOW=Path(__file__).resolve().parents[2] / ".github/workflows/football-king-six-free-upgrade.yml"

class SixLeagueQualityArchivePolicy(unittest.TestCase):
    def setUp(self):
        self.script=FLOW.read_text(encoding="utf-8")

    def test_history_uses_run_and_attempt_and_gzip(self):
        self.assertIn('sources/six_league_quality_history/$day/$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT/',self.script)
        self.assertIn('gzip -n -c "quality/$filename.json"',self.script)

    def test_only_three_sanitized_public_research_reports_archived(self):
        self.assertEqual(self.script.count('for filename in six-free seven-gates fixture-overlap; do'),2)
        self.assertIn('sources/six_league_fixture_overlap_latest.json',self.script)
        self.assertNotIn('raw-odds',self.script.lower())

    def test_history_cannot_be_overwritten_with_a_sha(self):
        start=self.script.index('# Preserve immutable sanitized as-of evidence')
        stop=self.script.index('for filename in six-free seven-gates fixture-overlap; do',start+90)
        # Check the historical branch exits if it already exists.
        history=self.script[start:stop]
        self.assertIn('Immutable quality-history snapshot exists',history)
        self.assertIn('continue',history)
        self.assertNotIn('-f sha=',history)

    def test_production_still_closed(self):
        self.assertIn("assert o['can_promote_model'] is False",self.script)
        self.assertIn("assert c['original_bookmaker_quotes_stored'] is False",self.script)

if __name__=="__main__":
    unittest.main()
