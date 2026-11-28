"""Regression of official club aliases, synthetic rows only."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from team_identity import alias_index, same_team, team_id


class SourceAliasTests(unittest.TestCase):
    def test_levante(self):
        self.assertTrue(same_team("laliga", "Levante", "Levante UD"))

    def test_racing(self):
        self.assertTrue(same_team("laliga", "Racing de Santander", "Real Racing Club de Santander"))

    def test_bologna(self):
        self.assertTrue(same_team("seriea", "Bologna", "Bologna FC 1909"))
        self.assertTrue(same_team("seriea", "Bologna FC", "Bologna FC 1909"))

    def test_scope(self):
        self.assertFalse(same_team("seriea", "Levante", "Levante UD"))
        self.assertFalse(same_team("epl", "Bologna", "Bologna FC 1909"))
        self.assertFalse(same_team("championship", "Racing de Santander", "Real Racing Club de Santander"))

    def test_negative_controls(self):
        for league, name, other in (
            ("laliga", "Levante", "Levante UD B"),
            ("laliga", "Levante", "Levante Women"),
            ("laliga", "Racing de Santander", "Racing Club"),
            ("laliga", "Racing de Santander", "Racing de Ferrol"),
            ("seriea", "Bologna", "Bologna U19"),
        ):
            with self.subTest(name=name, other=other):
                self.assertFalse(same_team(league, name, other))

    def test_no_collision(self):
        index = alias_index()
        self.assertIn("laliga", index)
        self.assertNotEqual(team_id("laliga", "Levante UD"), team_id("laliga", "Real Racing Club de Santander"))


if __name__ == "__main__":
    unittest.main()
