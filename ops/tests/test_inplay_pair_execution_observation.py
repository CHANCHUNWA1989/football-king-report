"""Local in-process observation tests; all candidates are synthetic stubs."""
import copy
from datetime import datetime
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_inplay_same_snapshot_comparison import sample
from inplay_pair_execution_observation import observe_local


class LocalExecutionObservationTests(unittest.TestCase):
    def test_one_real_python_callback_invocation_only_research(self):
        case, snapshot, output = sample()
        original = copy.deepcopy((case, snapshot, output))
        calls = []
        def candidate(arg):
            calls.append(copy.deepcopy(arg))
            return copy.deepcopy(output)
        result = observe_local(case, snapshot, candidate)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], snapshot)
        self.assertEqual((case, snapshot, output), original)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["local_callback_invocation_count"], 1)
        self.assertTrue(result["callback_return_observed_in_process"])
        self.assertFalse(result["candidate_implementation_authenticated"])
        self.assertFalse(result["externally_witnessed"])
        self.assertFalse(result["genuine_pr433_execution_proven"])
        self.assertFalse(result["formal_model_comparison_allowed"])
        self.assertEqual(result["certified_paired_samples"], 0)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertIsNone(result["roi"])
        self.assertIsNone(result["recommendation"])
        self.assertEqual(len(result["input_sha256_unattested"]), 64)
        self.assertEqual(len(result["output_sha256_unattested"]), 64)
        self.assertLessEqual(datetime.fromisoformat(result["local_call_started_utc"]),
                             datetime.fromisoformat(result["local_call_finished_utc"]))

    def test_cannot_use_a_supplied_result_as_execution_callable(self):
        case, snap, out = sample()
        self.assertEqual(observe_local(case, snap, out)["reason"],
                         "CALLABLE_REQUIRED_NO_REPLAYED_OUTPUT")

    def test_baseline_hold_prevents_callback(self):
        case, snap, out = sample()
        case["state"]["home_red_cards"] = 1
        called = []
        def fn(arg):
            called.append(True)
            return out
        r = observe_local(case, snap, fn)
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(called, [])
        self.assertEqual(r["local_callback_invocation_count"], 0)

    def test_wrong_identity_or_decision_clock_blocks_before_execution(self):
        for key, value in (("fixture_id", "other"),
                           ("decision_utc", "2026-11-23T00:53:10Z"),
                           ("score_home", 2), ("minute_elapsed", 46),
                           ("red_away", True)):
            case, snap, out = sample()
            snap[key] = value
            called = []
            def fn(arg):
                called.append(True)
                return out
            r = observe_local(case, snap, fn)
            self.assertEqual(r["status"], "HOLD")
            self.assertEqual(called, [])

    def test_bad_prematch_cutoff_blocks_before_execution(self):
        case, snap, out = sample()
        snap["prematch"]["forecast_utc"] = "2026-11-23T00:01:00Z"
        calls = []
        def fn(arg):
            calls.append(True)
            return out
        self.assertEqual(observe_local(case, snap, fn)["status"], "HOLD")
        self.assertEqual(calls, [])

    def test_forged_challenger_output_is_rejected_after_actual_call(self):
        case, snap, out = sample()
        out["fulltime_probabilities"]["HOME"] = .9
        calls = []
        def fn(arg):
            calls.append(True)
            return copy.deepcopy(out)
        r = observe_local(case, snap, fn)
        self.assertEqual(calls, [True])
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["local_callback_invocation_count"], 1)
        self.assertIsNone(r["output_sha256_unattested"])

    def test_input_mutation_rejected_and_original_preserved(self):
        case, snap, out = sample()
        original = copy.deepcopy(snap)
        def fn(arg):
            arg["score_home"] = 18
            return copy.deepcopy(out)
        r = observe_local(case, snap, fn)
        self.assertEqual(r["reason"], "CALLBACK_MUTATED_INPUT")
        self.assertEqual(snap, original)

    def test_exception_message_not_exposed(self):
        case, snap, out = sample()
        def fn(arg):
            raise RuntimeError("SECRET_DO_NOT_LOG_123")
        r = observe_local(case, snap, fn)
        self.assertEqual(r["reason"], "CALLBACK_FAILED")
        self.assertNotIn("SECRET_DO_NOT_LOG_123", str(r))

    def test_missing_trusted_time_or_result_injected_never_certifies(self):
        case, snap, out = sample()
        snap["final_result"] = "2-2"
        called = []
        def fn(arg):
            called.append(True)
            return out
        self.assertEqual(observe_local(case, snap, fn)["status"], "HOLD")
        self.assertEqual(called, [])

    def test_non_dict_and_unserializable_outputs_rejected(self):
        case, snap, out = sample()
        for output in (None, "foo", {"unexpected": {3,4}}):
            def fn(arg):
                return output
            self.assertEqual(observe_local(case, snap, fn)["status"], "HOLD")

    def test_no_double_invocation_for_callback_returned_hold(self):
        case, snap, out = sample()
        calls = []
        def fn(arg):
            calls.append(1)
            return {"status": "HOLD", "reason": "NOT_READY"}
        r = observe_local(case, snap, fn)
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
