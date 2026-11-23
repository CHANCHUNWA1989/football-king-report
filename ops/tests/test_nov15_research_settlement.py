import unittest
from ops.nov15_research_settlement import settle


class Nov15SettlementTests(unittest.TestCase):
    def s(self, selection, line, home, away):
        return settle(selection, line, home, away, True, True)

    def test_no_evidence_no_settlement(self):
        self.assertEqual(settle("HOME", "-1", 4, 0), "PENDING_EVIDENCE")
        self.assertEqual(settle("HOME", "-1", 4, 0, True, False), "PENDING_EVIDENCE")

    def test_original_seven_as_unverified_scenarios_only(self):
        # Prior assistant-reported scores are illustrative, NOT certified FT.
        cases = [
            ("HOME", "-1", 4, 0, "FULL_WIN"),
            ("AWAY_1X2", None, 1, 1, "FULL_LOSS"),
            ("AWAY", "-1", 0, 2, "FULL_WIN"),
            ("UNDER", "4", 7, 2, "FULL_LOSS"),
            ("HOME", "-0.75", 1, 1, "FULL_LOSS"),
            ("AWAY", "0.25", 4, 1, "FULL_LOSS"),
            ("HOME", "-1", 2, 1, "PUSH"),
        ]
        for selection, line, home, away, expected in cases:
            with self.subTest(selection=selection, line=line):
                self.assertEqual(self.s(selection, line, home, away), expected)

    def test_quarter_line_half_outcomes(self):
        self.assertEqual(self.s("HOME", "-0.75", 2, 1), "HALF_WIN")
        self.assertEqual(self.s("HOME", "-0.25", 1, 1), "HALF_LOSS")
        self.assertEqual(self.s("AWAY", "0.25", 1, 1), "HALF_WIN")
        self.assertEqual(self.s("UNDER", "3.75", 2, 2), "HALF_LOSS")
        self.assertEqual(self.s("UNDER", "4.25", 2, 2), "HALF_WIN")
        self.assertEqual(self.s("UNDER", "4", 2, 2), "PUSH")

    def test_invalid_data(self):
        for selection, line, home, away in [
            ("HOME", "-0.3", 1, 0),
            ("HOME", "NaN", 1, 0),
            ("HOME", "-1", -1, 0),
            ("HOME", "-1", 1.0, 0),
            ("UNDER", "-1", 1, 0),
        ]:
            with self.subTest(selection=selection, line=line):
                with self.assertRaises(ValueError):
                    self.s(selection, line, home, away)


if __name__ == "__main__":
    unittest.main()
