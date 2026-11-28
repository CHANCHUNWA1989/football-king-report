"""Real Git-checkout catalogue plus isolated negative controls."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import dixon_coles_capacity_preflight as preflight
import dixon_coles_capture_history as history
import prepare_forecast_proof as existing

ROOT=Path(__file__).resolve().parents[2]/"openliga_capture_provenance"
FAILED_RUN="46130358395"


class CapacityPreflightTests(unittest.TestCase):
    def test_historical_failure_catalogue(self):
        with patch.object(history,"_files",side_effect=AssertionError("no proof reads")), \
             patch.object(history,"_metadata",side_effect=AssertionError("no API calls")):
            r=preflight.inspect_capacity(ROOT,run_id=FAILED_RUN,attempt="1")
            self.assertEqual(r["historical_count"],32)
            self.assertEqual(r["historical_limit"],31)
            self.assertEqual(r["total_with_current"],33)
            self.assertEqual(r["excess"],1)
            self.assertEqual(r["reason"],"CAPTURE_HISTORY_COUNT_LIMIT")
            self.assertFalse(r["capacity_ok"])
            self.assertFalse(r["remote_history_completeness_verified"])
            self.assertEqual(r["certified_case_count"],0)
            self.assertEqual(r["production_recommendations"],"DISABLED")
            with self.assertRaisesRegex(existing.PreparationError,"CAPTURE_HISTORY_COUNT_LIMIT"):
                history.collect(ROOT,current_proof=ROOT.parent/"unopened-test-proof",
                                run_id=FAILED_RUN,attempt="1")

    def make(self,root,count):
        for i in range(count):
            (root/"2026"/"10"/"26"/(str(history.FIRST_RUN+i)+"-1")).mkdir(parents=True)

    def test_exact_limit_and_current_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.make(root,32)
            r=preflight.inspect_capacity(root,run_id=str(history.FIRST_RUN+31),attempt="1")
            self.assertEqual(r["historical_count"],31)
            self.assertTrue(r["capacity_ok"])
            self.assertEqual(r["status"],"HOLD")

    def test_over_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.make(root,32)
            r=preflight.inspect_capacity(root,run_id=str(history.FIRST_RUN+32),attempt="1")
            self.assertEqual(r["excess"],1)
            self.assertFalse(r["capacity_ok"])

    def test_missing_baseline_and_bad_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertEqual(preflight.inspect_capacity(root,run_id=FAILED_RUN,attempt="1")["reason"],
                             "CAPTURE_HISTORY_BASELINE_MISSING")
            self.assertFalse(preflight.inspect_capacity(root,run_id="PRIVATE_PAYLOAD",attempt="1")["catalogue_valid"])

    def test_cli_safe_failure(self):
        with patch("sys.stdout",new_callable=io.StringIO) as out:
            result=preflight.main(["--capture-archives",str(ROOT),"--run-id",FAILED_RUN,"--attempt","1"])
        self.assertEqual(result,1)
        self.assertEqual(json.loads(out.getvalue())["reason"],"CAPTURE_HISTORY_COUNT_LIMIT")
        self.assertNotIn(str(ROOT),out.getvalue())
