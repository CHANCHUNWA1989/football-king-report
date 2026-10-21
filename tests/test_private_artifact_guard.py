import json
import unittest
from ops.private_artifact_guard import sanitize

class ArtifactSafety(unittest.TestCase):
    def test_legacy_claims_cannot_certify_or_lower_required_samples(self):
        output = sanitize({}, {"grounded_progress": {
            "settled_cases_in_archive": 300,
            "independently_verified_result_cases": 300,
            "settled_cases_required": 1}})
        progress = output["evidence_progress"]
        self.assertEqual(progress["independently_verified_result_cases"], 0)
        self.assertEqual(progress["settled_cases_required"], 300)
        self.assertEqual(progress["result_rows_marked_independently_verified"], 300)
        self.assertEqual(output["production_recommendations"], "DISABLED")

    def test_explicit_unverified_claims_are_preserved_as_aggregate_only(self):
        output = sanitize({}, {"grounded_progress": {
            "settled_cases_in_archive": 9,
            "independently_verified_result_cases": 0,
            "result_rows_marked_independently_verified": 7,
            "fixture_id": "private-fixture"}})
        self.assertEqual(output["evidence_progress"]["result_rows_marked_independently_verified"], 7)
        self.assertEqual(output["evidence_progress"]["independently_verified_result_cases"], 0)
        self.assertNotIn("private-fixture", json.dumps(output))

    def test_explicit_claim_zero_is_not_replaced_by_legacy_verified_number(self):
        progress = sanitize({}, {"grounded_progress": {
            "independently_verified_result_cases": 300,
            "result_rows_marked_independently_verified": 0}})["evidence_progress"]
        self.assertEqual(progress["result_rows_marked_independently_verified"], 0)
        self.assertEqual(progress["independently_verified_result_cases"], 0)

    def test_untrusted_claim_count_types_and_bounds_are_not_normalized(self):
        for field in ("result_rows_marked_independently_verified", "independently_verified_result_cases"):
            for claim in (True, False, "7", 7.0, -1, 20001, None, {}):
                with self.subTest(field=field, claim=claim):
                    progress = sanitize({}, {"grounded_progress": {field: claim}})["evidence_progress"]
                    self.assertEqual(progress["result_rows_marked_independently_verified"], 0)
                    self.assertEqual(progress["independently_verified_result_cases"], 0)
                    self.assertEqual(progress["settled_cases_required"], 300)

    def test_empty_progress_keeps_full_certified_requirement(self):
        for ready in ({}, {"grounded_progress": {}}, {"grounded_progress": []}):
            with self.subTest(ready=ready):
                progress = sanitize({}, ready)["evidence_progress"]
                self.assertEqual(progress["result_rows_marked_independently_verified"], 0)
                self.assertEqual(progress["independently_verified_result_cases"], 0)
                self.assertEqual(progress["settled_cases_required"], 300)

    def test_no_raw_licensed_quotes_or_identity_can_escape(self):
        raw = {
            "input_status": "CONNECTED",
            "counts": {"RESEARCH_ONLY": 2, "VERIFIED_VALUE": 500},
            "coverage": [{"league": "epl", "quotes": 2,
                          "bookmaker": "secretbook", "decimal_odds": 2.35,
                          "home": "Secret Home", "away": "Secret Away"}],
            "requested_markets": ["h2h", "invalid", "spreads"],
            "candidates": [{"fixture_id": "private-fixture",
                            "source": "secretbook", "decimal_odds": 2.35,
                            "selection": "Secret Home"}]}
        ready = {"grounded_progress": {"settled_cases_in_archive": 1,
                                       "additional_settled_cases_needed": 299,
                                       "secret_raw_odds": "do not upload"}}
        output = sanitize(raw, ready)
        serialized = json.dumps(output)
        for secret in ("secretbook", "private-fixture", "Secret Home",
                       "Secret Away", "2.35", "decimal_odds", "secret_raw_odds"):
            self.assertNotIn(secret, serialized)
        self.assertEqual(output["counts"]["VERIFIED_VALUE"], 0)
        self.assertEqual(output["requested_markets"], ["h2h", "spreads"])
        self.assertEqual(output["production_recommendations"], "DISABLED")

if __name__ == "__main__":
    unittest.main()
