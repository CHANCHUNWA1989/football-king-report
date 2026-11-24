import unittest
from intelligence_x_live_evidence import audit_live


class LiveEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.registry = {
            "one": dict(publisher_group="p1", origin_group="o1", provider_fixture_id="111"),
            "two": dict(publisher_group="p2", origin_group="o2", provider_fixture_id="222"),
        }
        self.a = dict(source="one", fixture_id="match-A", provider_fixture_id="111",
                      phase="SECOND_HALF", home_score=1, away_score=0, home_red_cards=0,
                      away_red_cards=1, updated_at="2026-11-24T13:49:00Z",
                      observed_at="2026-11-24T13:49:20Z", payload_sha256="a"*64)
        self.b = dict(self.a, source="two", provider_fixture_id="222", payload_sha256="b"*64)

    def run_audit(self, rows):
        return audit_live(rows, fixture_id="match-A", registry=self.registry,
                          now_utc="2026-11-24T13:50:00Z")

    def blocked(self, rows, reason):
        out = self.run_audit(rows)
        self.assertEqual(out["diagnostic"], "BLOCKED")
        self.assertIsNone(out["match_state"])
        self.assertIn(reason, out["reasons"])
        self.assertFalse(out["eligible_for_model_scoring"])

    def test_agreement_does_not_authorize(self):
        out = self.run_audit([self.a, self.b])
        self.assertEqual(out["diagnostic"], "AGREEMENT_CANDIDATE")
        self.assertEqual(out["match_state"]["away_red_cards"], 1)
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(out["production_recommendations"], "DISABLED")
        for k in ("source_authorized", "independently_verified", "eligible_for_model_scoring"):
            self.assertIs(out[k], False)

    def test_stale_or_future(self):
        for updated, observed in [("2026-11-24T13:47:59Z", self.b["observed_at"]),
                                  ("2026-11-24T13:50:01Z", "2026-11-24T13:50:01Z"),
                                  ("2026-11-24T13:49:30Z", self.b["observed_at"])]:
            self.blocked([self.a, dict(self.b, updated_at=updated, observed_at=observed)], "STALE_OR_FUTURE")

    def test_time_skew(self):
        self.blocked([dict(self.a, updated_at="2026-11-24T13:48:00Z"),
                      dict(self.b, updated_at="2026-11-24T13:49:15Z")], "TIME_SKEW")

    def test_unknown_source_and_fixture(self):
        self.blocked([self.a, dict(self.b, source="unknown")], "UNKNOWN_SOURCE")
        self.blocked([self.a, dict(self.b, provider_fixture_id="999")], "FIXTURE_MISMATCH")

    def test_duplicate_source_and_payload(self):
        self.blocked([self.a, self.a], "DUPLICATE_SOURCE")
        self.blocked([self.a, dict(self.b, payload_sha256=self.a["payload_sha256"])], "DUPLICATE_PAYLOAD")

    def test_same_origin_and_publisher(self):
        for group in ("origin_group", "publisher_group"):
            old = self.registry["two"][group]
            self.registry["two"][group] = self.registry["one"][group]
            self.blocked([self.a, self.b], "SHARED_ORIGIN_OR_PUBLISHER")
            self.registry["two"][group] = old

    def test_state_conflicts(self):
        for key, value in [("away_score", 1), ("away_red_cards", 0), ("phase", "HALF_TIME")]:
            self.blocked([self.a, dict(self.b, **{key: value})], "CONFLICTING_MATCH_STATE")

    def test_missing_invalid_and_extra_fields(self):
        missing = dict(self.b)
        del missing["away_red_cards"]
        self.blocked([self.a, missing], "INVALID_FIELDS")
        self.blocked([self.a, dict(self.b, live_execution_allowed=True)], "INVALID_FIELDS")
        self.blocked([self.a, dict(self.b, home_red_cards=False)], "INVALID_MATCH_STATE")
        self.blocked([self.a, dict(self.b, payload_sha256="fake")], "INVALID_DIGEST")
        self.blocked([self.a, dict(self.b, updated_at="2026-11-24T13:49:00")], "INVALID_CLOCK")

    def test_single_source_and_invalid_registry(self):
        self.blocked([self.a], "INSUFFICIENT_SOURCES")
        self.registry["two"]["origin_group"] = "UNKNOWN"
        with self.assertRaisesRegex(ValueError, "INVALID_REGISTRY"):
            self.run_audit([self.a, self.b])

    def test_bounds_and_all_rows_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "INVALID_BATCH"):
            self.run_audit([self.a]*9)
        self.blocked([self.a, self.b, {}], "INVALID_FIELDS")


if __name__ == "__main__":
    unittest.main()
