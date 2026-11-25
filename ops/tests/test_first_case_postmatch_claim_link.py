import hashlib
import json
import unittest
from ops.first_case_postmatch_claim_link import audit, RESULT_SCHEMA
from ops.tests.test_first_case_payload_binding import bundle, encoded


def claims(manifest):
    base = {"schema": RESULT_SCHEMA, "fixture_id": "synthetic-bundesliga-001",
            "league": "bundesliga", "home_key": "club-a", "away_key": "club-b",
            "kickoff_utc": "2026-11-21T12:00:00Z",
            "actual_kickoff_utc": "2026-11-21T12:00:00Z",
            "finished_utc": "2026-11-21T13:55:00Z",
            "observed_utc": "2026-11-21T14:00:00Z",
            "provider": "provider-a", "upstream_origin": "origin-a",
            "native_event_id": "a-123", "score_scope": "FT90",
            "home_goals": 2, "away_goals": 1,
            "prematch_manifest_sha256": hashlib.sha256(manifest).hexdigest(),
            "production_recommendations": "DISABLED"}
    return base, base | {"provider":"provider-b","upstream_origin":"origin-b",
                         "native_event_id":"b-456"}


class PostmatchClaimLinkTests(unittest.TestCase):
    def setUp(self):
        self.pre = bundle()
        self.a, self.b = claims(self.pre[2])

    def check(self, a=None, b=None, pre=None, cutoff="2026-11-21T15:00:00Z"):
        return audit(*(self.pre if pre is None else pre),
                     encoded(self.a if a is None else a),
                     encoded(self.b if b is None else b), as_of_utc=cutoff)

    def test_consistent_claims_never_certified(self):
        r = self.check()
        self.assertTrue(r["claim_chain_consistent"])
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["certified_forward_case_count"], 0)
        self.assertFalse(r["eligible_for_model_scoring"])
        self.assertFalse(r["external_timestamp_verified"])
        self.assertFalse(r["source_origins_independently_verified"])
        self.assertNotIn("home_goals", r)
        self.assertEqual(r, self.check(self.b,self.a))

    def test_rehashed_forecast_cannot_reuse_old_result_claims(self):
        f, q, m = self.pre
        new_f = f.replace(b"research-a",b"research-b")
        manifest = json.loads(m)
        manifest["forecast_sha256"] = hashlib.sha256(new_f).hexdigest()
        self.assertFalse(self.check(pre=(new_f,q,encoded(manifest)))["claim_chain_consistent"])

    def test_mismatched_scores_or_identity(self):
        for patch in ({"home_goals":3},{"fixture_id":"other"},{"away_key":"other"},
                      {"prematch_manifest_sha256":"0"*64},
                      {"actual_kickoff_utc":"2026-11-21T12:01:00Z"}):
            with self.subTest(patch=patch):
                self.assertFalse(self.check(b=self.b | patch)["claim_chain_consistent"])

    def test_same_source_and_scope(self):
        for patch in ({"provider":"PROVIDER-A"},{"upstream_origin":"ORIGIN-A"},
                      {"score_scope":"AET"},{"home_goals":True},{"certified":True}):
            with self.subTest(patch=patch):
                self.assertFalse(self.check(b=self.b | patch)["claim_chain_consistent"])

    def test_premature_result_and_future_observation(self):
        for patch in ({"finished_utc":"2026-11-21T13:29:59Z"},
                      {"observed_utc":"2026-11-21T15:01:00Z"},
                      {"observed_utc":"2026-11-21T13:54:59Z"}):
            with self.subTest(patch=patch):
                self.assertFalse(self.check(b=self.b | patch)["claim_chain_consistent"])

    def test_tampered_prematch_and_duplicate_json(self):
        f,q,m = self.pre
        self.assertFalse(self.check(pre=(f,q.replace(b"1.943",b"1.944"),m))["claim_chain_consistent"])
        raw = encoded(self.a).rstrip()[:-1] + b',"provider":"duplicate"}'
        out = audit(f,q,m,raw,encoded(self.b),as_of_utc="2026-11-21T15:00:00Z")
        self.assertFalse(out["claim_chain_consistent"])


if __name__ == "__main__":
    unittest.main()
