import unittest
from unittest.mock import Mock, patch
import consolidated_historical_replay as replay

class HistoricalReplayTests(unittest.TestCase):
    def test_each_season_fetched_once_and_never_promoted(self):
        fetch=Mock(side_effect=[b"train",b"test"])
        with patch.object(replay.low,"parse",return_value=[]), patch.object(replay.half,"parse",return_value=[]), patch.object(replay.low,"report",return_value={}), patch.object(replay.half,"report",return_value={}):
            result=replay.run(fetch)
        self.assertEqual(fetch.call_count,2)
        self.assertEqual(result["production_recommendations"],"DISABLED")
        self.assertEqual(result["verified_forward_sample_credit"],0)
    def test_bad_pins_fail_closed(self):
        with self.assertRaises(ValueError):
            replay.run(lambda season:b"bad")
