"""Synthetic clocks expose backdating; these fixtures are not football evidence."""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import shadow_forecast as forecast


class MutableDatetime(datetime):
    current = None
    reads = 0

    @classmethod
    def now(cls, tz=None):
        cls.reads += 1
        if cls.current is None:
            raise AssertionError("offline prediction unexpectedly read wallclock")
        return cls.current.astimezone(tz or timezone.utc)


def source_rows(start, kickoff):
    history = []
    teams = ("A", "B", "C", "D", "E", "F")
    for index in range(48):
        history.append({
            "date": (start.astimezone(forecast.HK).date() - timedelta(days=index+1)).isoformat(),
            "home": teams[index % 6], "away": teams[(index+1) % 6],
            "score_ft": [1 + index % 2, index % 3], "status": "FINISHED",
            "kickoff_utc": None,
        })
    return history + [{
        "date": kickoff.astimezone(forecast.HK).date().isoformat(),
        "home": "A", "away": "B", "score_ft": None,
        "status": "SCHEDULED", "event_id": "synthetic-clock-fixture",
        "kickoff_utc": kickoff.isoformat(),
    }]


class ShadowForecastCompletionClockTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 26, 10, tzinfo=timezone.utc)
        MutableDatetime.current, MutableDatetime.reads = self.start, 0
        self.addCleanup(setattr, MutableDatetime, "current", None)
        self.leagues = patch.object(forecast, "LEAGUES", ("epl",))
        self.leagues.start()
        self.addCleanup(self.leagues.stop)

    def getter(self, rows, completed=None, observed=None):
        def get(**kwargs):
            if observed is not None:
                observed.append(kwargs["clock"]())
            if completed is not None:
                MutableDatetime.current = completed
            if observed is not None:
                observed.append(kwargs["clock"]())
            return {"status": "READY_RESEARCH", "matches": copy.deepcopy(rows),
                    "source": "synthetic", "source_url": "https://example.invalid/fixture",
                    "captured_utc": MutableDatetime.current.isoformat()
                    if MutableDatetime.current is not None else self.start.isoformat()}
        return get

    def generate(self, getter, **kwargs):
        with patch.object(forecast, "datetime", MutableDatetime):
            return forecast.generate(getter=getter, **kwargs)

    def assert_safe(self, output):
        self.assertEqual(output["production_recommendations"], "DISABLED")
        self.assertIs(output["model_calibrated"], False)
        self.assertIs(output["independently_verified_results"], False)
        self.assertEqual(output["predictions_count"], len(output["predictions"]))
        self.assertEqual(sum(row["predictions"] for row in output["sources"]),
                         output["predictions_count"])

    def test_slow_getter_cannot_backdate_a_prediction_after_kickoff(self):
        kickoff = self.start + timedelta(minutes=11)
        completed = kickoff + timedelta(seconds=1)
        output = self.generate(self.getter(source_rows(self.start, kickoff), completed))
        self.assertEqual(output["as_of_utc"], completed.isoformat())
        self.assertEqual(output["predictions"], [])
        self.assertEqual(output["status"], "HOLD")
        self.assert_safe(output)

    def test_retained_forecast_changes_clock_without_changing_model_math(self):
        kickoff = self.start + timedelta(hours=3)
        rows = source_rows(self.start, kickoff)
        baseline = forecast.generate(now=self.start, getter=self.getter(rows))
        completed = self.start + timedelta(seconds=37)
        output = self.generate(self.getter(rows, completed))
        self.assertEqual(output["as_of_utc"], completed.isoformat())
        self.assertEqual(len(output["predictions"]), 1)
        row = copy.deepcopy(output["predictions"][0])
        self.assertEqual(row.pop("prediction_utc"), completed.isoformat())
        old = copy.deepcopy(baseline["predictions"][0]); old.pop("prediction_utc")
        self.assertEqual(row, old)
        self.assert_safe(output)

    def test_live_getter_clock_advances_during_the_response(self):
        completed = self.start + timedelta(seconds=29)
        observed = []
        output = self.generate(self.getter(source_rows(self.start, self.start+timedelta(hours=3)),
                                          completed, observed))
        self.assertEqual(observed, [self.start, completed])
        self.assertEqual(output["as_of_utc"], completed.isoformat())

    def test_explicit_offline_clock_is_fixed_and_never_reads_wallclock(self):
        rows = source_rows(self.start, self.start+timedelta(hours=3))
        baseline = forecast.generate(now=self.start, getter=self.getter(rows))
        MutableDatetime.current = None
        observed = []
        output = self.generate(self.getter(rows, observed=observed), now=self.start,
                               return_finished=False)
        self.assertEqual(MutableDatetime.reads, 0)
        self.assertEqual(observed, [self.start, self.start])
        self.assertEqual(output, baseline)

    def test_final_buffer_is_strict_at_600_and_keeps_601_seconds(self):
        kickoff = self.start+timedelta(seconds=660)
        rows = source_rows(self.start, kickoff)
        for lead, expected in ((600, 0), (601, 1)):
            with self.subTest(lead=lead):
                MutableDatetime.current = self.start
                completed = kickoff-timedelta(seconds=lead)
                output = self.generate(self.getter(rows, completed))
                self.assertEqual(output["as_of_utc"], completed.isoformat())
                self.assertEqual(output["predictions_count"], expected)
                self.assert_safe(output)

    def test_completion_clock_includes_final_league_model_computation(self):
        completed = self.start+timedelta(seconds=13)
        rows = source_rows(self.start, self.start+timedelta(hours=3))
        original = forecast.predict_league
        def slow_math(*args, **kwargs):
            result = original(*args, **kwargs)
            MutableDatetime.current = completed
            return result
        with patch.object(forecast, "predict_league", side_effect=slow_math):
            output = self.generate(self.getter(rows))
        self.assertEqual(output["as_of_utc"], completed.isoformat())
        self.assertEqual(output["predictions"][0]["prediction_utc"], completed.isoformat())

    def test_hk_midnight_during_default_batch_holds_without_finished_inputs(self):
        for start in (datetime(2026, 10, 26, 15, 59, 50, tzinfo=timezone.utc),
                      datetime(2026, 6, 30, 15, 59, 50, tzinfo=timezone.utc)):
            with self.subTest(start=start):
                MutableDatetime.current = start
                completed = start+timedelta(seconds=20)
                rows = source_rows(start, start+timedelta(hours=3))
                output = self.generate(self.getter(rows, completed), return_finished=True)
                self.assertEqual(output["as_of_utc"], completed.isoformat())
                self.assertEqual(output["status"], "HOLD")
                self.assertEqual(output["predictions"], [])
                self.assertEqual(output["_internal_finished_results"]["records"], [])
                self.assert_safe(output)

    def test_backwards_default_clock_holds_without_finished_inputs(self):
        rows = source_rows(self.start, self.start+timedelta(hours=3))
        completed = self.start-timedelta(seconds=1)
        output = self.generate(self.getter(rows, completed), return_finished=True)
        self.assertEqual(output["status"], "HOLD")
        self.assertEqual(output["predictions"], [])
        self.assertEqual(output["_internal_finished_results"]["records"], [])
        self.assert_safe(output)

    def test_finished_input_clock_records_completion_and_remains_unverified(self):
        completed = self.start+timedelta(seconds=17)
        output = self.generate(self.getter(source_rows(self.start, self.start+timedelta(hours=3)),
                                          completed), return_finished=True)
        internal = output["_internal_finished_results"]
        self.assertEqual(internal["captured_utc"], completed.isoformat())
        self.assertEqual(len(internal["records"]), 48)
        self.assertIs(internal["independently_verified_all_leagues"], False)
        self.assertEqual(internal["production_recommendations"], "DISABLED")
        self.assert_safe(output)

    def test_sampled_forward_then_rewind_cannot_recover_by_finishing_after_start(self):
        rows = source_rows(self.start, self.start+timedelta(hours=3))
        def getter(**kwargs):
            MutableDatetime.current = self.start+timedelta(seconds=5)
            kwargs["clock"]()
            MutableDatetime.current = self.start+timedelta(seconds=4)
            kwargs["clock"]()
            MutableDatetime.current = self.start+timedelta(seconds=6)
            return {"status": "READY_RESEARCH", "matches": rows}
        output = self.generate(getter, return_finished=True)
        self.assertEqual(output["as_of_utc"], (self.start+timedelta(seconds=6)).isoformat())
        self.assertEqual(output["status"], "HOLD")
        self.assertEqual(output["predictions"], [])
        self.assertEqual(output["_internal_finished_results"]["records"], [])
        self.assertIs(output["generation_clock"]["sampled_clock_order_and_hk_day_valid"], False)
        self.assert_safe(output)

    def test_sampled_hk_day_change_stays_invalid_after_returning_to_original_day(self):
        start = datetime(2026, 10, 26, 15, 59, 59, tzinfo=timezone.utc)
        MutableDatetime.current = start
        rows = source_rows(start, start+timedelta(hours=3))
        def getter(**kwargs):
            MutableDatetime.current = start+timedelta(seconds=1)
            kwargs["clock"]()
            MutableDatetime.current = start+timedelta(microseconds=500000)
            kwargs["clock"]()
            return {"status": "READY_RESEARCH", "matches": rows}
        output = self.generate(getter, return_finished=True)
        self.assertEqual(output["status"], "HOLD")
        self.assertEqual(output["predictions"], [])
        self.assertEqual(output["_internal_finished_results"]["records"], [])
        self.assertIs(output["generation_clock"]["sampled_clock_order_and_hk_day_valid"], False)
        self.assert_safe(output)

    def test_last_getter_failure_still_advances_prior_forecasts_and_refilters_them(self):
        near = self.start+timedelta(seconds=660)
        far = self.start+timedelta(hours=3)
        rows = source_rows(self.start, near)
        far_row = copy.deepcopy(rows[-1])
        far_row.update(event_id="synthetic-far-fixture", kickoff_utc=far.isoformat())
        rows.append(far_row)
        completed = self.start+timedelta(seconds=120)
        def getter(**kwargs):
            if kwargs["league"] == "laliga":
                MutableDatetime.current = completed
                raise OSError("synthetic source outage")
            return {"status": "READY_RESEARCH", "matches": copy.deepcopy(rows),
                    "captured_utc": self.start.isoformat()}
        with patch.object(forecast, "LEAGUES", ("epl", "laliga")):
            output = self.generate(getter)
        self.assertEqual(output["as_of_utc"], completed.isoformat())
        self.assertEqual([row["event_id"] for row in output["predictions"]],
                         ["synthetic-far-fixture"])
        self.assertEqual(output["predictions"][0]["prediction_utc"], completed.isoformat())
        self.assertEqual(output["sources"][1]["status"], "HOLD")
        self.assert_safe(output)

    def test_explicit_offset_clock_keeps_exact_offline_output_and_callback_offset(self):
        fixed = self.start.astimezone(timezone(timedelta(hours=8)))
        rows = source_rows(self.start, self.start+timedelta(hours=3))
        baseline = forecast.generate(now=fixed, getter=self.getter(rows))
        MutableDatetime.current = None
        observed = []
        output = self.generate(self.getter(rows, observed=observed), now=fixed)
        self.assertEqual(output, baseline)
        self.assertEqual(output["as_of_utc"], fixed.isoformat())
        self.assertEqual(output["predictions"][0]["prediction_utc"], fixed.isoformat())
        self.assertEqual([value.isoformat() for value in observed], [fixed.isoformat()]*2)
        self.assertEqual(MutableDatetime.reads, 0)
        self.assertNotIn("generation_clock", output)

    def test_invalid_explicit_clocks_fail_before_any_source_request(self):
        def forbidden_getter(**kwargs):
            self.fail("invalid clock reached a source request")
        for fixed in (True, False, 0, 1, "", "2026-10-26", self.start.replace(tzinfo=None)):
            with self.subTest(clock=fixed), self.assertRaises(ValueError):
                self.generate(forbidden_getter, now=fixed)
        self.assertEqual(MutableDatetime.reads, 0)

    def test_original_source_capture_claim_is_not_relabelled_as_completion(self):
        claimed_capture = self.start-timedelta(minutes=3)
        completed = self.start+timedelta(seconds=17)
        rows = source_rows(self.start, self.start+timedelta(hours=3))
        def getter(**kwargs):
            MutableDatetime.current = completed
            return {"status": "READY_RESEARCH", "matches": rows,
                    "captured_utc": claimed_capture.isoformat()}
        output = self.generate(getter, return_finished=True)
        self.assertEqual(output["as_of_utc"], completed.isoformat())
        self.assertEqual(output["sources"][0]["captured_utc"], claimed_capture.isoformat())
        self.assertIs(output["generation_clock"]["source_capture_or_actual_kickoff_authenticated"], False)
        self.assert_safe(output)

    def test_real_enrichment_expiring_at_16_hours_rejects_without_recomputing_math(self):
        # Exercise the real enrichment module with its existing allowed-team
        # schema. Each source is individually still fresh at entry and stale
        # at completion; prices/probabilities are never model inputs.
        import test_schedule_enrichment as enrichment_fixture
        for expiring in ("secondary", "market"):
            with self.subTest(expiring=expiring):
                fixture = enrichment_fixture.SafeScheduleEnrichmentTests()
                fixture.setUp()
                start = fixture.now
                MutableDatetime.current = start
                completed = start+timedelta(seconds=2)
                stale_at_completion = (start-timedelta(hours=16)+timedelta(seconds=1)).isoformat()
                if expiring == "secondary":
                    fixture.audit["collected_utc"] = stale_at_completion
                else:
                    fixture.market["as_of_utc"] = stale_at_completion
                    fixture.market["events"][0]["market_last_update_utc"] = stale_at_completion
                before = copy.deepcopy((fixture.rows, fixture.audit, fixture.market))
                baseline = forecast.generate(now=start, getter=self.getter(fixture.rows),
                    secondary_snapshot=fixture.audit, market_schedule=fixture.market)
                self.assertEqual(baseline["predictions_count"], 1)
                with patch.object(forecast, "poisson_1x2", wraps=forecast.poisson_1x2) as math_call:
                    output = self.generate(self.getter(fixture.rows, completed),
                        secondary_snapshot=fixture.audit, market_schedule=fixture.market)
                self.assertEqual(math_call.call_count, 1)
                self.assertEqual(output["as_of_utc"], completed.isoformat())
                self.assertEqual(output["predictions"], [])
                self.assertEqual(output["status"], "HOLD")
                self.assertEqual(output["sources"][0]["reason"],
                                 "ENRICHMENT_CONTEXT_CHANGED_AT_COMPLETION")
                self.assertEqual((fixture.rows, fixture.audit, fixture.market), before)
                self.assert_safe(output)

    def test_new_completion_clock_passes_fixed_challenger_source_binding(self):
        from model_ab import apply as add_b
        import model_dixon_coles_forward as challenger
        completed = self.start+timedelta(seconds=21)
        # D's producer validates fixed source identity and known team aliases.
        rows = source_rows(self.start, self.start+timedelta(hours=3))
        for row in rows:
            for role in ("home", "away"):
                row[role] = {"A": "Arsenal FC", "B": "Chelsea FC", "C": "Liverpool FC",
                             "D": "Everton FC", "E": "Fulham FC", "F": "Aston Villa FC"}[row[role]]
        output = self.generate(self.getter(rows, completed))
        original = copy.deepcopy(output["predictions"][0])
        add_b(output)
        captured = challenger.build(output, now=completed+timedelta(seconds=1))
        self.assertEqual(captured["predictions_count"], 1)
        case = captured["predictions"][0]
        self.assertEqual(case["source_prediction_utc"], completed.isoformat())
        self.assertEqual(case["candidate_generated_utc"],
                         (completed+timedelta(seconds=1)).isoformat())
        self.assertEqual(case["original"], [original[key] for key in ("p_home", "p_draw", "p_away")])
        self.assertEqual(case["training_observations_sha256"], original["training_observations_sha256"])
        self.assertIs(captured["automatic_model_promotion"], False)
        self.assertEqual(captured["production_recommendations"], "DISABLED")
        self.assertIs(output["independently_verified_results"], False)

    def test_enrichment_revalidation_latency_is_included_in_final_prediction_clock(self):
        import schedule_enrichment as schedule
        completed = self.start+timedelta(seconds=2)
        secondary = {"schema": "football-king-extra-source-audit-v1",
                     "status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
                     "collected_utc": self.start.isoformat(), "providers": [],
                     "sampled_fixtures": []}
        market = {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
                  "as_of_utc": self.start.isoformat(), "events": []}
        normal_diag = schedule.enrich([], "epl", secondary, market, self.start)[1]
        for kickoff, retained in ((self.start+timedelta(seconds=601), 0),
                                   (self.start+timedelta(hours=3), 1)):
            with self.subTest(kickoff=kickoff):
                MutableDatetime.current = self.start
                rows = source_rows(self.start, kickoff)
                calls = []
                def slow_revalidation(data, league, audit, prices, at):
                    calls.append(at)
                    if len(calls) == 2:
                        MutableDatetime.current = completed
                    return data, copy.deepcopy(normal_diag)
                with patch.object(schedule, "enrich", side_effect=slow_revalidation):
                    output = self.generate(self.getter(rows), secondary_snapshot=secondary,
                                           market_schedule=market)
                self.assertGreaterEqual(len(calls), 2)
                self.assertEqual(output["predictions_count"], retained)
                self.assertEqual(output["as_of_utc"], completed.isoformat())
                if retained:
                    self.assertEqual(output["predictions"][0]["prediction_utc"], completed.isoformat())
                self.assert_safe(output)

    def test_real_enrichment_window_expiry_during_revalidation_rejects_the_league(self):
        import schedule_enrichment as schedule
        import test_schedule_enrichment as enrichment_fixture
        for expiring in ("secondary", "market", "minimum_kickoff_window"):
            with self.subTest(expiring=expiring):
                fixture = enrichment_fixture.SafeScheduleEnrichmentTests()
                fixture.setUp()
                start = fixture.now
                completed = start+timedelta(seconds=2)
                MutableDatetime.current = start
                stale_at_completion = (start-timedelta(hours=16)+timedelta(seconds=1)).isoformat()
                if expiring == "secondary":
                    fixture.audit["collected_utc"] = stale_at_completion
                elif expiring == "market":
                    fixture.market["as_of_utc"] = stale_at_completion
                    fixture.market["events"][0]["market_last_update_utc"] = stale_at_completion
                else:
                    kickoff = start+timedelta(seconds=3601)
                    fixture.rows[-1]["date"] = kickoff.astimezone(forecast.HK).date().isoformat()
                    fixture.audit["sampled_fixtures"][0]["kickoff_utc"] = kickoff.isoformat()
                    fixture.market["events"][0]["kickoff_utc"] = kickoff.isoformat()
                original = schedule.enrich
                calls = []
                def slow_revalidation(*args):
                    result = original(*args)
                    calls.append(args[-1])
                    if len(calls) == 2:
                        MutableDatetime.current = completed
                    return result
                with patch.object(schedule, "enrich", side_effect=slow_revalidation), \
                     patch.object(forecast, "poisson_1x2", wraps=forecast.poisson_1x2) as math_call:
                    output = self.generate(self.getter(fixture.rows),
                        secondary_snapshot=fixture.audit, market_schedule=fixture.market)
                self.assertGreaterEqual(len(calls), 2)
                self.assertEqual(math_call.call_count, 1)
                self.assertEqual(output["predictions_count"], 0)
                self.assertEqual(output["as_of_utc"], completed.isoformat())
                self.assertEqual(output["status"], "HOLD")
                self.assertEqual(output["sources"][0]["status"], "HOLD")
                self.assert_safe(output)


if __name__ == "__main__":
    unittest.main()
