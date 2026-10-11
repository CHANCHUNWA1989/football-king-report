"""C prospective market-anchored challenger: fixed, auditable, never a betting pick."""
import gzip
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_pair import pair
from model_market_challenger import MODEL, candidate, matches_sealed
from forward_validation import load_archived, extend, report_metrics, valid_prior_sample
from evidence_merge import validate, merge
from research_center import metrics as center_metrics


class MarketChallengerTests(unittest.TestCase):
    def setUp(self):
        self.pred = datetime(2026, 10, 11, 8, tzinfo=timezone.utc)
        self.ko = self.pred + timedelta(days=1)
        self.reported_at = self.ko + timedelta(hours=4)
        self.forecast = {
            "league": "epl", "home": "Everton", "away": "Arsenal",
            "kickoff_utc": self.ko.isoformat(),
            "prediction_utc": self.pred.isoformat(),
            "p_home": .7, "p_draw": .2, "p_away": .1,
            "production_recommendations": "DISABLED",
        }
        self.market_row = {
            "league": "epl", "home": "Everton", "away": "Arsenal",
            "source_event_id": "event-1",
            "kickoff_utc": self.ko.isoformat(),
            "market_last_update_utc":
                (self.pred - timedelta(minutes=12)).isoformat(),
            "p_home": .3, "p_draw": .3, "p_away": .4,
        }
        self.market = {
            "status": "RESEARCH_ONLY",
            "as_of_utc": (self.pred - timedelta(minutes=10)).isoformat(),
            "events": [self.market_row],
            "production_recommendations": "DISABLED",
        }
        self.shadow = {
            "status": "SHADOW_ONLY", "as_of_utc": self.pred.isoformat(),
            "predictions": [self.forecast],
            "production_recommendations": "DISABLED",
        }
        self.public_report = {
            "checked_utc": self.reported_at.isoformat(),
            "fixtures": {"matches": [{
                "league": "epl", "home": "Everton", "away": "Arsenal",
                "kickoff_utc": self.ko.isoformat(), "score_ft": [1, 2],
                "status": "FINISHED",
            }]},
        }

    def paired(self):
        comparison = pair(self.shadow, self.market)
        self.assertEqual(comparison["matched_count"], 1)
        return comparison["comparisons"][0]

    def archive(self, root, comparison):
        with gzip.open(Path(root) / "prediction.json.gz", "wt", encoding="utf-8") as stream:
            json.dump({"comparisons": [comparison],
                       "production_recommendations": "DISABLED"}, stream)

    def settle(self, comparison):
        with tempfile.TemporaryDirectory() as folder:
            self.archive(folder, comparison)
            archived = load_archived(folder)
        return extend({}, archived, self.public_report)

    def test_frozen_market_anchor_is_valid_and_normalized(self):
        p, m = [.7, .2, .1], [.3, .3, .4]
        self.assertEqual(candidate(p, m), [.4, .275, .325])
        self.assertTrue(matches_sealed(p, m, candidate(p, m), MODEL))
        self.assertFalse(matches_sealed(p, m, candidate(p, m), "unregistered-version"))
        self.assertFalse(matches_sealed(p, m, [.7, .2, .1], MODEL))

    def test_bool_nan_and_unnormalized_challenger_inputs_rejected(self):
        good = [.4, .3, .3]
        for invalid in ([True, .3, .7], [.9, .9, .9], [-.1, .4, .7],
                        [float("nan"), .5, .5], "bad", [1.0]):
            with self.subTest(invalid=repr(invalid)):
                with self.assertRaises(ValueError):
                    candidate(invalid, good)
                self.assertFalse(matches_sealed(good, invalid, good, MODEL))

    def test_c_created_only_after_prior_market_pair(self):
        comp = self.paired()
        self.assertEqual(comp["c_model"], MODEL)
        self.assertEqual(comp["c"], [.4, .275, .325])
        self.assertTrue(comp["c_uses_only_prior_de_vigged_market"])
        self.assertTrue(comp["c_research_only_not_calibrated_or_executable"])
        self.assertEqual(comp["result"], None)
        self.assertFalse(comp["available_for_betting"])
        self.market["as_of_utc"] = (self.pred + timedelta(minutes=1)).isoformat()
        self.assertEqual(pair(self.shadow, self.market)["matched_count"], 0)
        self.market["events"] = []
        self.assertEqual(pair(self.shadow, self.market)["comparisons"], [])

    def test_new_archived_c_settles_once_and_old_history_cannot_be_backfilled(self):
        comp = self.paired()
        settled = self.settle(comp)
        self.assertEqual(settled["n"], 1)
        row = settled["samples"][0]
        self.assertEqual(row["c"], [.4, .275, .325])
        self.assertEqual(row["c_model"], MODEL)
        self.assertEqual(row["y"], 2)
        self.assertFalse(row["fixture_result_source_independently_verified"])
        self.assertTrue(valid_prior_sample(row))
        result = report_metrics(settled)["fixed_market_anchored_challenger_c"]
        self.assertEqual(result["status"], "SHADOW_ONLY_UNVERIFIED")
        self.assertEqual(result["n"], 1)
        self.assertFalse(result["improvement_over_market_confirmed"])
        self.assertEqual(result["market_top_choice_correct"], 1)
        self.assertEqual(result["original_model_top_choice_correct"], 0)
        self.assertEqual(result["candidate_top_choice_correct"], 0)
        self.assertTrue(result["candidate_log_loss"] < result["original_model_log_loss"])
        self.assertTrue(result["market_log_loss"] < result["candidate_log_loss"])
        # A legacy snapshot never gains C after settlement, even though
        # current code can calculate a retrospective blended probability.
        legacy = {k:v for k,v in comp.items() if not k.startswith("c")}
        older = self.settle(legacy)
        self.assertNotIn("c", older["samples"][0])
        self.assertEqual(
            report_metrics(older)["fixed_market_anchored_challenger_c"]["n"], 0)

    def test_tampered_or_unauthorized_c_cannot_enter_archived_settlement(self):
        original = self.paired()
        malicious = [
            {**original, "c": [.7, .2, .1]},
            {**original, "c_model": "unknown-model"},
            {**original, "c": [True, .275, .325]},
            {**original, "c_uses_only_prior_de_vigged_market": False},
            {**original, "c_research_only_not_calibrated_or_executable": False},
            {**original, "c": None},
        ]
        for item in malicious:
            with self.subTest(changed=item.get("c"), version=item.get("c_model")):
                with tempfile.TemporaryDirectory() as folder:
                    self.archive(folder, item)
                    self.assertEqual(load_archived(folder), [])

    def test_prior_tampering_and_merge_rejected_without_dropping_old_samples(self):
        original = self.paired()
        settled = self.settle(original)
        doc = {**settled}
        self.assertEqual(len(validate(doc)), 1)
        self.assertEqual(merge(doc, doc)["newly_settled"], 0)
        changed = dict(settled["samples"][0], c=[.7, .2, .1])
        self.assertFalse(valid_prior_sample(changed))
        with self.assertRaisesRegex(ValueError, "INVALID_SEALED_MARKET_ANCHORED_CHALLENGER"):
            validate({**doc, "samples": [changed]})
        self.assertEqual(
            extend({**doc, "samples": [changed]}, [], self.public_report)["n"], 0)

    def test_center_compares_three_models_on_same_sealed_case(self):
        comp = self.paired()
        s = self.settle(comp)["samples"][0]
        other = dict(s)
        other.pop("c")
        other.pop("c_model")
        other["key"] = "an-older-sample-with-no-C"
        rows = [s, other]
        result = center_metrics(rows)
        self.assertEqual(result["settled_games"], 2)
        summary = result["market_anchored_c_research"]
        self.assertEqual(summary["same_sealed_case_count"], 1)
        self.assertTrue(summary["candidate_log_loss"] < summary["original_model_log_loss"])
        self.assertTrue(summary["same_case_market_log_loss"] < summary["candidate_log_loss"])
        self.assertFalse(summary["model_promotion_allowed"])
        self.assertFalse(summary["results_independently_verified"])

    def test_only_true_new_C_cohort_comparisons_count(self):
        comp = self.paired()
        a = self.settle(comp)
        old = self.settle({k:v for k,v in comp.items() if not k.startswith("c")})
        # Simulate two different fixtures, one predating this registration.
        old["samples"][0]["key"] = "legacy-unrelated-key"
        merged = {
            "newly_settled": 1,
            "samples": a["samples"] + old["samples"],
        }
        scored = report_metrics(merged)
        self.assertEqual(scored["forward_archive_samples"], 2)
        self.assertEqual(scored["fixed_market_anchored_challenger_c"]["n"], 1)
        self.assertEqual(scored["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
