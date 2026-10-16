import unittest
from ops.offline_1x2_validation import evaluate_1x2

class TestOffline1X2(unittest.TestCase):
    def test_scores(self):
        r=evaluate_1x2([{"event_id":"match1",
             "probabilities":{"H":.7,"D":.2,"A":.1},"outcome":"H"}])
        self.assertEqual(r["sample_count"],1)
        self.assertAlmostEqual(r["brier"],.14)
        self.assertEqual(r["accuracy"],1)

    def test_invalid_probabilities_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_1x2([{"event_id":"match1",
                "probabilities":{"H":.7,"D":.2,"A":.2},"outcome":"H"}])

    def test_duplicate_event_rejected(self):
        row={"event_id":"match1","probabilities":{"H":.7,"D":.2,"A":.1},"outcome":"H"}
        with self.assertRaises(ValueError):
            evaluate_1x2([row,row])

if __name__=="__main__":
    unittest.main()
