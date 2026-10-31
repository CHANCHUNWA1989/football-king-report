import unittest
from research.asian_settlement import settle_asian

class SettlementTests(unittest.TestCase):
    def check(self, market, selection, line, h, a, expected):
        self.assertEqual(settle_asian(market=market, selection=selection, line=line,
            home_goals=h, away_goals=a, final=True).status, expected)

    def test_original_seal(self):
        self.check("asian_handicap", "away", 1, 0, 1, "FULL_WIN")
        self.check("asian_handicap", "away", 1, 2, 0, "FULL_LOSS")
        self.check("totals", "under", 4, 2, 2, "PUSH")
        self.check("asian_handicap", "away", 1.5, 2, 1, "FULL_WIN")

    def test_quarter_lines(self):
        self.check("asian_handicap", "away", 0.75, 1, 0, "HALF_LOSS")
        self.check("asian_handicap", "away", 1.25, 1, 0, "HALF_WIN")
        self.check("totals", "under", 2.25, 1, 1, "HALF_WIN")
        self.check("totals", "under", 2.75, 2, 1, "HALF_LOSS")

    def test_unfinished_never_settles(self):
        r = settle_asian(market="totals", selection="under", line=2.5,
            home_goals=0, away_goals=0, final=False)
        self.assertEqual(r.status, "HOLD")

if __name__ == "__main__":
    unittest.main()
