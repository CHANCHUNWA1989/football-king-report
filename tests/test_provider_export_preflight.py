"""Fail-closed provider export preflight tests."""
import unittest
from copy import deepcopy
from ops.provider_export_preflight import validate_export

NOW="2026-10-21T10:00:00Z"
BASE={"source":"offline-provider","fixtures":[{"id":"f1","home":"A","away":"B",
    "kickoff_utc":"2026-10-21T12:00:00Z","quotes":[{
        "id":"q1","bookmaker":"book","market":"TOTALS","selection":"OVER",
        "line":2.5,"decimal_odds":1.9,"quote_utc":"2026-10-21T09:55:00Z"}]}]}

class ProviderExportPreflightTests(unittest.TestCase):
    def validate(self,payload):
        return validate_export(payload,generated_utc=NOW)

    def test_valid_export_not_claimed_authentic(self):
        result=self.validate(BASE)
        self.assertEqual(result["quote_count"],1)
        self.assertFalse(result["provider_authenticity_verified"])
        self.assertEqual(result["production_recommendations"],"HOLD")

    def test_duplicate_fixture_rejected(self):
        p=deepcopy(BASE);p["fixtures"].append(deepcopy(p["fixtures"][0]))
        with self.assertRaisesRegex(ValueError,"DUPLICATE_FIXTURE"):self.validate(p)

    def test_duplicate_quote_rejected(self):
        p=deepcopy(BASE);p["fixtures"][0]["quotes"].append(deepcopy(p["fixtures"][0]["quotes"][0]))
        with self.assertRaisesRegex(ValueError,"DUPLICATE_QUOTE_ID"):self.validate(p)

    def test_future_quote_rejected(self):
        p=deepcopy(BASE);p["fixtures"][0]["quotes"][0]["quote_utc"]="2026-10-21T10:01:00Z"
        with self.assertRaisesRegex(ValueError,"QUOTE_IN_FUTURE"):self.validate(p)

    def test_invalid_market_rejected(self):
        p=deepcopy(BASE);p["fixtures"][0]["quotes"][0]["market"]="1X2"
        with self.assertRaisesRegex(ValueError,"UNSUPPORTED_MARKET"):self.validate(p)

    def test_invalid_price_rejected(self):
        p=deepcopy(BASE);p["fixtures"][0]["quotes"][0]["decimal_odds"]=1
        with self.assertRaisesRegex(ValueError,"INVALID_ODDS_OR_LINE"):self.validate(p)

    def test_started_fixture_rejected(self):
        p=deepcopy(BASE);p["fixtures"][0]["kickoff_utc"]="2026-10-21T09:00:00Z"
        with self.assertRaisesRegex(ValueError,"FIXTURE_ALREADY_STARTED"):self.validate(p)

if __name__=="__main__":
    unittest.main()
