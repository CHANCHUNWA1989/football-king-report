"""Synthetic tests for the ephemeral private cohort orchestration."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from live_core_statsbomb_private_pipeline import execute

class PrivatePipelineTests(unittest.TestCase):
    def test_no_rights_no_network(self):
        with tempfile.TemporaryDirectory() as d,patch("live_core_statsbomb_private_pipeline.acquire") as a:
            with self.assertRaises(ValueError):execute(Path(d),rights_confirmed=False)
            a.assert_not_called()

    def test_full_private_result_never_returned_and_temp_removed(self):
        with tempfile.TemporaryDirectory() as d,patch("live_core_statsbomb_private_pipeline.acquire",return_value={"downloaded":64,"index_verified":True,"byte_identity_verified":True}),patch("live_core_statsbomb_private_pipeline.run",return_value={"scheduled":64,"accepted":64,"complete_cohort":True,"rejected_match_ids":[],"private_match_research":[{"sensitive":"never print"}]}):
            result=execute(Path(d),rights_confirmed=True)
            self.assertEqual(result,{"status":"PRIVATE_REPLAY_FINISHED","production_recommendations":"DISABLED","model_calibrated":False,"verified_forward_sample_credit":0})
            self.assertEqual(list(Path(d).iterdir()),[])

    def test_failed_download_never_replays_and_cleans(self):
        with tempfile.TemporaryDirectory() as d,patch("live_core_statsbomb_private_pipeline.acquire",side_effect=ValueError("raw secret")),patch("live_core_statsbomb_private_pipeline.run") as r:
            with self.assertRaisesRegex(ValueError,"PRIVATE_ACQUISITION_FAILED"):
                execute(Path(d),rights_confirmed=True)
            r.assert_not_called()
            self.assertEqual(list(Path(d).iterdir()),[])

    def test_incomplete_or_inconsistent_replay_not_success(self):
        for accepted,complete in ((63,False),(65,True),(True,True)):
            with tempfile.TemporaryDirectory() as d,patch("live_core_statsbomb_private_pipeline.acquire",return_value={"downloaded":64,"index_verified":True,"byte_identity_verified":True}),patch("live_core_statsbomb_private_pipeline.run",return_value={"scheduled":64,"accepted":accepted,"complete_cohort":complete,"rejected_match_ids":[1]}):
                with self.assertRaisesRegex(ValueError,"PRIVATE_REPLAY_INCOMPLETE"):
                    execute(Path(d),rights_confirmed=True)
                self.assertEqual(list(Path(d).iterdir()),[])
