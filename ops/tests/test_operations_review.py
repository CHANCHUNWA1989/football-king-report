import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone
from ops.operations_review import build,publish

NOW=datetime(2026,11,26,11,tzinfo=timezone.utc)
def doc(**kwargs):return {"production_recommendations":"DISABLED",**kwargs}
class OperationsReviewTests(unittest.TestCase):
    def test_missing_unknown_not_zero(self):
        r=build({},now=NOW)
        self.assertIsNone(r["counts"]["recorded_settled_research"])
        self.assertEqual(r["authenticated_forward_samples"],0)
        self.assertEqual(r["status"],"HOLD")
    def test_real_zero_separate_from_unknown_and_stale(self):
        r=build({"market_status":doc(matched_count=0,market_as_of_utc="2026-11-24T11:00:00Z")},now=NOW)
        self.assertEqual(r["counts"]["time_valid_market_pairs"],0)
        self.assertEqual(r["market_age_hours"],48)
        self.assertIn("MARKET_CLOCK_STALE_OR_FUTURE",[a["code"] for a in r["alerts"]])
    def test_mismatch_and_unsafe(self):
        r=build({"production_gate":doc(status="HOLD",model_promoted=False,settled_samples=2),
                 "forward_daily_scorecard":doc(settled_observations=3),
                 "quality":{"production_recommendations":"ENABLED","public_matches":99}},now=NOW)
        self.assertIsNone(r["counts"]["public_window_observations"])
        self.assertIn("SETTLED_REPORT_COUNT_MISMATCH",[a["code"] for a in r["alerts"]])
        self.assertFalse(r["automatic_bets"])
    def test_safe_publication_and_idempotent_nav(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root);(p/"index.html").write_text("<html><body></body></html>")
            (p/"quality.json").write_text(json.dumps(doc(public_matches=2,secret="<script>bad</script>")))
            publish(p,now=NOW);publish(p,now=NOW)
            self.assertEqual((p/"index.html").read_text().count('id="operations-review-nav"'),1)
            self.assertNotIn("<script>bad</script>",(p/"operations-review.html").read_text())
            self.assertEqual(json.loads((p/"operations_review.json").read_text())["status"],"HOLD")
if __name__=="__main__":unittest.main()
