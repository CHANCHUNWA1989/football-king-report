import json
import unittest
from intelligence_x_domain_adapter import football_summary
from shared.intelligence_x_contract import validate_summary


class FootballDomainAdapterTests(unittest.TestCase):
    def test_p5_summary_isolated(self):
        url = "https://club.example/news"
        raw = json.dumps({"success": True, "data": {"markdown": "Synthetic",
                         "metadata": {"sourceURL": url, "url": url, "statusCode": 200}}}).encode()
        row = dict(raw=raw, requested_url=url, collected_at="2026-11-24T09:59:00Z", http_status=200)
        out = football_summary([row, row, {}], reviewed_urls={url},
                               now_utc="2026-11-24T10:00:00Z")
        self.assertEqual((out["total"], out["candidates"], out["rejected"]), (3, 1, 2))
        self.assertEqual(validate_summary(out, expected_domain="football"), out)
        self.assertNotIn(url, json.dumps(out))
        with self.assertRaises(ValueError):
            validate_summary(out, expected_domain="finance")


if __name__ == "__main__":
    unittest.main()
