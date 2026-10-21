import unittest
from datetime import datetime, timezone, timedelta
from ops.asian_ev_quote_provenance import canonical_quote_digest, research_evidence_record


class ProvenanceTests(unittest.TestCase):
    def quote(self):
        return {"fixture_id": "fx-123", "market_id": "ah-home-minus-quarter",
                "source": "example-provider", "source_quote_id": "q-123",
                "observed_at_utc": datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc),
                "decimal_odds": 1.95}

    def test_deterministic_across_field_order(self):
        q = self.quote()
        self.assertEqual(canonical_quote_digest(q), canonical_quote_digest(dict(reversed(list(q.items())))))

    def test_tamper_changes_digest(self):
        q = self.quote()
        old = canonical_quote_digest(q)
        q["decimal_odds"] = 1.96
        self.assertNotEqual(old, canonical_quote_digest(q))

    def test_timezone_normalization(self):
        q = self.quote()
        old = canonical_quote_digest(q)
        q["observed_at_utc"] = q["observed_at_utc"].astimezone(timezone(timedelta(hours=8)))
        self.assertEqual(old, canonical_quote_digest(q))

    def test_missing_source_quote_id_rejected(self):
        q = self.quote()
        del q["source_quote_id"]
        with self.assertRaises(ValueError):
            canonical_quote_digest(q)

    def test_invalid_odds_rejected(self):
        q = self.quote()
        q["decimal_odds"] = float("nan")
        with self.assertRaises(ValueError):
            canonical_quote_digest(q)

    def test_recommendations_stay_disabled(self):
        self.assertEqual(research_evidence_record(self.quote())["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
