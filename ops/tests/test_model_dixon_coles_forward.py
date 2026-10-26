"""The fixed research candidate must be captured now without rewriting A/B/C."""
import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_dixon_coles_forward import (
    MODEL, PROTOCOL, PROTOCOL_SHA256, TOP_KEY, build, publish,
)
from retrospective_dixon_coles import probabilities
from shadow_forecast import poisson_1x2

NOW = datetime(2026, 10, 27, 8, 31, 34, tzinfo=timezone.utc)
SOURCE = NOW - timedelta(seconds=34)


def fixture():
    original = poisson_1x2(1.234564321, .987654321)
    return {"league": "epl", "event_id": "source:42", "home": "Liverpool",
            "away": "Arsenal", "kickoff_utc": (NOW+timedelta(hours=2)).isoformat(),
            "prediction_utc": SOURCE.isoformat(),
            "model": "poisson-shrinkage-unvalidated-v4.1",
            "training_games": 80, "training_cutoff_local_day": "2026-10-26",
            "training_observations_sha256": "a"*64,
            "expected_home_goals": 1.23456, "expected_away_goals": .98765,
            "p_home": original[0], "p_draw": original[1], "p_away": original[2],
            "ab_model": "unchanged-B", "ab_candidate_p_home": .407,
            "production_recommendations": "DISABLED"}


def shadow(rows=None):
    rows = [fixture()] if rows is None else rows
    return {"schema": "football-king-uncalibrated-shadow-1",
            "as_of_utc": SOURCE.isoformat(),
            "status": "SHADOW_ONLY" if rows else "HOLD",
            "predictions_count": len(rows), "predictions": rows,
            "production_recommendations": "DISABLED",
            "ab_model": "unchanged-B", "ab_experiment": "SHADOW_ONLY"}


class ForwardDixonColesTests(unittest.TestCase):
    def test_fixed_protocol_and_separate_probability_capture(self):
        doc = shadow(); before = copy.deepcopy(doc)
        report = build(doc, now=NOW)
        self.assertEqual(doc, before)
        self.assertEqual(report["status"], "FORWARD_RESEARCH_CAPTURE_ONLY")
        self.assertEqual(report["model_id"], MODEL)
        self.assertEqual(report["frozen_rho"], -.05)
        self.assertEqual(report["predictions_count"], 1)
        self.assertEqual(report["protocol_sha256"], PROTOCOL_SHA256)
        self.assertEqual(hashlib.sha256(json.dumps(PROTOCOL, sort_keys=True,
                            separators=(",", ":"), ensure_ascii=False,
                            allow_nan=False).encode()).hexdigest(), PROTOCOL_SHA256)
        self.assertEqual(PROTOCOL["effective_from_utc"], "2026-10-26T08:30:34+00:00")
        self.assertEqual(report["source_report_sha256"],
                         "ab9114b156992162409a32cb24d292a0b82d49b2833cee4369ea1ca599790dba")
        case = report["predictions"][0]
        self.assertEqual(case["original"], [fixture()[k] for k in ("p_home", "p_draw", "p_away")])
        self.assertEqual(case["derived_rho0"], probabilities(1.23456, .98765, 0))
        self.assertEqual(case["candidate"], probabilities(1.23456, .98765, -.05))
        self.assertEqual(case["prediction_utc"], NOW.isoformat())
        self.assertEqual(case["candidate_generated_utc"], NOW.isoformat())
        self.assertEqual(case["source_prediction_utc"], SOURCE.isoformat())
        self.assertNotEqual(case["prediction_utc"], case["source_prediction_utc"])
        self.assertEqual(len(case["source_projection_sha256"]), 64)
        self.assertNotIn("kickoff_utc", case)
        self.assertEqual(case["kickoff_utc_recorded"], fixture()["kickoff_utc"])
        self.assertFalse(report["independently_verified_prematch_capture"])
        self.assertFalse(report["candidate_witness_time_verified"])
        self.assertFalse(report["actual_kickoff_independently_verified"])
        self.assertFalse(report["prospective_qualification_verified"])
        self.assertFalse(report["automatic_model_promotion"])
        self.assertEqual(report["production_recommendations"], "DISABLED")
        json.dumps(report, allow_nan=False)

    def test_own_clock_lead_source_freshness_and_protocol_lower_bound(self):
        for seconds, accepted in ((599, False), (600, False), (601, True)):
            doc = shadow(); doc["predictions"][0]["kickoff_utc"] = (NOW+timedelta(seconds=seconds)).isoformat()
            self.assertEqual(build(doc, now=NOW)["predictions_count"], int(accepted))
        old = shadow(); old["as_of_utc"] = (NOW-timedelta(hours=10)).isoformat()
        old["predictions"][0]["prediction_utc"] = old["as_of_utc"]
        self.assertEqual(build(old, now=NOW)["predictions_count"], 1)
        old["as_of_utc"] = (NOW-timedelta(hours=10, microseconds=1)).isoformat()
        old["predictions"][0]["prediction_utc"] = old["as_of_utc"]
        self.assertEqual(build(old, now=NOW)["status"], "HOLD")
        self.assertEqual(build(shadow(), now=NOW-timedelta(hours=1))["status"], "HOLD")
        before = shadow(); before["as_of_utc"] = "2026-10-26T08:30:33+00:00"
        before["predictions"][0].update(prediction_utc=before["as_of_utc"],
                                        training_cutoff_local_day="2026-10-25")
        fresh_now = datetime(2026, 10, 26, 8, 31, 34, tzinfo=timezone.utc)
        result = build(before, now=fresh_now)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["source_problem"], "SOURCE_BEFORE_PROTOCOL_OR_STALE_OR_FUTURE")
        before["as_of_utc"] = "2026-10-26T08:30:32+00:00"
        before["predictions"][0]["prediction_utc"] = before["as_of_utc"]
        result = build(before, now=datetime(2026, 10, 26, 8, 30, 33, tzinfo=timezone.utc))
        self.assertEqual(result["source_problem"], "BEFORE_PROTOCOL_EFFECTIVE_FROM")
        future = shadow(); future["as_of_utc"] = (NOW+timedelta(microseconds=1)).isoformat()
        self.assertEqual(build(future, now=NOW)["status"], "HOLD")

    def test_explicit_invalid_clock_does_not_fall_back_to_now(self):
        for bad in (False, True, 0, "", "2026-10-26T08:31:34Z", datetime(2026, 10, 26)):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(ValueError): build(shadow(), now=bad)
        offset = NOW.astimezone(timezone(timedelta(hours=8)))
        self.assertEqual(build(shadow(), now=offset), build(shadow(), now=NOW))

    def test_invalid_source_document_is_hold_without_guessing(self):
        for key, value in (("schema", "other"), ("status", "HOLD"),
                           ("production_recommendations", "ENABLED"),
                           ("predictions_count", True), ("predictions_count", 2),
                           ("predictions", {}), ("as_of_utc", "2026-10-26T08:31:00")):
            doc = shadow(); doc[key] = value
            with self.subTest(key=key):
                self.assertEqual(build(doc, now=NOW)["status"], "HOLD")
        for doc in (None, [], {}, shadow([])):
            self.assertEqual(build(doc, now=NOW)["predictions_count"], 0)

    def test_bad_rates_probabilities_training_and_labels_are_excluded(self):
        bad_fields = [("expected_home_goals", v) for v in
                      (True, "1.2", .09999, 5.50001, 1.123456, float("nan"), 10**1000)]
        bad_fields += [("p_home", True), ("p_home", float("inf")),
                       ("p_home", .99), ("training_games", True),
                       ("training_games", 29), ("training_cutoff_local_day", "2026-10-27"),
                       ("training_observations_sha256", "no"), ("model", "changed"),
                       ("production_recommendations", "ENABLED"), ("score_ft", [1, 0]),
                       ("result", 0), ("historical_outcome", False), ("y", 1),
                       ("status", "FINISHED"), ("event_id", True),
                       ("home", "Arsenal"), ("kickoff_utc", None)]
        for key, value in bad_fields:
            case = fixture(); case[key] = value
            with self.subTest(key=key, value=repr(value)[:60]):
                self.assertEqual(build(shadow([case]), now=NOW)["predictions_count"], 0)

    def test_exact_instant_source_clock_is_required_but_offsets_are_equivalent(self):
        doc = shadow(); doc["predictions"][0]["prediction_utc"] = (SOURCE+timedelta(microseconds=1)).isoformat()
        self.assertEqual(build(doc, now=NOW)["predictions_count"], 0)
        doc["predictions"][0]["prediction_utc"] = SOURCE.astimezone(timezone(timedelta(hours=8))).isoformat()
        self.assertEqual(build(doc, now=NOW)["predictions_count"], 1)

    def test_invalid_duplicates_poison_all_known_event_and_fixture_bindings(self):
        original = fixture()
        for kind in ("event", "fixture"):
            other = copy.deepcopy(original)
            other["expected_home_goals"] = None
            if kind == "event":
                other["home"], other["away"] = "Chelsea", "Everton"
                other["kickoff_utc"] = (NOW+timedelta(hours=3)).isoformat()
            else:
                other["event_id"] = "different-id"
                other["home"] = "Liverpool FC"
                other["kickoff_utc"] = datetime.fromisoformat(original["kickoff_utc"]).astimezone(timezone(timedelta(hours=8))).isoformat()
            for rows in ([original, other], [other, original]):
                with self.subTest(kind=kind):
                    result = build(shadow(rows), now=NOW)
                    self.assertEqual(result["predictions_count"], 0)
                    self.assertEqual(result["exclusions"]["AMBIGUOUS_SOURCE_IDENTITY"], 2)

    def test_malformed_source_ids_are_rejected_without_trimming_or_normalizing(self):
        class StringSubclass(str):
            pass
        for bad in (" source:42", "source:42 ", "\tsource:42", "source:42\n",
                    "source:\t42", "source:\n42", "source:\x0042", "source:\x7f42",
                    "", " "*2, "x"*513, True, 42, None, [], b"source:42",
                    StringSubclass("source:42")):
            with self.subTest(value=repr(bad)[:70]):
                case = fixture(); case["event_id"] = bad
                result = build(shadow([case]), now=NOW)
                self.assertEqual(result["predictions_count"], 0)
                self.assertEqual(result["status"], "HOLD")

    def test_valid_provider_and_fallback_ids_are_preserved_exactly(self):
        for event_id in ("openligadb:12345", "epl|2026-10-29|Manchester City|Arsenal"):
            case = fixture(); case["event_id"] = event_id
            result = build(shadow([case]), now=NOW)
            self.assertEqual(result["predictions_count"], 1)
            self.assertEqual(result["predictions"][0]["event_id"], event_id)

    def test_independent_leagues_and_other_valid_fixtures_survive_quarantine(self):
        first, duplicate, safe = fixture(), fixture(), fixture()
        duplicate["p_home"] = False
        safe.update(event_id="safe", home="Chelsea", away="Everton")
        result = build(shadow([first, duplicate, safe]), now=NOW)
        self.assertEqual([r["event_id"] for r in result["predictions"]], ["safe"])
        alternate = fixture(); alternate.update(league="championship", event_id="other-league")
        result = build(shadow([fixture(), alternate]), now=NOW)
        self.assertEqual(result["predictions_count"], 2)
        alternate["event_id"] = fixture()["event_id"]
        self.assertEqual(build(shadow([fixture(), alternate]), now=NOW)["predictions_count"], 0)

    def test_projection_hash_covers_used_values_and_does_not_alias_input(self):
        doc = shadow(); first = build(doc, now=NOW)
        doc["predictions"][0]["expected_home_goals"] = 1.34567
        p = poisson_1x2(1.34567, .98765)
        for key, value in zip(("p_home", "p_draw", "p_away"), p):
            doc["predictions"][0][key] = value
        second = build(doc, now=NOW)
        self.assertNotEqual(first["predictions"][0]["source_projection_sha256"],
                            second["predictions"][0]["source_projection_sha256"])
        first["protocol"]["rho"] = .025
        first["predictions"][0]["original"][0] = 0
        self.assertEqual(build(shadow(), now=NOW)["frozen_rho"], -.05)
        self.assertEqual(shadow()["predictions"][0]["p_home"], fixture()["p_home"])

    def test_original_rate_rounding_coherence_is_a_bound_not_authentication(self):
        accepted = build(shadow(), now=NOW)
        self.assertLessEqual(accepted["maximum_original_rho0_probability_difference"], .000011)
        self.assertEqual(accepted["original_rho0_argmax_disagreements"], 0)
        inconsistent = fixture()
        inconsistent.update(p_home=.7, p_draw=.2, p_away=.1)
        rejected = build(shadow([inconsistent]), now=NOW)
        self.assertEqual(rejected["predictions_count"], 0)
        self.assertEqual(rejected["exclusions"], {"ORIGINAL_RATE_PROBABILITY_INCOHERENCE": 1})

    def test_frozen_protocol_and_probability_implementation_cannot_silently_change(self):
        with patch.dict(PROTOCOL, {"rho": -.1}):
            changed = build(shadow(), now=NOW)
            self.assertEqual(changed["source_problem"], "FROZEN_PROTOCOL_DIGEST_MISMATCH")
            self.assertEqual(changed["predictions_count"], 0)
        with patch("model_dixon_coles_forward.EXPECTED_IMPLEMENTATION_SHA256", "0"*64):
            changed = build(shadow(), now=NOW)
            self.assertEqual(changed["predictions_count"], 0)
        with patch("model_dixon_coles_forward._implementation_matches", return_value=False):
            changed = build(shadow(), now=NOW)
            self.assertEqual(changed["source_problem"], "FROZEN_PROBABILITY_IMPLEMENTATION_MISMATCH")
        self.assertEqual(build(shadow(), now=NOW)["predictions_count"], 1)

    def test_default_clock_is_read_after_maths_and_expired_lead_is_excluded(self):
        for duration in (1, 2):
            doc = shadow()
            doc["predictions"][0]["kickoff_utc"] = (NOW+timedelta(seconds=601)).isoformat()
            with patch("model_dixon_coles_forward.datetime") as clock:
                clock.now.return_value = NOW
                clock.fromisoformat.side_effect = datetime.fromisoformat
                def delayed(*args):
                    clock.now.return_value = NOW+timedelta(seconds=duration)
                    return probabilities(*args)
                with patch("model_dixon_coles_forward.probabilities", side_effect=delayed):
                    report = build(doc)
                self.assertEqual(report["predictions_count"], 0)
                self.assertEqual(report["generated_utc"], (NOW+timedelta(seconds=duration)).isoformat())
                self.assertEqual(report["exclusions"]["INSUFFICIENT_OWN_CLOCK_KICKOFF_LEAD"], 1)
                with patch("model_dixon_coles_forward.probabilities", side_effect=delayed):
                    fixed = build(doc, now=NOW)
                self.assertEqual(fixed["predictions_count"], 1)
                self.assertEqual(fixed["generated_utc"], NOW.isoformat())

    def test_default_completion_crosses_source_age_limit_or_rewinds_fail_closed(self):
        doc = shadow()
        doc["as_of_utc"] = (NOW-timedelta(hours=10)+timedelta(seconds=1)).isoformat()
        doc["predictions"][0]["prediction_utc"] = doc["as_of_utc"]
        with patch("model_dixon_coles_forward.datetime") as clock:
            clock.now.side_effect = [NOW, NOW+timedelta(seconds=2)]
            clock.fromisoformat.side_effect = datetime.fromisoformat
            report = build(doc)
        self.assertEqual(report["predictions_count"], 0)
        self.assertEqual(report["source_problem"], "SOURCE_CLOCK_INVALID_AT_COMPLETION")
        with patch("model_dixon_coles_forward.datetime") as clock:
            clock.now.side_effect = [NOW, NOW-timedelta(microseconds=1)]
            clock.fromisoformat.side_effect = datetime.fromisoformat
            report = build(shadow())
        self.assertEqual(report["predictions_count"], 0)
        self.assertEqual(report["source_problem"], "CAPTURE_CLOCK_REWOUND")

    def test_default_completion_stamp_normalizes_offset_aware_clock(self):
        offset = timezone(timedelta(hours=8))
        end = NOW+timedelta(seconds=3)
        with patch("model_dixon_coles_forward.datetime") as clock:
            clock.now.side_effect = [NOW.astimezone(offset), end.astimezone(offset)]
            clock.fromisoformat.side_effect = datetime.fromisoformat
            report = build(shadow())
        self.assertEqual(report["generated_utc"], end.isoformat())
        self.assertEqual(report["predictions"][0]["prediction_utc"], end.isoformat())


class ForwardDixonColesPublishTests(unittest.TestCase):
    def test_publisher_changes_only_new_root_key_and_refuses_recreation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"shadow.json"; original = shadow()
            path.write_text(json.dumps(original))
            result = publish(folder, now=NOW)
            saved = json.loads(path.read_text())
            self.assertEqual(saved.pop(TOP_KEY), result)
            self.assertEqual(saved, original)
            before = path.read_bytes()
            with self.assertRaises(ValueError): publish(folder, now=NOW+timedelta(minutes=1))
            self.assertEqual(path.read_bytes(), before)

    def test_publish_rejects_duplicate_json_nonfinite_large_and_populated_key(self):
        values = ['{"predictions":[],"predictions":[]}', '{"x":NaN}',
                  '{"x":Infinity}', ' '*8_000_001]
        doc = shadow(); doc[TOP_KEY] = None; values.append(json.dumps(doc))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"shadow.json"
            for raw in values:
                path.write_text(raw)
                with self.assertRaises(ValueError): publish(folder, now=NOW)
                self.assertEqual(path.read_text(), raw)

    def test_default_publish_uses_real_utc_clock(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"shadow.json"; path.write_text(json.dumps(shadow()))
            with patch("model_dixon_coles_forward.datetime") as clock:
                clock.now.return_value = NOW
                clock.fromisoformat.side_effect = datetime.fromisoformat
                result = publish(folder)
                self.assertEqual(clock.now.call_count, 2)
                self.assertTrue(all(call.args == (timezone.utc,) for call in clock.now.call_args_list))
            self.assertEqual(result["generated_utc"], NOW.isoformat())

    def test_atomic_publisher_preserves_source_after_staging_or_replace_failure(self):
        real_fdopen = os.fdopen
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"shadow.json"; path.write_text(json.dumps(shadow()))
            before = path.read_bytes()
            def broken_writer(fd, *args, **kwargs):
                stream = real_fdopen(fd, *args, **kwargs)
                class Broken:
                    def __enter__(self): return self
                    def __exit__(self, *_): stream.close()
                    def write(self, payload):
                        stream.write(payload[:10])
                        raise OSError("simulated incomplete staging write")
                return Broken()
            with patch("model_dixon_coles_forward.os.fdopen", side_effect=broken_writer):
                with self.assertRaises(OSError): publish(folder, now=NOW)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual([p.name for p in Path(folder).iterdir()], ["shadow.json"])
            with patch("model_dixon_coles_forward.os.replace", side_effect=OSError("simulated replace failure")):
                with self.assertRaises(OSError): publish(folder, now=NOW)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual([p.name for p in Path(folder).iterdir()], ["shadow.json"])

    def test_publisher_refuses_symlink_and_nonregular_source(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/"original.json"; target.write_text(json.dumps(shadow()))
            path = Path(folder)/"shadow.json"; path.symlink_to(target)
            before = target.read_bytes()
            with self.assertRaises(ValueError): publish(folder, now=NOW)
            self.assertEqual(target.read_bytes(), before)
            path.unlink(); path.mkdir()
            with self.assertRaises(ValueError): publish(folder, now=NOW)


if __name__ == "__main__":
    unittest.main()
