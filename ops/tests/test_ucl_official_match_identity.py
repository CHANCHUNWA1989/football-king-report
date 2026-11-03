"""Offline regression for official UEFA identifiers versus bookmaker event IDs."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ops"))
from ucl_official_match_identity import validate_official_links, PINNED
from ucl_md4_nine_fixture_coverage import audit

MANIFEST = json.loads((ROOT / "config/ucl_md4_2026_11_03_nine_fixtures.json")
                      .read_text(encoding="utf-8"))
EVIDENCE = json.loads((ROOT / "config/ucl_md4_2026_11_03_uefa_match_links.json")
                      .read_text(encoding="utf-8"))
NOW = "2026-11-03T11:00:00Z"


def domestic_market():
    """Realistic empty but valid no-odds public research snapshot."""
    return {
        "schema": "football-king-market-consensus-v1",
        "provider": "the-odds-api.com/v4",
        "as_of_utc": "2026-11-03T10:59:00Z",
        "status": "RESEARCH_ONLY",
        "production_recommendations": "DISABLED",
        "raw_bookmaker_quotes_redistributed": False,
        "raw_bookmaker_names_redistributed": False,
        "model_value_advantage_verified": False,
        "market": "h2h",
        "requested_markets": ["h2h"],
        "missing_markets": ["spreads", "totals"],
        "event_count": 0,
        "events": [],
    }


class OfficialMatchIdentityTest(unittest.TestCase):
    def test_all_nine_official_links_are_reconciled(self):
        out = validate_official_links(EVIDENCE, MANIFEST)
        self.assertEqual(len(out), 9)
        self.assertEqual(set(out), set(PINNED))
        self.assertEqual(len({x["uefa_match_id"] for x in out.values()}), 9)
        self.assertEqual(out["ucl26m4-atletico-bayern"]["uefa_match_id"], "2049608")
        self.assertEqual(out["ucl26m4-feyenoord-inter"]["uefa_match_id"], "2049610")

    def test_uefa_public_links_are_visible_but_never_bookmaker_ids(self):
        report = audit(MANIFEST, domestic_market(), now_utc=NOW,
                       uefa_evidence=EVIDENCE)
        self.assertEqual(report["uefa_official_match_links_reconciled"], 9)
        self.assertEqual(report["uefa_match_link_evidence_state"],
                         "REVIEWED_UEFA_LINKS_RECONCILED_OFFLINE")
        self.assertEqual(len(report["fixtures"]), 9)
        self.assertEqual(report["fixtures_with_verified_betting_quotes"], 0)
        self.assertEqual(report["fixtures_with_structurally_matched_public_h2h"], 0)
        self.assertFalse(report["source_fixture_ids_independently_authenticated"])
        self.assertTrue(all(row["uefa_official_match_id"] is not None
                            and row["uefa_official_match_url"].startswith(
                                "https://www.uefa.com/uefachampionsleague/match/")
                            and row["uefa_match_link_reviewed_offline"]
                            and not row["uefa_live_page_response_authenticated"]
                            and not row["provider_identity_independently_verified"]
                            and row["status"] == "HOLD"
                            for row in report["fixtures"]))
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertEqual(report["bets_authorized"], 0)

    def test_official_id_cannot_be_passed_as_odds_event_id(self):
        report = audit(MANIFEST, domestic_market(), now_utc=NOW,
                       uefa_evidence=EVIDENCE, bindings=[
                           {
                               "local_request_id": "ucl26m4-feyenoord-inter",
                               "source_event_id": "2049610",
                               "provider": "the-odds-api.com/v4",
                               "provider_sport_key": "soccer_uefa_champs_league",
                           },
                       ])
        selected = next(x for x in report["fixtures"]
                        if x["local_request_id"] == "ucl26m4-feyenoord-inter")
        self.assertIn("NATIVE_EVENT_NOT_FOUND_IN_UCL_SCOPE",
                      selected["blockers"])
        self.assertEqual(report["fixtures_with_verified_betting_quotes"], 0)
        self.assertFalse(selected["public_h2h_structural_observation"])

    def test_missing_evidence_has_zero_official_links(self):
        out = audit(MANIFEST, domestic_market(), now_utc=NOW)
        self.assertEqual(out["uefa_official_match_links_reconciled"], 0)
        self.assertTrue(all(x["uefa_official_match_id"] is None
                            for x in out["fixtures"]))

    def test_tampered_evidence_quarantines_all_nine_in_audit(self):
        mutations = (
            lambda x: x["links"][0].update(uefa_match_id="2049612"),
            lambda x: x["links"][0].update(uefa_match_url=(
                "https://faked-uefa.example/match/2049613")),
            lambda x: x["links"][0].update(official_page_title="Someone Else"),
            lambda x: x["links"][0].update(local_request_id="ucl26m4-feyenoord-inter"),
            lambda x: x["links"][0].update(uefa_match_id=2049613),
            lambda x: x["links"][0].update(uefa_match_id=True),
            lambda x: x["links"][0].update(uefa_match_id=[]),
            lambda x: x["links"][0].update(uefa_match_url=(
                x["links"][0]["uefa_match_url"] + "?foo=1")),
            lambda x: x.update(provider_bookmaker_ids_confirmed=True),
            lambda x: x.update(source_index_url="https://fake.example/"),
            lambda x: x.update(evidence_method="SELF_ASSERTED_BY_USER"),
            lambda x: x.update(observation_date_utc="2026-11-04"),
            lambda x: x.update(unexpected="external provider cert"),
            lambda x: x["links"][0].update(verified=True),
            lambda x: x["links"].pop(),
        )
        for mutate in mutations:
            evidence = copy.deepcopy(EVIDENCE)
            mutate(evidence)
            with self.subTest(evidence=evidence.get("evidence_method")):
                with self.assertRaises(ValueError):
                    validate_official_links(evidence, MANIFEST)
                out = audit(MANIFEST, domestic_market(), now_utc=NOW,
                            uefa_evidence=evidence)
                self.assertEqual(out["uefa_match_link_evidence_state"],
                                 "INVALID_OR_CONFLICTING_OFFICIAL_LINK_EVIDENCE")
                self.assertEqual(out["uefa_official_match_links_reconciled"], 0)
                self.assertTrue(all(x["uefa_official_match_id"] is None
                                    for x in out["fixtures"]))
                self.assertEqual(out["bets_authorized"], 0)

    def test_manifest_identity_mutation_rejected_even_if_links_correct(self):
        manifest = copy.deepcopy(MANIFEST)
        manifest["fixtures"][2]["home"] = manifest["fixtures"][2]["away"]
        with self.assertRaises(ValueError):
            validate_official_links(EVIDENCE, manifest)

    def test_untrusted_or_oversized_evidence_blocks_fail_closed(self):
        for payload in (None, {}, [], {"links": []}, "not-evidence",
                        {**EVIDENCE, "links": EVIDENCE["links"] * 12}):
            with self.subTest(type=str(type(payload))):
                with self.assertRaises(ValueError):
                    validate_official_links(payload, MANIFEST)

    def test_no_bookmaker_prices_secrets_or_accuracy_claims(self):
        out = audit(MANIFEST, domestic_market(), now_utc=NOW,
                    uefa_evidence=EVIDENCE)
        text = json.dumps(out, ensure_ascii=False)
        self.assertIn("2049610", text)  # Public UEFA page ID may be published.
        for forbidden in ("raw_bookmaker_price", "PRIVATE_TEST_BOOK",
                          "PRIVATE_PROVIDER_FIXTURE_ID", "ROI_CERTIFIED"):
            self.assertNotIn(forbidden, text)
        self.assertFalse(out["calibrated_prediction_probabilities_verified"])
        self.assertFalse(out["asian_handicap_quotes_authenticated"])
        self.assertFalse(out["corners_quotes_authenticated"])
        self.assertFalse(out["first_half_goals_quotes_authenticated"])


if __name__ == "__main__":
    unittest.main()
