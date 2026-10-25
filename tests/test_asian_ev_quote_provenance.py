import unittest
from datetime import datetime, timezone, timedelta
from ops.asian_ev_quote_provenance import canonical_quote_digest, research_evidence_record


class ProvenanceTests(unittest.TestCase):
    def quote(self):
        return {"fixture_id": "fx-123", "market_id": "ah-home-minus-quarter",
                "source": "example-provider", "source_quote_id": "q-123",
                "observed_at_utc": datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc),
                "decimal_odds": 1.95, "bookmaker_id": "test-bookmaker",
                "market_type": "spreads", "selection": "HOME", "line": -0.25,
                "bookmaker_updated_at_utc": datetime(2026, 10, 21, 9, 59, tzinfo=timezone.utc),
                "kickoff_utc": datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)}

    def test_each_semantic_field_is_bound(self):
        q = self.quote()
        old = canonical_quote_digest(q)
        changes = {"fixture_id": "other", "market_id": "other", "source": "other",
                   "source_quote_id": "other", "bookmaker_id": "other", "line": -0.75,
                   "selection": "AWAY", "decimal_odds": 2.0,
                   "market_type": "totals",
                   "bookmaker_updated_at_utc": q["bookmaker_updated_at_utc"] - timedelta(seconds=1),
                   "observed_at_utc": q["observed_at_utc"] + timedelta(seconds=1),
                   "kickoff_utc": q["kickoff_utc"] + timedelta(seconds=1)}
        # A market type substitution must include a valid selection and line.
        for key, value in changes.items():
            with self.subTest(field=key):
                changed = dict(q, **{key: value})
                if key == "market_type":
                    changed.update(selection="OVER", line=2.5)
                self.assertNotEqual(old, canonical_quote_digest(changed))

    def test_incomplete_or_unknown_fields_rejected(self):
        for key in self.quote():
            with self.subTest(missing=key):
                q = self.quote()
                del q[key]
                with self.assertRaises(ValueError):
                    canonical_quote_digest(q)
        with self.assertRaises(ValueError):
            canonical_quote_digest(dict(self.quote(), unbound_metadata="must not silently disappear"))

    def test_market_contract_rejected(self):
        for changes in ({"line": True}, {"line": float("nan")}, {"line": float("inf")},
                        {"line": 0.3}, {"selection": "DRAW"}, {"market_type": "unknown"},
                        {"bookmaker_id": " "}, {"market_type": "totals", "selection": "OVER", "line": -1},
                        {"market_type": "h2h", "line": 0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                canonical_quote_digest(dict(self.quote(), **changes))

    def test_time_order_and_naive_times_rejected(self):
        q = self.quote()
        for changes in ({"bookmaker_updated_at_utc": q["observed_at_utc"] + timedelta(seconds=1)},
                        {"observed_at_utc": q["kickoff_utc"]},
                        {"kickoff_utc": q["observed_at_utc"]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                canonical_quote_digest(dict(q, **changes))
        for key in ("bookmaker_updated_at_utc", "observed_at_utc", "kickoff_utc"):
            with self.subTest(field=key), self.assertRaises(ValueError):
                canonical_quote_digest(dict(q, **{key: q[key].replace(tzinfo=None)}))

    def test_all_markets_and_utc_canonicalization(self):
        for market, selection, line in (("h2h", "DRAW", None), ("spreads", "AWAY", 0.25),
                                        ("totals", "UNDER", 2.75)):
            q = dict(self.quote(), market_type=market, selection=selection, line=line)
            original = dict(q)
            old = canonical_quote_digest(q)
            for key in ("bookmaker_updated_at_utc", "observed_at_utc", "kickoff_utc"):
                q[key] = q[key].astimezone(timezone(timedelta(hours=8)))
            self.assertEqual(old, canonical_quote_digest(q))
            self.assertEqual(q, original)

    def test_record_has_explicit_v2_research_scope(self):
        record = research_evidence_record(self.quote())
        self.assertEqual(record["schema"], "football-king-quote-evidence-v2")
        self.assertIs(record["independently_verified"], False)

    def test_extreme_numbers_and_utc_overflow_are_rejected_consistently(self):
        for changes in ({"line": 10**400}, {"decimal_odds": 10**400},
                        {"line": 1e308},
                        {"bookmaker_updated_at_utc": datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=14)))}):
            with self.subTest(field=next(iter(changes))), self.assertRaises(ValueError):
                canonical_quote_digest(dict(self.quote(), **changes))

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
