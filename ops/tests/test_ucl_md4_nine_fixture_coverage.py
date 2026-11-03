"""No-network nine-match Champions League coverage regression."""
import copy
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ops"))
from ucl_md4_nine_fixture_coverage import audit, validate_manifest

MANIFEST = json.loads((ROOT / "config/ucl_md4_2026_11_03_nine_fixtures.json")
                      .read_text(encoding="utf-8"))
NOW = "2026-11-03T11:00:00Z"
SPORT = "soccer_uefa_champs_league"


def public_snapshot():
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


def source_row(*, index=0, event_id="PRIVATE_NATIVE_ID_001"):
    fixture = MANIFEST["fixtures"][index]
    return {
        "source_event_id": event_id, "league": SPORT,
        "home": fixture["home"], "away": fixture["away"],
        "kickoff_utc": fixture["kickoff_utc"],
        "market_last_update_utc": "2026-11-03T10:58:45Z",
        "contributing_bookmakers": 3,
        "p_home": 0.43, "p_draw": 0.25, "p_away": 0.32,
        "probabilities_are_no_vig_consensus": True,
        "prediction_or_value_bet": False,
    }


def source_binding(index=0, event_id="PRIVATE_NATIVE_ID_001"):
    return {
        "local_request_id": MANIFEST["fixtures"][index]["local_request_id"],
        "source_event_id": event_id,
        "provider": "the-odds-api.com/v4",
        "provider_sport_key": SPORT,
    }


def with_event(snapshot, row):
    snapshot["events"] = [row]
    snapshot["event_count"] = 1
    return snapshot


class NineFixtureCoverageTests(unittest.TestCase):
    def test_manifest_is_exactly_nine_with_utc_two_early_seven_late(self):
        validated = validate_manifest(MANIFEST)
        self.assertEqual(len(validated), 9)
        self.assertEqual(sum(x["kickoff_utc"].endswith("17:45:00Z")
                             for x in validated), 2)
        self.assertEqual(sum(x["kickoff_utc"].endswith("20:00:00Z")
                             for x in validated), 7)
        self.assertFalse(MANIFEST["official_fixture_ids_available"])
        self.assertFalse(MANIFEST["local_ids_are_provider_ids"])

    def test_six_league_public_consensus_is_not_ucl(self):
        market = with_event(public_snapshot(), source_row())
        market["events"][0]["league"] = "epl"
        result = audit(MANIFEST, market, now_utc=NOW)
        self.assertEqual(result["fixtures_expected"], 9)
        self.assertEqual(result["observed_ucl_events_in_public_snapshot"], 0)
        self.assertEqual(result["fixtures_with_structurally_matched_public_h2h"], 0)
        self.assertEqual(result["status"], "HOLD")
        self.assertTrue(all("NO_UCL_EVENTS_IN_PUBLIC_SNAPSHOT" in f["blockers"]
                            for f in result["fixtures"]))

    def test_empty_market_is_nine_holds(self):
        out = audit(MANIFEST, public_snapshot(), now_utc=NOW)
        self.assertEqual(out["fixtures_expected"], 9)
        self.assertEqual(out["fixtures_with_verified_betting_quotes"], 0)
        self.assertTrue(all(row["status"] == "HOLD"
                            for row in out["fixtures"]))
        self.assertEqual(out["bets_authorized"], 0)
        self.assertEqual(out["production_recommendations"], "DISABLED")

    def test_requested_markets_are_never_observed_quotes(self):
        market = public_snapshot()
        market["requested_markets"] = ["h2h", "spreads", "totals"]
        out = audit(MANIFEST, market, now_utc=NOW)
        self.assertEqual(out["fixtures_with_verified_betting_quotes"], 0)
        self.assertFalse(out["asian_handicap_quotes_authenticated"])
        self.assertFalse(out["corners_quotes_authenticated"])
        self.assertEqual(out["status"], "HOLD")

    def test_matching_names_without_native_id_binding_not_counted(self):
        out = audit(MANIFEST, with_event(public_snapshot(), source_row()),
                    now_utc=NOW)
        self.assertEqual(out["observed_ucl_events_in_public_snapshot"], 1)
        self.assertEqual(out["fixtures_with_structurally_matched_public_h2h"], 0)
        self.assertIn("NO_PROVIDER_NATIVE_EVENT_BINDING",
                      out["fixtures"][0]["blockers"])

    def test_explicit_exact_native_id_join_is_structural_only(self):
        market = with_event(public_snapshot(), source_row())
        out = audit(MANIFEST, market,
                    bindings=[source_binding()], now_utc=NOW)
        self.assertEqual(out["fixtures_with_structurally_matched_public_h2h"], 1)
        self.assertTrue(out["fixtures"][0]["public_h2h_structural_observation"])
        self.assertFalse(out["fixtures"][0]["provider_identity_independently_verified"])
        self.assertEqual(out["fixtures_with_verified_betting_quotes"], 0)
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(out["bets_authorized"], 0)
        output = json.dumps(out)
        self.assertNotIn("PRIVATE_NATIVE_ID_001", output)
        self.assertNotIn("0.43", output)
        self.assertNotIn("0.25", output)

    def test_wrong_kickoff_is_rejected_not_rounded(self):
        row = source_row()
        row["kickoff_utc"] = "2026-11-03T17:46:00Z"
        out = audit(MANIFEST, with_event(public_snapshot(), row),
                    bindings=[source_binding()], now_utc=NOW)
        self.assertFalse(out["fixtures"][0]["public_h2h_structural_observation"])
        self.assertIn("NATIVE_EVENT_FIXTURE_KICKOFF_MISMATCH",
                      out["fixtures"][0]["blockers"])

    def test_swapped_home_away_does_not_join(self):
        row = source_row()
        row["home"], row["away"] = row["away"], row["home"]
        out = audit(MANIFEST, with_event(public_snapshot(), row),
                    bindings=[source_binding()], now_utc=NOW)
        self.assertIn("NATIVE_EVENT_FIXTURE_KICKOFF_MISMATCH",
                      out["fixtures"][0]["blockers"])

    def test_duplicate_event_id_in_public_snapshot_poison(self):
        market = public_snapshot()
        row = source_row()
        market["events"] = [row, dict(row)]
        market["event_count"] = 2
        out = audit(MANIFEST, market,
                    bindings=[source_binding()], now_utc=NOW)
        self.assertIn("DUPLICATE_PUBLIC_NATIVE_EVENT_ID",
                      out["fixtures"][0]["blockers"])
        self.assertEqual(out["fixtures_with_structurally_matched_public_h2h"], 0)

    def test_native_id_collision_across_leagues_is_quarantined(self):
        """Same upstream provider ID cannot certify both UCL and EPL events."""
        ucl = source_row(event_id="SHARED_NATIVE_EVENT_ID")
        domestic = dict(ucl)
        domestic.update(league="epl", home="Different Club",
                        away="Another Club")
        market = public_snapshot()
        market["events"] = [ucl, domestic]
        market["event_count"] = 2
        out = audit(MANIFEST, market,
                    bindings=[source_binding(event_id="SHARED_NATIVE_EVENT_ID")],
                    now_utc=NOW)
        self.assertEqual(out["fixtures_with_structurally_matched_public_h2h"], 0)
        self.assertFalse(out["fixtures"][0]["public_h2h_structural_observation"])
        self.assertIn("DUPLICATE_PUBLIC_NATIVE_EVENT_ID",
                      out["fixtures"][0]["blockers"])
        self.assertEqual(out["bets_authorized"], 0)

    def test_distinct_domestic_native_id_does_not_poison_ucl(self):
        ucl = source_row(event_id="UCL_NATIVE_EVENT_ID")
        domestic = dict(ucl)
        domestic.update(source_event_id="EPL_NATIVE_EVENT_ID",
                        league="epl", home="Different Club",
                        away="Another Club")
        market = public_snapshot()
        market["events"] = [ucl, domestic]
        market["event_count"] = 2
        out = audit(MANIFEST, market,
                    bindings=[source_binding(event_id="UCL_NATIVE_EVENT_ID")],
                    now_utc=NOW)
        self.assertEqual(out["fixtures_with_structurally_matched_public_h2h"], 1)
        self.assertEqual(out["fixtures_with_verified_betting_quotes"], 0)
        self.assertEqual(out["status"], "HOLD")

    def test_one_native_id_cannot_bind_two_local_fixtures(self):
        market = with_event(public_snapshot(), source_row())
        out = audit(MANIFEST, market,
                    bindings=[source_binding(), source_binding(index=1)],
                    now_utc=NOW)
        self.assertEqual(out["fixtures_with_structurally_matched_public_h2h"], 0)
        self.assertIn("AMBIGUOUS_PROVIDER_NATIVE_BINDING",
                      out["fixtures"][0]["blockers"])

    def test_duplicate_bindings_for_one_case_are_quarantined(self):
        market = with_event(public_snapshot(), source_row())
        bindings = [source_binding(), source_binding()]
        out = audit(MANIFEST, market, bindings=bindings, now_utc=NOW)
        self.assertIn("AMBIGUOUS_PROVIDER_NATIVE_BINDING",
                      out["fixtures"][0]["blockers"])

    def test_untrusted_provider_claim_does_not_pass(self):
        market = with_event(public_snapshot(), source_row())
        binding = source_binding()
        binding["provider"] = "unrelated_provider"
        out = audit(MANIFEST, market, bindings=[binding], now_utc=NOW)
        self.assertIn("NATIVE_EVENT_SOURCE_MISMATCH",
                      out["fixtures"][0]["blockers"])

    def test_old_capture_not_current_market_coverage(self):
        market = with_event(public_snapshot(), source_row())
        market["as_of_utc"] = "2026-11-03T05:00:00Z"
        market["events"][0]["market_last_update_utc"] = "2026-11-03T04:59:45Z"
        out = audit(MANIFEST, market, bindings=[source_binding()], now_utc=NOW)
        self.assertEqual(out["snapshot_state"], "STALE_PUBLIC_SNAPSHOT")
        self.assertEqual(out["fixtures_with_structurally_matched_public_h2h"], 0)

    def test_future_capture_and_post_kickoff_not_prematch(self):
        market = with_event(public_snapshot(), source_row())
        market["as_of_utc"] = "2026-11-03T11:01:00Z"
        out = audit(MANIFEST, market, bindings=[source_binding()], now_utc=NOW)
        self.assertEqual(out["snapshot_state"], "FUTURE_OR_INVALID_SNAPSHOT_TIME")
        out = audit(MANIFEST, with_event(public_snapshot(), source_row()),
                    bindings=[source_binding()],
                    now_utc="2026-11-03T20:05:00Z")
        self.assertIn("POST_KICKOFF_NO_NEW_PREMATCH_AUTHORIZATION",
                      out["fixtures"][0]["blockers"])
        self.assertEqual(out["bets_authorized"], 0)

    def test_bad_or_sensitive_public_snapshot_never_unlocks(self):
        for patch in (
            {"event_count": True},
            {"market": "spreads"},
            {"production_recommendations": "ENABLED"},
            {"raw_bookmaker_quotes_redistributed": True},
            {"events": "not an array"},
        ):
            market = public_snapshot()
            market.update(patch)
            with self.subTest(patch=patch):
                out = audit(MANIFEST, market, now_utc=NOW)
                self.assertEqual(out["snapshot_state"], "INVALID_PUBLIC_SNAPSHOT")
                self.assertEqual(out["fixtures_with_verified_betting_quotes"], 0)

    def test_malformed_binding_fail_closed(self):
        market = with_event(public_snapshot(), source_row())
        for bindings in ({"not": "a list"}, [{"local_request_id": []}],
                         [None], [source_binding() | {"verified": True}]):
            with self.subTest(bindings=bindings):
                out = audit(MANIFEST, market, bindings=bindings, now_utc=NOW)
                self.assertEqual(out["fixtures_with_structurally_matched_public_h2h"], 0)
                self.assertEqual(out["binding_state"], "INVALID_BINDINGS")

    def test_manifest_mutations_fail_closed(self):
        for change in ("duplicate_id", "naive_kickoff", "fake_tenth",
                       "fake_source_ids", "invalid_home"):
            manifest = copy.deepcopy(MANIFEST)
            fixtures = manifest["fixtures"]
            if change == "duplicate_id":
                fixtures[1]["local_request_id"] = fixtures[0]["local_request_id"]
            elif change == "naive_kickoff":
                fixtures[0]["kickoff_utc"] = "2026-11-03T17:45:00"
            elif change == "fake_tenth":
                fixtures.append(copy.deepcopy(fixtures[0]))
            elif change == "fake_source_ids":
                manifest["official_fixture_ids_available"] = True
            else:
                fixtures[0]["home"] = fixtures[0]["away"]
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_manifest(manifest)

    def test_invalid_scope_cannot_alias_ucl_with_domestic_row(self):
        market = with_event(public_snapshot(), source_row())
        market["events"][0]["league"] = "soccer_epl"
        out = audit(MANIFEST, market, bindings=[source_binding()], now_utc=NOW)
        self.assertEqual(out["fixtures_with_structurally_matched_public_h2h"], 0)
        self.assertEqual(out["observed_ucl_events_in_public_snapshot"], 0)

    def test_no_credential_or_raw_quote_ever_echoed(self):
        market = with_event(public_snapshot(), source_row(event_id="PRIVATE_SECRET_ID"))
        binding = source_binding(event_id="PRIVATE_SECRET_ID")
        out = audit(MANIFEST, market, bindings=[binding], now_utc=NOW)
        txt = json.dumps(out)
        for forbidden in ("PRIVATE_SECRET_ID", "the-odds-api.com/v4", "0.43",
                          "0.25", "0.32"):
            self.assertNotIn(forbidden, txt)

if __name__ == "__main__":
    unittest.main()
