import copy
import hashlib
import unittest
from intelligence_x_claim_corroboration import compare


class ClaimCorroborationTests(unittest.TestCase):
    def setUp(self):
        self.a = "https://a.example/news"
        self.b = "https://b.example/news"
        self.registry = {self.a: {"publisher_group": "a", "origin_group": "a"},
                         self.b: {"publisher_group": "b", "origin_group": "b"}}
        self.key = dict(fixture_id="match-1", subject_id="player-1",
                        claim_id="injury-1", kind="injury")
        self.rows = [dict(self.key, source_url=url, value="OUT",
                          payload_sha256=hashlib.sha256(url.encode()).hexdigest(),
                          excerpt_sha256=hashlib.sha256((url+"excerpt").encode()).hexdigest(),
                          collected_at="2026-11-24T09:59:00Z",
                          upstream_observed_at="2026-11-24T09:58:00Z")
                     for url in (self.a, self.b)]

    def run_compare(self, rows=None, registry=None):
        return compare(self.rows if rows is None else rows,
                       registry=self.registry if registry is None else registry,
                       now_utc="2026-11-24T10:00:00Z", **self.key)

    def test_agreement_never_promotes(self):
        self.rows[0].update(independently_verified=True, source_authorized=True,
                            eligible_for_model_scoring=True, status="PASS")
        out = self.run_compare()
        self.assertEqual(out["diagnostic"], "AGREEMENT_CANDIDATE")
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(out["production_recommendations"], "DISABLED")
        for flag in ("independently_verified", "source_authorized", "eligible_for_model_scoring"):
            self.assertIs(out[flag], False)

    def test_single_or_empty_source(self):
        for rows in ([], self.rows[:1]):
            self.assertIn("INSUFFICIENT_SOURCES", self.run_compare(rows)["reasons"])

    def test_duplicate_source(self):
        self.assertIn("DUPLICATE_SOURCE", self.run_compare(self.rows + self.rows[:1])["reasons"])

    def test_shared_publisher_and_origin(self):
        for field, reason in (("publisher_group", "SHARED_PUBLISHER_GROUP"),
                              ("origin_group", "SHARED_ORIGIN_GROUP")):
            cfg = copy.deepcopy(self.registry)
            cfg[self.b][field] = cfg[self.a][field]
            self.assertIn(reason, self.run_compare(registry=cfg)["reasons"])

    def test_duplicate_payload_or_excerpt(self):
        for field, reason in (("payload_sha256", "DUPLICATE_PAYLOAD"),
                              ("excerpt_sha256", "DUPLICATE_EXCERPT")):
            rows = copy.deepcopy(self.rows)
            rows[1][field] = rows[0][field]
            self.assertIn(reason, self.run_compare(rows)["reasons"])

    def test_contradictory_claim(self):
        self.rows[1]["value"] = "AVAILABLE"
        self.assertIn("CONFLICTING_CLAIMS", self.run_compare()["reasons"])

    def test_identity_mismatch(self):
        for field in self.key:
            rows = copy.deepcopy(self.rows)
            rows[1][field] = "other"
            with self.assertRaisesRegex(ValueError, "CLAIM_IDENTITY"):
                self.run_compare(rows)

    def test_unregistered_url(self):
        self.rows[1]["source_url"] = "https://c.example/news"
        with self.assertRaisesRegex(ValueError, "UNKNOWN_SOURCE"):
            self.run_compare()

    def test_no_upstream_clock(self):
        self.rows[1]["upstream_observed_at"] = None
        self.assertIn("UPSTREAM_CLOCK_MISSING", self.run_compare()["reasons"])

    def test_stale_or_future_clock(self):
        for field, reason in (("collected_at", "COLLECTION_CLOCK_OUT_OF_RANGE"),
                              ("upstream_observed_at", "UPSTREAM_CLOCK_OUT_OF_RANGE")):
            for time in ("2026-11-24T08:00:00Z", "2026-11-24T11:00:00Z"):
                rows = copy.deepcopy(self.rows)
                rows[1][field] = time
                self.assertIn(reason, self.run_compare(rows)["reasons"])

    def test_invalid_value_or_digest(self):
        for field, value in (("value", "YES"), ("payload_sha256", "x"),
                             ("excerpt_sha256", None)):
            rows = copy.deepcopy(self.rows)
            rows[1][field] = value
            with self.assertRaises(ValueError):
                self.run_compare(rows)

    def test_batch_bound(self):
        with self.assertRaisesRegex(ValueError, "INVALID_BATCH"):
            self.run_compare(self.rows * 51)

    def test_order_invariance(self):
        self.assertEqual(self.run_compare(), self.run_compare(list(reversed(self.rows))))

    def test_other_supported_types(self):
        for kind, value in (("lineup", "STARTER"), ("red_card", "CONFIRMED"),
                            ("club_notice", "ISSUED")):
            self.key["kind"] = kind
            rows = [dict(row, kind=kind, value=value) for row in self.rows]
            self.assertEqual(self.run_compare(rows)["diagnostic"], "AGREEMENT_CANDIDATE")


if __name__ == "__main__":
    unittest.main()
