import unittest
from tempfile import NamedTemporaryFile
from unified_prediction_ledger import validate_prediction, settle_prediction, record_prediction

BASE = dict(prediction_id="test-1", system="football", event_id="match-1", created_at="2026-10-17T10:00:00+08:00", model_version="v1", market="1X2", selection="home", probability=.6, odds=2.0, status="RESEARCH_ONLY")
class LedgerTests(unittest.TestCase):
    def test_valid(self): self.assertTrue(validate_prediction(BASE))
    def test_nan_rejected(self):
        with self.assertRaises(ValueError): validate_prediction(dict(BASE, probability=float("nan")))
    def test_no_live(self):
        with self.assertRaises(ValueError): validate_prediction(dict(BASE, status="LIVE"))
    def test_no_lookahead(self):
        with self.assertRaises(ValueError): settle_prediction(BASE, 1, "2026-10-17T09:00:00+08:00")
    def test_settlement(self): self.assertAlmostEqual(settle_prediction(BASE, 1, "2026-10-17T11:00:00+08:00")["brier"], .16)
    def test_record(self):
        with NamedTemporaryFile(mode="w+", encoding="utf-8") as f:
            record_prediction(f.name, BASE)
            self.assertIn("test-1", open(f.name, encoding="utf-8").read())
if __name__ == "__main__": unittest.main()
