"""Synthetic A + two real-interface model handoff adversarial tests."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from ops.penaltyblog_a_dual_prematch_capture import (
    A_MODEL, SCHEMA, capture, main,
)
from ops.tests.test_penaltyblog_research_bridge import FakeModel, sample

A = datetime(2026, 11, 30, 19, 50, tzinfo=timezone.utc)
CUT = datetime(2026, 11, 30, 20, tzinfo=timezone.utc)
KO = datetime(2026, 12, 1, 0, tzinfo=timezone.utc)


def z(date):
    return date.isoformat().replace("+00:00", "Z")


def payload():
    base = sample()
    target = dict(base["target_fixture"])
    target["kickoff_utc"] = z(KO)
    original = {
        **target,
        "produced_utc": z(A),
        "max_input_received_utc": z(A - timedelta(minutes=1)),
        "model_id": A_MODEL,
        "probabilities": [.45, .35, .2],
        "source_authenticity_verified": False,
        "independently_timestamped": False,
        "production_recommendations": "DISABLED",
    }
    return {
        "schema": SCHEMA, "production_recommendations": "DISABLED",
        "decision_cutoff_utc": z(CUT), "original_a": original,
        "historical_matches": base["historical_matches"],
    }


class Clock:
    def __init__(self, times=None):
        self.times = list(times or [
            A + timedelta(minutes=5),
            A + timedelta(minutes=5, seconds=2),
            A + timedelta(minutes=5, seconds=4),
        ])
        self.calls = 0

    def __call__(self):
        value = self.times[self.calls]
        self.calls += 1
        return value


FACTORIES = {"poisson": FakeModel, "dixon_coles": FakeModel}


class PrematchDualCaptureTests(unittest.TestCase):
    def setUp(self):
        self.data = payload()
        self.clock = Clock()
        FakeModel.calls = []

    def audit(self):
        return capture(self.data, clock=self.clock, model_factories=FACTORIES)

    def test_bivariate_factory_cannot_expand_fixed_dual_handoff(self):
        report = capture(self.data, clock=self.clock,
                         model_factories={**FACTORIES, "bivariate_poisson": FakeModel})
        self.assertEqual(report["reason"], "INVALID_RESEARCH_MODEL_FACTORY")
        self.assertNotIn("unverified_triple_capture", report)
        self.assertFalse(report["positive_ev_verified"])

    def test_complete_technical_handoff_never_authenticates(self):
        r = self.audit()
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["reason"], "LOCAL_A_POISSON_DC_CAPTURE_NOT_EXTERNALLY_ATTESTED")
        self.assertEqual(FakeModel.calls, [])
        self.assertEqual(self.clock.calls, 3)
        self.assertFalse(r["positive_ev_verified"])
        self.assertFalse(r["model_promoted"])
        self.assertFalse(r["independent_provenance_verified"])
        self.assertFalse(r["historical_results_independently_verified"])
        self.assertFalse(r["original_a_source_authenticated"])
        self.assertFalse(r["trusted_clock_verified"])
        self.assertFalse(r["eligible_for_model_scoring"])
        self.assertEqual(r["certified_prospective_samples"], 0)
        self.assertEqual(r["production_recommendations"], "DISABLED")
        v = r["unverified_triple_capture"]
        self.assertEqual(v["event_id"], "future-1")
        self.assertEqual(v["original_a_model_id"], A_MODEL)
        self.assertEqual(v["original_a_probabilities"], [.45, .35, .2])
        self.assertEqual([x["model"] for x in v["challenger_observations"]],
                         ["poisson", "dixon_coles"])
        self.assertEqual([x["training_match_count"] for x in v["challenger_observations"]],
                         [40, 40])
        self.assertEqual([x["probabilities"] for x in v["challenger_observations"]],
                         [[.5, .3, .2], [.5, .3, .2]])
        self.assertEqual(len(v["historical_training_input_sha256_unattested"]), 64)
        self.assertEqual(len(r["locally_reproducible_capture_sha256"]), 64)
        self.assertNotIn("odds", json.dumps(r))
        self.assertNotIn("ev_per_unit", r)

    def test_same_claimed_cutoff_normalizes_utc_offsets(self):
        self.data["decision_cutoff_utc"] = "2026-12-01T04:00:00+08:00"
        self.assertIn("unverified_triple_capture", self.audit())

    def test_bad_model_reference_rejected(self):
        self.data["original_a"]["model_id"] = "fake-producer"
        self.assertEqual(self.audit()["reason"], "INVALID_ORIGINAL_A_UNVERIFIED_SNAPSHOT")
        self.assertEqual(self.clock.calls, 0)

    def test_original_a_flags_cannot_approve(self):
        self.data["original_a"]["source_authenticity_verified"] = True
        self.assertEqual(self.audit()["reason"], "INVALID_ORIGINAL_A_UNVERIFIED_SNAPSHOT")

    def test_production_enabled_rejected(self):
        self.data["production_recommendations"] = "ENABLED"
        self.assertEqual(self.audit()["reason"], "INVALID_HANDOFF_CONTRACT")

    def test_original_a_production_enabled_rejected(self):
        self.data["original_a"]["production_recommendations"] = "ENABLED"
        self.assertEqual(self.audit()["reason"], "INVALID_ORIGINAL_A_UNVERIFIED_SNAPSHOT")

    def test_missing_required_native_id_rejected(self):
        del self.data["original_a"]["home_team_id"]
        self.assertEqual(self.audit()["reason"], "INVALID_ORIGINAL_A_CONTRACT")

    def test_injected_outcome_in_original_a_rejected(self):
        self.data["original_a"]["home_goals"] = 2
        self.assertEqual(self.audit()["reason"], "INVALID_ORIGINAL_A_CONTRACT")

    def test_original_a_boolean_probability_rejected(self):
        self.data["original_a"]["probabilities"] = [True, 0, 0]
        self.assertEqual(self.audit()["reason"], "INVALID_ORIGINAL_A_UNVERIFIED_SNAPSHOT")

    def test_original_a_probabilities_bad_sum_rejected(self):
        self.data["original_a"]["probabilities"] = [.3, .3, .3]
        self.assertEqual(self.audit()["reason"], "INVALID_ORIGINAL_A_UNVERIFIED_SNAPSHOT")

    def test_original_a_lookahead_from_claimed_input(self):
        self.data["original_a"]["max_input_received_utc"] = z(A + timedelta(minutes=1))
        self.assertEqual(self.audit()["reason"], "ORIGINAL_A_LOOKAHEAD_OR_KICKOFF_BUFFER")
        self.assertEqual(self.clock.calls, 0)

    def test_original_a_stale_rejected(self):
        self.data["original_a"]["produced_utc"] = z(A - timedelta(hours=3))
        self.data["original_a"]["max_input_received_utc"] = z(A - timedelta(hours=4))
        self.assertEqual(self.audit()["reason"], "STALE_ORIGINAL_A_SNAPSHOT")

    def test_history_future_result_rejected_before_any_model_fit(self):
        self.data["historical_matches"][0]["result_recorded_utc"] = z(CUT)
        self.assertEqual(self.audit()["reason"], "LOOKAHEAD_OR_UNAVAILABLE_RESULT")
        self.assertEqual(self.clock.calls, 0)

    def test_history_after_actual_start_but_before_deadline_rejects_before_fit(self):
        started = A + timedelta(minutes=5)
        future = started + timedelta(microseconds=1)
        for index in (0, -1):
            for stamp in (z(future), future.astimezone(timezone(timedelta(hours=8))).isoformat()):
                with self.subTest(index=index, stamp=stamp):
                    data = payload()
                    data["historical_matches"][index]["result_recorded_utc"] = stamp
                    original = copy.deepcopy(data)
                    factory = Mock(wraps=FakeModel)
                    clock = Clock()
                    report = capture(data, clock=clock, model_factories={
                        "poisson": factory, "dixon_coles": factory})
                    self.assertEqual(report["reason"], "HISTORY_UNAVAILABLE_AT_ACTUAL_MODEL_START")
                    factory.assert_not_called()
                    self.assertEqual(clock.calls, 1)
                    self.assertEqual(data, original)
                    self.assertNotIn("unverified_triple_capture", report)
                    self.assertNotIn("ev_per_unit", report)
                    self.assertFalse(report["positive_ev_verified"])
                    self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_history_available_at_actual_start_keeps_valid_local_capture(self):
        started = A + timedelta(minutes=5)
        for instant in (started - timedelta(microseconds=1), started):
            with self.subTest(instant=instant):
                data = payload()
                data["historical_matches"][-1]["result_recorded_utc"] = instant.astimezone(
                    timezone(timedelta(hours=8))).isoformat()
                factory = Mock(wraps=FakeModel)
                report = capture(data, clock=Clock(), model_factories={
                    "poisson": factory, "dixon_coles": factory})
                self.assertIn("unverified_triple_capture", report)
                self.assertEqual(factory.call_count, 2)
                self.assertEqual(report["certified_prospective_samples"], 0)
                self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_histories_from_different_provider_rejected(self):
        self.data["historical_matches"][0]["source_namespace"] = "other"
        self.assertEqual(self.audit()["reason"], "CROSS_SOURCE_OR_LEAGUE_MISMATCH")
        self.assertEqual(self.clock.calls, 0)

    def test_model_cannot_take_over_future_fixture_history(self):
        self.data["historical_matches"][0]["event_id"] = "future-1"
        self.assertEqual(self.audit()["reason"], "DUPLICATE_OR_TARGET_RESULT")

    def test_both_models_must_finish_before_cutoff(self):
        self.clock = Clock([A + timedelta(minutes=5), A + timedelta(minutes=6),
                            CUT + timedelta(seconds=1)])
        r = self.audit()
        self.assertEqual(r["reason"], "MODEL_EXECUTION_CROSSED_PREMATCH_WINDOW")
        self.assertNotIn("unverified_triple_capture", r)
        self.assertEqual(self.clock.calls, 3)

    def test_first_model_crosses_cutoff(self):
        self.clock = Clock([A + timedelta(minutes=5), CUT + timedelta(seconds=1)])
        self.assertEqual(self.audit()["reason"], "MODEL_EXECUTION_CROSSED_PREMATCH_WINDOW")

    def test_clock_goes_backwards(self):
        self.clock = Clock([A + timedelta(minutes=5), A + timedelta(minutes=4)])
        self.assertEqual(self.audit()["reason"], "MODEL_EXECUTION_CROSSED_PREMATCH_WINDOW")

    def test_runner_after_cutoff_blocks_before_model(self):
        self.clock = Clock([CUT + timedelta(seconds=1)])
        self.assertEqual(self.audit()["reason"], "NOT_CAPTURED_WITHIN_DECLARED_PREMATCH_WINDOW")
        self.assertEqual(self.clock.calls, 1)

    def test_runner_before_claimed_original_production_rejected(self):
        self.clock = Clock([A - timedelta(seconds=1)])
        self.assertEqual(self.audit()["reason"], "NOT_CAPTURED_WITHIN_DECLARED_PREMATCH_WINDOW")

    def test_naive_local_clock_rejected(self):
        self.clock = Clock([datetime(2026, 11, 30, 19, 55)])
        self.assertEqual(self.audit()["reason"], "INVALID_LOCAL_CLOCK")

    def test_insufficient_history_rejected(self):
        self.data["historical_matches"] = self.data["historical_matches"][:10]
        self.assertEqual(self.audit()["reason"], "INSUFFICIENT_OR_EXCESS_TRAINING")

    def test_invalid_model_factory_map_rejected(self):
        r = capture(self.data, clock=self.clock, model_factories={"poisson": FakeModel})
        self.assertEqual(r["reason"], "INVALID_RESEARCH_MODEL_FACTORY")

    def test_failed_second_model_fails_entire_cohort(self):
        class Failed(FakeModel):
            def fit(self):
                raise RuntimeError("intentional synthetic fit failure")
        r = capture(self.data, clock=self.clock, model_factories={
            "poisson": FakeModel, "dixon_coles": Failed})
        self.assertEqual(r["reason"], "MODEL_UNAVAILABLE_OR_UNTRUSTED")
        self.assertNotIn("unverified_triple_capture", r)

    def test_no_penaltyblog_installed_causes_hold_not_fallback(self):
        with patch.dict("sys.modules", {"penaltyblog": None}):
            r = capture(self.data, clock=self.clock)
        self.assertEqual(r["reason"], "MODEL_UNAVAILABLE_OR_UNTRUSTED")
        self.assertNotIn("unverified_triple_capture", r)

    def test_extra_caller_certification_fields_rejected(self):
        self.data["source_authenticated"] = True
        self.assertEqual(self.audit()["reason"], "INVALID_HANDOFF_CONTRACT")

    def test_original_a_fixture_is_target_not_a_training_result(self):
        self.data["historical_matches"][0]["event_id"] = self.data["original_a"]["event_id"]
        self.assertEqual(self.audit()["reason"], "DUPLICATE_OR_TARGET_RESULT")

    def test_no_output_on_invalid_cli_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "input.json"
            out = Path(tmp) / "out.json"
            self.data["original_a"]["model_id"] = "fake"
            inp.write_text(json.dumps(self.data), encoding="utf-8")
            self.assertEqual(main(["--input", str(inp), "--output", str(out)]), 1)
            self.assertFalse(out.exists())

    def test_input_output_alias_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            path.write_text(json.dumps(self.data), encoding="utf-8")
            before = path.read_bytes()
            self.assertEqual(main(["--input", str(path), "--output", str(path)]), 1)
            self.assertEqual(path.read_bytes(), before)

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            actual, alias, out = (Path(tmp) / x for x in ("input.json", "alias.json", "out.json"))
            actual.write_text(json.dumps(self.data), encoding="utf-8")
            alias.symlink_to(actual)
            self.assertEqual(main(["--input", str(alias), "--output", str(out)]), 1)
            self.assertFalse(out.exists())

    def test_duplicate_json_object_key_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp, out = Path(tmp) / "input.json", Path(tmp) / "out.json"
            inp.write_bytes(b'{"schema":"1","schema":"2"}')
            self.assertEqual(main(["--input", str(inp), "--output", str(out)]), 1)
            self.assertFalse(out.exists())

    def test_cli_existing_output_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp, out = Path(tmp) / "input.json", Path(tmp) / "out.json"
            inp.write_text(json.dumps(self.data), encoding="utf-8")
            out.write_bytes(b"existing")
            result = {"unverified_triple_capture": {"synthetic": True},
                      "status": "HOLD", "reason": "LOCAL_A_POISSON_DC_CAPTURE_NOT_EXTERNALLY_ATTESTED"}
            with patch("ops.penaltyblog_a_dual_prematch_capture.capture", return_value=result):
                self.assertEqual(main(["--input", str(inp), "--output", str(out)]), 1)
            self.assertEqual(out.read_bytes(), b"existing")

    def test_private_cli_file_mode_and_no_certification(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp, out = Path(tmp) / "input.json", Path(tmp) / "out.json"
            inp.write_text(json.dumps(self.data), encoding="utf-8")
            result = {"unverified_triple_capture": {"synthetic": True},
                      "status": "HOLD", "reason": "LOCAL_A_POISSON_DC_CAPTURE_NOT_EXTERNALLY_ATTESTED",
                      "production_recommendations": "DISABLED",
                      "positive_ev_verified": False}
            with patch("ops.penaltyblog_a_dual_prematch_capture.capture", return_value=result):
                self.assertEqual(main(["--input", str(inp), "--output", str(out)]), 0)
            self.assertEqual(json.loads(out.read_text())["status"], "HOLD")
            self.assertEqual(out.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
