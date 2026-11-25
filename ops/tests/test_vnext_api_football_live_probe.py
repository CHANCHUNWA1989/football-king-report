import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vnext_api_football_live_probe import probe,summarize,URL

def sample():
    return {"errors":[],"response":[{"fixture":{"id":1,"status":{"short":"2H"}},
                                      "goals":{"home":1,"away":0}}]}
class ProbeTests(unittest.TestCase):
    def test_default_and_missing_key_no_calls(self):
        with patch("vnext_api_football_live_probe.fetch") as f:
            self.assertEqual(probe(key="test")["requests_attempted"],0)
            self.assertEqual(probe(key="",allow=True)["reason"],"NOT_CONFIGURED")
            f.assert_not_called()
    def test_single_call_and_no_certification(self):
        with patch("vnext_api_football_live_probe.fetch",return_value=(sample(),"OK")) as f:
            out=probe(key="synthetic",allow=True)
            f.assert_called_once_with("api_football",URL,{"x-apisports-key":"synthetic"},requester=None)
            self.assertEqual(out["claimed_live_score_rows"],1)
            self.assertEqual(out["status"],"HOLD")
            self.assertFalse(out["upstream_timestamp_verified"])
            self.assertFalse(out["positive_ev_verified"])
            self.assertNotIn("synthetic",str(out))
    def test_denied_and_rate_limit_no_retry(self):
        for status in ("KEY_REJECTED","PLAN_OR_LEAGUE_RESTRICTED","RATE_LIMITED"):
            with patch("vnext_api_football_live_probe.fetch",return_value=(None,status)) as f:
                self.assertEqual(probe(key="x",allow=True)["reason"],status)
                f.assert_called_once()
    def test_duplicates_and_bad_score(self):
        b=sample()
        b["response"]*=2
        with self.assertRaises(ValueError):
            summarize(b)
        b=sample()
        b["response"][0]["goals"]["home"]=True
        self.assertEqual(summarize(b),(1,0))
    def test_provider_errors(self):
        with self.assertRaises(ValueError):
            summarize({"errors":{"plan":"denied"},"response":[]})
