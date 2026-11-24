import unittest
from ops.cross_league_bridge_coverage import audit_bridges


def match(i, a="A", b="B", neutral=False):
    h, v = f"{a}:club{i%3}", f"{b}:club{i%3}"
    return {"fixture_id": f"match{i}", "source_namespace": "synthetic",
            "home_team_id": h, "away_team_id": v, "home_league_id": a,
            "away_league_id": b, "kickoff_utc": f"2025-01-{i+1:02d}T10:00:00Z",
            "result_observed_utc": f"2025-01-{i+1:02d}T12:00:00Z",
            "home_goals": 1, "away_goals": 0,
            "venue": "NEUTRAL" if neutral else "HOME",
            "competition_kind": "INTERNATIONAL_CLUB" if a != b else "DOMESTIC",
            "score_scope": "FT90"}


class CrossLeagueBridgeTests(unittest.TestCase):
    def audit(self, rows):
        return audit_bridges(rows, league_a="A", league_b="B",
                             as_of_utc="2025-02-01T00:00:00Z")

    def test_unconnected(self):
        self.assertEqual(self.audit([match(0, "A", "A") | {"away_team_id": "A:other"}])["reason"],
                         "UNCONNECTED_LEAGUES")

    def test_indirect_only(self):
        r = self.audit([match(0, "A", "C"), match(1, "C", "B")])
        self.assertTrue(r["claimed_connected"])
        self.assertEqual(r["direct_bridge_matches"], 0)
        self.assertFalse(r["research_coverage_threshold_met"])

    def test_balanced_coverage_never_authorizes(self):
        rows = [match(i, "A", "B") if i%2 else match(i, "B", "A")
                for i in range(12)]
        r = self.audit(rows)
        self.assertTrue(r["research_coverage_threshold_met"])
        self.assertEqual(r["direct_bridge_matches"], 12)
        self.assertEqual(r["distinct_clubs_by_league"], {"A":3,"B":3})
        self.assertEqual(r["status"], "HOLD")
        self.assertIsNone(r["strength_multiplier"])
        self.assertEqual(r["certified_prospective_samples"], 0)

    def test_neutral_not_home(self):
        r = self.audit([match(i, neutral=True) for i in range(12)])
        self.assertFalse(r["research_coverage_threshold_met"])
        self.assertEqual(r["venue_counts"]["NEUTRAL"], 12)

    def test_duplicate_and_mixed_source(self):
        a = match(0)
        for b in (a.copy(), a | {"fixture_id":"renamed"},
                  match(1) | {"source_namespace":"other"}):
            with self.subTest(b=b), self.assertRaises(ValueError):
                self.audit([a,b])

    def test_future_and_nonregulation_rejected(self):
        for patch in ({"result_observed_utc":"2025-02-01T00:00:00Z"},
                      {"score_scope":"AET"}, {"home_goals":True},
                      {"venue":"UNKNOWN"}, {"competition_kind":"DOMESTIC"}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.audit([match(0) | patch])

    def test_reversed_result_time(self):
        with self.assertRaisesRegex(ValueError,"RESULT_TIME_LEAKAGE"):
            self.audit([match(0) | {"result_observed_utc":"2025-01-01T09:00:00Z"}])


if __name__ == "__main__":
    unittest.main()
