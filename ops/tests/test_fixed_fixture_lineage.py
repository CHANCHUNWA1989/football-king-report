"""Synthetic prospective identity lineage checks; no result authentication."""
import gzip
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forward_validation import load_archived
from market_pair import pair
from shadow_archive_bridge import export_archives
from source_fixture_identity import identity_metadata, metadata_from_event_id, validate_sealed_identity


class FixedFixtureLineageTests(unittest.TestCase):
    def setUp(self):
        self.forecast = {
            "league": "bundesliga", "home": "VfB Stuttgart",
            "away": "Borussia Mönchengladbach", "event_id": "openligadb:83212",
            "prediction_utc": "2026-10-20T02:30:00+00:00",
            "kickoff_utc": "2026-10-23T18:30:00+00:00",
            "p_home": .5, "p_draw": .3, "p_away": .2,
            "production_recommendations": "DISABLED"}
        self.shadow = {
            "status": "SHADOW_ONLY", "as_of_utc": self.forecast["prediction_utc"],
            "predictions": [self.forecast], "production_recommendations": "DISABLED"}
        self.quote = {
            "league": self.forecast["league"], "home": self.forecast["home"],
            "away": self.forecast["away"], "kickoff_utc": self.forecast["kickoff_utc"],
            "source_event_id": "market-event-1",
            "market_last_update_utc": "2026-10-20T02:10:00+00:00",
            "p_home": .4, "p_draw": .3, "p_away": .3}
        self.market = {
            "status": "RESEARCH_ONLY", "as_of_utc": "2026-10-20T02:20:00+00:00",
            "events": [self.quote], "production_recommendations": "DISABLED"}

    def archive(self, rows, *, export=False):
        with tempfile.TemporaryDirectory() as folder:
            for i, row in enumerate(rows):
                with gzip.open(Path(folder) / f"{i}.json.gz", "wt", encoding="utf-8") as out:
                    json.dump({"comparisons": [row], "production_recommendations": "DISABLED"}, out)
            return export_archives(folder) if export else load_archived(folder)

    def test_pair_preserves_original_forecast_provider_identity(self):
        original = deepcopy(self.shadow)
        result = pair(self.shadow, self.market)
        self.assertEqual(result["matched_count"], 1)
        row = result["comparisons"][0]
        self.assertEqual(row["forecast_event_id"], "openligadb:83212")
        self.assertEqual(row["source_fixture_identity"],
                         {"provider": "OpenLigaDB", "match_id": "83212"})
        self.assertEqual(self.shadow, original)
        self.assertEqual(row["model"], [.5, .3, .2])
        self.assertEqual(row["market"], [.4, .3, .3])
        self.assertIsNone(row["result"])
        self.assertFalse(row["available_for_betting"])
        self.assertIs(row["independently_verified"], False)
        self.assertIs(row["eligible_for_model_scoring"], False)

    def test_export_preserves_sealed_provider_identity_without_certifying_it(self):
        row = pair(self.shadow, self.market)["comparisons"][0]
        # Supply already sealed metadata so this independently catches export loss.
        row.update(forecast_event_id="openligadb:83212",
                   source_fixture_identity={"provider": "OpenLigaDB", "match_id": "83212"},
                   source_fixture_identity_status="UNAUTHENTICATED",
                   independently_verified=False, eligible_for_model_scoring=False)
        saved = self.archive([row], export=True)[0]
        self.assertEqual(saved["forecast_event_id"], "openligadb:83212")
        self.assertEqual(saved["source_fixture_identity"], row["source_fixture_identity"])
        self.assertEqual(saved["source_fixture_identity_status"], "UNAUTHENTICATED")
        self.assertIs(saved["independently_verified"], False)
        self.assertIs(saved["eligible_for_model_scoring"], False)
        self.assertEqual(saved["production_recommendations"], "DISABLED")

    def test_legacy_rows_keep_original_fixture_key_and_have_no_backfilled_id(self):
        del self.forecast["event_id"]
        row = pair(self.shadow, self.market)["comparisons"][0]
        self.assertNotIn("forecast_event_id", row)
        saved = self.archive([row], export=True)[0]
        self.assertEqual(saved["fixture_id"], json.dumps(
            ["bundesliga", "vfbstuttgart", "borussiamonchengladbach",
             self.forecast["kickoff_utc"]], ensure_ascii=False, separators=(",", ":")))
        self.assertNotIn("forecast_event_id", saved)
        self.assertNotIn("source_fixture_identity", saved)
        self.assertEqual(saved["model"], row["model"])
        self.assertEqual(saved["market"], row["market"])

    def test_unknown_or_noncanonical_namespace_is_raw_identity_only(self):
        for event_id in ("other-provider:83212", "OpenLigaDB:83212", "openligadb:083212",
                         "openligadb:0", "openligadb:+83212", "openligadb:８３２１２",
                         "some-openligadb:83212", "two-source-utc-bundesliga-example"):
            with self.subTest(event_id=event_id):
                self.forecast["event_id"] = event_id
                row = pair(self.shadow, self.market)["comparisons"][0]
                saved = self.archive([row], export=True)[0]
                self.assertEqual(saved["forecast_event_id"], event_id)
                self.assertNotIn("source_fixture_identity", saved)
                self.assertNotIn("source_fixture_identity_status", saved)
                self.assertIs(saved["eligible_for_model_scoring"], False)

    def test_malformed_original_event_id_cannot_enter_new_pair(self):
        for value in (None, True, 83212, [], {}, "", " ", " openligadb:83212",
                      "openligadb:83212 ", "openligadb:83212\n", "x\x00y", "x" * 513):
            with self.subTest(value=repr(value)):
                self.forecast["event_id"] = value
                self.assertEqual(pair(self.shadow, self.market)["matched_count"], 0)

    def test_typed_identity_cannot_override_original_forecast_event_id(self):
        metadata = metadata_from_event_id("openligadb:83213")
        self.forecast.update(metadata)
        self.assertEqual(pair(self.shadow, self.market)["matched_count"], 0)
        self.forecast.update(metadata_from_event_id("openligadb:83212"))
        self.assertEqual(pair(self.shadow, self.market)["matched_count"], 1)

    def test_archive_rejects_malformed_or_mismatched_typed_claims(self):
        valid = pair(self.shadow, self.market)["comparisons"][0]
        claims = [None, True, [], {},
                  {"provider": "OpenLigaDB", "match_id": True},
                  {"provider": "OpenLigaDB", "match_id": 83212},
                  {"provider": "OpenLigaDB", "match_id": "083212"},
                  {"provider": "OpenLigaDB", "match_id": "83212 "},
                  {"provider": "openligadb", "match_id": "83212"},
                  {"provider": "NDR", "match_id": "83212"},
                  {"provider": "OpenLigaDB", "match_id": "83212", "verified": True},
                  {"provider": "OpenLigaDB", "match_id": "83213"}]
        for identity in claims:
            with self.subTest(identity=identity):
                row = {**valid, "source_fixture_identity": identity}
                with self.assertRaises(ValueError):
                    validate_sealed_identity(row)
                self.assertEqual(self.archive([row]), [])

    def test_identity_cannot_claim_authentication_or_scoring_eligibility(self):
        valid = pair(self.shadow, self.market)["comparisons"][0]
        for field, value in (("source_fixture_identity_status", "VERIFIED"),
                             ("independently_verified", True),
                             ("independently_verified", 0),
                             ("eligible_for_model_scoring", True),
                             ("eligible_for_model_scoring", None)):
            with self.subTest(field=field, value=value):
                self.assertEqual(self.archive([{**valid, field: value}]), [])
        for field in ("forecast_event_id", "source_fixture_identity_status",
                      "independently_verified", "eligible_for_model_scoring"):
            with self.subTest(missing=field):
                row = dict(valid)
                del row[field]
                self.assertEqual(self.archive([row]), [])

    def test_canonical_raw_archived_id_is_never_reinterpreted_as_sealed_typed_id(self):
        row = pair(self.shadow, self.market)["comparisons"][0]
        del row["source_fixture_identity"]
        del row["source_fixture_identity_status"]
        saved = self.archive([row], export=True)[0]
        self.assertEqual(saved["forecast_event_id"], "openligadb:83212")
        self.assertNotIn("source_fixture_identity", saved)

    def test_same_time_conflicting_identity_or_legacy_absence_is_quarantined(self):
        first = pair(self.shadow, self.market)["comparisons"][0]
        other = {**first, **metadata_from_event_id("openligadb:83213")}
        legacy = {k: v for k, v in first.items() if k not in metadata_from_event_id("openligadb:83212")}
        for second in (other, legacy):
            for order in ((first, second), (second, first)):
                with self.subTest(second=second.get("forecast_event_id"), first=order[0].get("forecast_event_id")):
                    self.assertEqual(self.archive(order), [])

    def test_provider_id_reused_for_different_fixture_is_quarantined_in_both_orders(self):
        first = pair(self.shadow, self.market)["comparisons"][0]
        independent = {**first, **metadata_from_event_id("openligadb:99999"), "home": "Other Home"}
        changes = (("league", "bundesliga2"), ("home", "Other Club"),
                   ("away", "Other Away"), ("kickoff_utc", "2026-10-24T18:30:00+00:00"))
        for field, value in changes:
            conflicting = {**first, field: value}
            for order in ((first, conflicting), (conflicting, first)):
                with self.subTest(field=field, first=order[0].get(field)):
                    selected = self.archive([*order, independent], export=True)
                    self.assertEqual(len(selected), 1)
                    self.assertEqual(selected[0]["source_fixture_identity"]["match_id"], "99999")

    def test_later_unselected_provider_id_reuse_still_quarantines_both_fixtures(self):
        first = pair(self.shadow, self.market)["comparisons"][0]
        legacy = {k: v for k, v in first.items() if k not in metadata_from_event_id("openligadb:83212")}
        later = {**first, "prediction_utc": "2026-10-20T03:30:00+00:00"}
        conflicting = {**first, "home": "Other Club"}
        for rows in ((legacy, later, conflicting), (conflicting, later, legacy),
                     (later, legacy, conflicting)):
            self.assertEqual(self.archive(rows), [])

    def test_later_metadata_never_backfills_original_earliest_legacy_record(self):
        first = pair(self.shadow, self.market)["comparisons"][0]
        legacy = {k: v for k, v in first.items() if k not in metadata_from_event_id("openligadb:83212")}
        later = {**first, "prediction_utc": "2026-10-20T03:30:00+00:00"}
        for rows in ((legacy, later), (later, legacy)):
            selected = self.archive(rows, export=True)
            self.assertEqual(len(selected), 1)
            self.assertNotIn("forecast_event_id", selected[0])
            self.assertNotIn("source_fixture_identity", selected[0])
            self.assertEqual(selected[0]["sealed_at_utc"], legacy["prediction_utc"])

    def test_identical_replays_keep_one_original_sealed_row(self):
        row = pair(self.shadow, self.market)["comparisons"][0]
        selected = self.archive([row, deepcopy(row)])
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0][1], row)
        self.assertEqual(identity_metadata(row)["source_fixture_identity"], row["source_fixture_identity"])

    def test_many_provider_ids_for_one_fixture_are_bounded_before_selection(self):
        first = pair(self.shadow, self.market)["comparisons"][0]
        rows = [{**first, **metadata_from_event_id(f"openligadb:{match_id}")}
                for match_id in (83212, 83213, 83214)]
        # The existing selected/ambiguous count is only one, so that old bound
        # alone cannot limit a new map containing many IDs for the same game.
        with patch("forward_validation.MAX_EVIDENCE", 2):
            with self.assertRaisesRegex(ValueError, "TOO_MANY_SOURCE_FIXTURE_IDENTITIES"):
                self.archive(rows)
        with patch("forward_validation.MAX_EVIDENCE", 1):
            self.assertEqual(len(self.archive([first, deepcopy(first)])), 1)


if __name__ == "__main__":
    unittest.main()
