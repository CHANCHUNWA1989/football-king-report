"""Synthetic, locally sealed 300-fixture 12+ UTC-week paired bootstrap tests."""
import copy
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vnext_prospective_block_bootstrap import audit_sealed_holdout, evaluate_sealed_holdout
from vnext_prospective_local_seal import seal_forecast_pair

UTC = timezone.utc
SCOPE = "bundesliga/2026-2027/regulation-90-minutes"
EVALUATION = "2026-12-15T00:00:00Z"


def stamp(t):
    return t.isoformat().replace("+00:00", "Z")


def fixture_case(i):
    kickoff = datetime(2026, 8, 1, 20, tzinfo=UTC) + timedelta(days=i // 3)
    asof = kickoff - timedelta(minutes=90)
    fid = f"vnext-synthetic-{i:04d}"
    pair = {
        "fixture_id": fid, "kickoff_utc": stamp(kickoff), "as_of_utc": stamp(asof),
        "models": {
            "baseline": {
                "model_id": "frozen-A",
                "forecast_utc": stamp(asof),
                "inputs_available_utc": stamp(asof - timedelta(minutes=10)),
                "input_sha256": "a" * 64,
                "probabilities_1x2": [0.45, 0.30, 0.25],
                "calibrated": False, "production_recommendations": "DISABLED",
            },
            "challenger": {
                "model_id": "frozen-C",
                "forecast_utc": stamp(asof),
                "inputs_available_utc": stamp(asof - timedelta(minutes=10)),
                "input_sha256": "b" * 64,
                "probabilities_1x2": [0.65, 0.20, 0.15],
                "calibrated": False, "production_recommendations": "DISABLED",
            },
        },
    }
    refs = [{
        "provider": "synthetic-forecast-feed", "source_event_id": f"event-{i:04d}",
        "source_group": "unknown-upstream",
        "source_updated_utc": stamp(asof - timedelta(minutes=9)),
        "received_utc": stamp(asof - timedelta(minutes=8)),
        "available_utc": stamp(asof - timedelta(minutes=7)),
        "raw_sha256": "c" * 64,
        "rights_scope": "DERIVED_METADATA_ONLY_UNVERIFIED",
    }]
    result = {
        "fixture_id": fid, "home_goals": 2, "away_goals": 1,
        "result_received_utc": stamp(kickoff + timedelta(hours=3)),
        "result_source": "synthetic-score-observation", "raw_sha256": "d" * 64,
        "independently_authenticated": False,
    }
    observations = [{
        "provider": name, "fixture_id": fid,
        "provider_fixture_id": f"record-{name}-{i}",
        "source_scope": SCOPE,
        "home_goals": 2, "away_goals": 1,
        "source_updated_utc": stamp(kickoff + timedelta(hours=2)),
        "received_utc": stamp(kickoff + timedelta(hours=2, minutes=5)),
        "raw_sha256": "e" * 64,
    } for name in ("NDR", "OpenLigaDB")]
    return pair, refs, result, observations, stamp(asof + timedelta(seconds=12))


def manifesto(cases):
    return {
        "cohort_id": "synthetic-300-preregistered-2026",
        "fixture_ids": sorted(x["result"]["fixture_id"] for x in cases),
        "registered_utc": "2026-07-15T00:00:00Z",
        "training_cutoff_utc": "2026-07-01T00:00:00Z",
        "baseline_model_id": "frozen-A",
        "challenger_model_id": "frozen-C",
        "evaluation_end_utc": "2026-12-01T00:00:00Z",
        "primary_metric": "LOG_LOSS",
        "resampling_unit": "UTC_ISO_WEEK",
        "production_recommendations": "DISABLED",
    }


class ProspectiveBootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.data = []
        for i in range(300):
            pair, refs, result, observations, clock = fixture_case(i)
            proof = seal_forecast_pair(cls.root, pair, refs, captured_utc=clock)
            cls.data.append({
                "file_name": proof["file_name"],
                "content_sha256": proof["content_sha256"],
                "result": result,
                "result_observations": observations,
            })
        cls.manifest = manifesto(cls.data)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def evaluate(self, cases=None, manifest=None):
        return audit_sealed_holdout(
            self.root,
            self.manifest if manifest is None else manifest,
            self.data if cases is None else cases,
            evaluated_utc=EVALUATION,
        )

    def test_all_300_sealed_matches_generate_exploratory_intervals(self):
        result = self.evaluate()
        self.assertEqual(result["status"], "EXPLORATORY_ONLY")
        self.assertEqual(result["fixture_count"], 300)
        self.assertGreaterEqual(result["distinct_utc_iso_weeks"], 12)
        self.assertEqual(result["bootstrap_replicates"], 500)
        self.assertEqual(result["source_observation_agreement_n"], 300)
        self.assertEqual(result["independently_verified_result_n"], 0)
        self.assertEqual(result["primary_metric"], "LOG_LOSS")
        self.assertIn("ll_diff", result["week_cluster_percentile_95_intervals_unverified"])
        self.assertGreater(result["paired_baseline_minus_challenger"]["ll_diff"], 0)
        for key in ("ll_diff", "brier_diff", "draw_brier_diff"):
            low, high = result["week_cluster_percentile_95_intervals_unverified"][key]
            self.assertLessEqual(low, high)
            self.assertLessEqual(low, result["paired_baseline_minus_challenger"][key])
            self.assertGreaterEqual(high, result["paired_baseline_minus_challenger"][key])
        for name in ("manifest_externally_registered", "archive_clock_externally_attested",
                     "independent_sources_certified", "independently_verified_real_oos",
                     "model_accuracy_improvement_verified", "model_eligible_for_promotion",
                     "market_ev_verified", "positive_ev_verified"):
            self.assertFalse(result[name])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_results_are_deterministic_regardless_of_row_order(self):
        first = self.evaluate()
        reverse = self.evaluate(cases=list(reversed(self.data)))
        self.assertEqual(first, reverse)

    def test_cannot_claim_model_win_from_synthetic_positive_delta(self):
        output = self.evaluate()
        self.assertGreater(output["week_cluster_percentile_95_intervals_unverified"]["ll_diff"][0], 0)
        self.assertFalse(output["model_accuracy_improvement_verified"])
        self.assertFalse(output["independently_verified_real_oos"])

    def test_299_cases_do_not_pass_minimum_research_gate(self):
        r = self.evaluate(cases=self.data[:-1])
        self.assertEqual(r["reason"], "INSUFFICIENT_OR_EXCESSIVE_PAIRED_FIXTURES")

    def test_missing_universe_fixture_is_not_silently_dropped(self):
        m = copy.deepcopy(self.manifest)
        m["fixture_ids"][0] = "unobserved-fixture"
        self.assertEqual(self.evaluate(manifest=m)["reason"],
                         "MISSING_OR_EXTRA_HOLDOUT_FIXTURES")

    def test_duplicate_fixture_cannot_count_as_new_independent_match(self):
        data = copy.deepcopy(self.data)
        data[-1] = copy.deepcopy(data[0])
        self.assertEqual(self.evaluate(cases=data)["reason"],
                         "DUPLICATE_FIXTURE_OR_MULTIPLE_CUTS")

    def test_manifest_registered_after_first_forecast_refused(self):
        m = copy.deepcopy(self.manifest)
        m["registered_utc"] = "2026-08-02T00:00:00Z"
        self.assertEqual(self.evaluate(manifest=m)["reason"],
                         "CANDIDATE_NOT_SEALED_AFTER_REGISTERED_MANIFEST")

    def test_training_cutoff_cannot_follow_registration(self):
        m = copy.deepcopy(self.manifest)
        m["training_cutoff_utc"] = "2026-07-20T00:00:00Z"
        self.assertEqual(self.evaluate(manifest=m)["reason"], "INVALID_HOLDOUT_CHRONOLOGY")

    def test_cannot_change_model_versions_mid_cohort(self):
        m = copy.deepcopy(self.manifest)
        m["challenger_model_id"] = "frozen-D"
        self.assertEqual(self.evaluate(manifest=m)["reason"], "UNEXPECTED_MODEL_VERSION")

    def test_result_disagreement_by_two_sources_holds(self):
        data = copy.deepcopy(self.data)
        data[0]["result_observations"][1]["away_goals"] = 4
        self.assertEqual(self.evaluate(cases=data)["reason"],
                         "UNCONFIRMED_OR_CONFLICTING_RESULT_SOURCES")

    def test_result_label_must_match_both_observations(self):
        data = copy.deepcopy(self.data)
        data[0]["result"]["away_goals"] = 0
        self.assertEqual(self.evaluate(cases=data)["reason"],
                         "RESULT_DISAGREES_WITH_SOURCE_OBSERVATIONS")

    def test_future_result_was_not_available_at_evaluation(self):
        data = copy.deepcopy(self.data)
        data[0]["result"]["result_received_utc"] = "2027-01-01T00:00:00Z"
        self.assertEqual(self.evaluate(cases=data)["reason"],
                         "RESULT_NOT_AVAILABLE_AT_EVALUATION")

    def test_upstream_independent_truth_is_not_declared_by_saved_bool(self):
        data = copy.deepcopy(self.data)
        data[0]["result"]["independently_authenticated"] = True
        self.assertEqual(self.evaluate(cases=data)["status"], "HOLD")

    def test_resampling_protocol_is_frozen_not_selected_after_results(self):
        for name, replacement in (("primary_metric", "Brier"),
                                  ("resampling_unit", "PER_MINUTE"),
                                  ("production_recommendations", "ENABLED")):
            with self.subTest(name=name):
                m = copy.deepcopy(self.manifest)
                m[name] = replacement
                self.assertEqual(self.evaluate(manifest=m)["status"], "HOLD")

    def test_fake_bookmaker_ev_or_odds_in_result_rejected(self):
        data = copy.deepcopy(self.data)
        data[0]["result"]["decimal_odds"] = 1.9
        self.assertEqual(self.evaluate(cases=data)["status"], "HOLD")

    def test_archive_digest_tampering_rejected(self):
        data = copy.deepcopy(self.data)
        data[0]["content_sha256"] = "f" * 64
        self.assertEqual(self.evaluate(cases=data)["reason"],
                         "ARCHIVE_INTEGRITY_OR_SIZE_FAILURE")

    def test_missing_archive_file_holds(self):
        data = copy.deepcopy(self.data)
        data[0]["file_name"] = "0" * 64 + ".json"
        self.assertEqual(self.evaluate(cases=data)["status"], "HOLD")

    def test_cannot_change_manifest_cause_of_status_without_pinning(self):
        m = copy.deepcopy(self.manifest)
        m["certified_licensed_sources"] = True
        self.assertEqual(self.evaluate(manifest=m)["reason"], "INVALID_HOLDOUT_MANIFEST")


if __name__ == "__main__":
    unittest.main()
