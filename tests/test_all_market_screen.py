import unittest
from datetime import datetime, timezone, timedelta
from ops.all_market_screen import screen

NOW = datetime(2026, 10, 10, 10, tzinfo=timezone.utc)
def quote(**kwargs):
    q = {"fixture_id": "fixture-1", "market": "asian_handicap", "selection": "home",
         "line": -1.25, "decimal_odds": 2.1, "source": "example",
         "information_cutoff_utc": "2026-10-10T09:50:00Z",
         "observed_utc": (NOW-timedelta(minutes=2)).isoformat(),
         "kickoff_utc": (NOW+timedelta(hours=2)).isoformat()}
    q.update(kwargs)
    # Existing synthetic positive cases now carry the same precise identity
    # and an earlier model-cutoff time as their reference bookmaker quote.
    if isinstance(q.get("model_scenarios"), list):
        for entry in q["model_scenarios"]:
            if isinstance(entry, dict):
                for key in ("fixture_id", "market", "selection", "line", "kickoff_utc",
                            "information_cutoff_utc"):
                    entry.setdefault(key, q[key])
                entry.setdefault("forecast_created_utc",
                                 (NOW-timedelta(minutes=5)).isoformat())
    return q

class TestAllMarketScreen(unittest.TestCase):
    def test_capture_time_is_preserved_separately_from_source_update(self):
        captured = (NOW-timedelta(minutes=1)).isoformat()
        item = screen({"quotes": [quote(captured_utc=captured)]}, NOW)["candidates"][0]
        self.assertEqual(item["captured_utc"], captured)
        self.assertEqual(item["observed_utc"], (NOW-timedelta(minutes=2)).isoformat())
        self.assertEqual(item["status"], "RESEARCH_ONLY")

    def test_missing_probability_is_research_only(self):
        self.assertEqual(screen({"quotes": [quote()]}, NOW)["candidates"][0]["status"], "RESEARCH_ONLY")

    def test_main_and_scenario_probabilities_reject_the_same_invalid_inputs(self):
        valid = {"full_win": .4, "half_win": .2, "push": 0,
                 "half_loss": .1, "full_loss": .3}
        bad_cases = {
            "true": {"full_win": True, "half_win": 0, "push": 0,
                     "half_loss": 0, "full_loss": 0},
            "false": {**valid, "push": False},
            "extra_key": {**valid, "unexpected": 0},
            "numeric_string": {**valid, "full_win": "0.4"},
            "loose_normalization": {**valid, "full_loss": .300001},
            "missing_key": {"full_win": 1, "half_win": 0, "push": 0, "half_loss": 0},
            "null": None,
            "list": [],
            "nan": {**valid, "push": float("nan")},
            "negative": {**valid, "push": -.1},
        }
        for name, bad in bad_cases.items():
            for target in ("main", "scenario"):
                with self.subTest(case=name, target=target):
                    if target == "main":
                        q = quote(settlement_probabilities=bad)
                    else:
                        q = quote(settlement_probabilities=valid, model_scenarios=[
                            {"model_id": "a", "settlement_probabilities": valid},
                            {"model_id": "b", "settlement_probabilities": bad}])
                    report = screen({"quotes": [q]}, NOW)
                    row = report["candidates"][0]
                    self.assertEqual(row["status"], "INVALID")
                    for field in ("ev_per_unit", "scenario_ev_min", "scenario_ev_max"):
                        self.assertNotIn(field, row)
                    self.assertIs(row.get("positive_ev_verified", False), False)
                    self.assertEqual(report["counts"]["VERIFIED_VALUE"], 0)

    def test_shared_five_outcome_contract_keeps_quarter_line_ev_correct(self):
        for probabilities, expected in (
                ({"full_win": .4, "half_win": .2, "push": 0,
                  "half_loss": .1, "full_loss": .3}, .2),
                ({"full_win": 1, "half_win": 0, "push": 0,
                  "half_loss": 0, "full_loss": 0}, 1.1)):
            for market, side, line in (("asian_handicap", "home", -1.25),
                                       ("totals", "over", 2.75)):
                with self.subTest(probabilities=probabilities, market=market):
                    q = quote(market=market, selection=side, line=line,
                              settlement_probabilities=probabilities, model_scenarios=[
                                  {"model_id": "a", "settlement_probabilities": probabilities},
                                  {"model_id": "b", "settlement_probabilities": probabilities}])
                    row = screen({"quotes": [q]}, NOW)["candidates"][0]
                    self.assertEqual(row["status"], "RESEARCH_ONLY")
                    for field in ("ev_per_unit", "scenario_ev_min", "scenario_ev_max"):
                        self.assertAlmostEqual(row[field], expected)
                    self.assertFalse(row["positive_ev_verified"])

    def test_half_settlement_ev(self):
        q = quote(settlement_probabilities={"full_win": .4, "half_win": .2, "push": 0,
                                            "half_loss": .1, "full_loss": .3},
                  independently_calibrated=True, lineup_checked=True, source_verified=True)
        item = screen({"quotes": [q]}, NOW)["candidates"][0]
        self.assertAlmostEqual(item["ev_per_unit"], .2)
        self.assertEqual(item["status"], "RESEARCH_ONLY")
        self.assertEqual(item["reason"], "INDEPENDENT_CERTIFICATION_GATE_NOT_IMPLEMENTED")
    def test_self_attested_flags_never_certify(self):
        p = {"full_win": 0.51, "half_win": 0, "push": 0, "half_loss": 0, "full_loss": 0.49}
        q = quote(settlement_probabilities=p, independently_calibrated=True,
                  lineup_checked=True, source_verified=True,
                  external_validation_record_verified=True)
        result = screen({"quotes": [q]}, NOW)
        self.assertEqual(result["candidates"][0]["status"], "RESEARCH_ONLY")
        self.assertEqual(result["counts"]["VERIFIED_VALUE"], 0)

    def test_malformed_payload_is_safe(self):
        self.assertEqual(screen({"quotes": None}, NOW)["candidates"], [])
        self.assertEqual(screen(None, NOW)["candidates"], [])
        self.assertEqual(screen({"quotes": [quote(observed_utc=123)]}, NOW)["candidates"][0]["status"], "INVALID")

    def test_stale_quote(self):
        item = screen({"quotes": [quote(observed_utc=(NOW-timedelta(hours=1)).isoformat())]}, NOW)["candidates"][0]
        self.assertEqual(item["status"], "STALE")
    def test_reject_postkickoff(self):
        item = screen({"quotes": [quote(kickoff_utc=(NOW-timedelta(minutes=1)).isoformat())]}, NOW)["candidates"][0]
        self.assertEqual(item["status"], "INVALID")
    def test_all_market_types_not_filtered(self):
        q = [quote(market=m, selection=s) for m,s in [("asian_handicap","away"),("totals","over"),("totals","under"),("h2h","home"),("btts","yes")]]
        self.assertEqual(len(screen({"quotes":q}, NOW)["candidates"]), 5)


    def test_multi_model_ev_sign_conflict_not_certified(self):
        q = quote(settlement_probabilities={"full_win": .4, "half_win": .2,
                                            "push": 0, "half_loss": .1, "full_loss": .3},
                  model_scenarios=[
                      {"model_id": "shadow-A", "settlement_probabilities":
                          {"full_win": .4, "half_win": .2, "push": 0, "half_loss": .1, "full_loss": .3}},
                      {"model_id": "shadow-B", "settlement_probabilities":
                          {"full_win": .3, "half_win": .1, "push": 0, "half_loss": .1, "full_loss": .5}}],
                  source_verified=True, independently_calibrated=True)
        result = screen({"quotes": [q]}, NOW)
        row = result["candidates"][0]
        self.assertAlmostEqual(row["ev_per_unit"], .2)
        self.assertAlmostEqual(row["scenario_ev_min"], -.165)
        self.assertAlmostEqual(row["scenario_ev_max"], .2)
        self.assertEqual(row["ev_sensitivity_status"], "SCENARIO_SIGN_CONFLICT")
        self.assertFalse(row["positive_ev_verified"])
        self.assertEqual(row["status"], "RESEARCH_ONLY")
        self.assertEqual(result["counts"]["VERIFIED_VALUE"], 0)

    def test_multiple_numerically_positive_scenarios_never_certify(self):
        q = quote(settlement_probabilities={"full_win": .4, "half_win": .2,
                                            "push": 0, "half_loss": .1, "full_loss": .3},
                  model_scenarios=[
                      {"model_id": "m1", "settlement_probabilities":
                          {"full_win": .4, "half_win": .2, "push": 0, "half_loss": .1, "full_loss": .3}},
                      {"model_id": "m2", "settlement_probabilities":
                          {"full_win": .6, "half_win": .1, "push": 0, "half_loss": .1, "full_loss": .2}}])
        row = screen({"quotes": [q]}, NOW)["candidates"][0]
        self.assertEqual(row["ev_sensitivity_status"], "ALL_SUPPLIED_SCENARIOS_NUMERICALLY_POSITIVE")
        self.assertFalse(row["positive_ev_verified"])
        self.assertEqual(row["status"], "RESEARCH_ONLY")

    def test_no_scenarios_cannot_claim_robust_edge(self):
        q = quote(settlement_probabilities={"full_win": .4, "half_win": .2,
                                            "push": 0, "half_loss": .1, "full_loss": .3})
        row = screen({"quotes": [q]}, NOW)["candidates"][0]
        self.assertEqual(row["ev_sensitivity_status"], "NOT_ASSESSED")
        self.assertNotIn("scenario_ev_min", row)
        self.assertFalse(row["positive_ev_verified"])

    def test_one_scenario_is_insufficient_even_when_positive(self):
        q = quote(settlement_probabilities={"full_win": .4, "half_win": .2,
                                            "push": 0, "half_loss": .1, "full_loss": .3},
                  model_scenarios=[{"model_id": "m1",
                      "settlement_probabilities": {
                          "full_win": .8, "half_win": 0, "push": 0,
                          "half_loss": 0, "full_loss": .2}}])
        row = screen({"quotes": [q]}, NOW)["candidates"][0]
        self.assertEqual(row["ev_sensitivity_status"], "INSUFFICIENT_SCENARIOS")
        self.assertNotIn("scenario_ev_min", row)
        self.assertFalse(row["positive_ev_verified"])

    def test_invalid_scenarios_fail_closed_no_ev_claim(self):
        base = {"full_win": .4, "half_win": .2, "push": 0,
                "half_loss": .1, "full_loss": .3}
        def scenario(mid, probabilities=None):
            return {"model_id": mid, "settlement_probabilities": base if probabilities is None else probabilities}
        bad_cases = [
            [], [scenario("same"), scenario("same")],
            [scenario("a"), scenario("", base)],
            [scenario("a"), scenario("b", {**base, "full_win": True})],
            [scenario("a"), scenario("b", {**base, "full_win": float("nan")})],
            [scenario("a"), scenario("b", {**base, "full_win": .8})],
            [scenario("a"), scenario("b", {"full_win": 1})],
            [scenario("a"), "not_a_scenario"],
            "not_a_list",
        ]
        for bad in bad_cases:
            with self.subTest(bad=str(bad)[:80]):
                row = screen({"quotes": [quote(
                    settlement_probabilities=base, model_scenarios=bad)]}, NOW)["candidates"][0]
                self.assertEqual(row["status"], "INVALID")
                self.assertEqual(row["reason"], "INVALID_MODEL_SCENARIOS")
                self.assertNotIn("ev_per_unit", row)

    def test_all_negative_scenarios_cannot_be_promoted(self):
        p = {"full_win": .2, "half_win": .1, "push": 0, "half_loss": .1, "full_loss": .6}
        q = quote(settlement_probabilities=p, model_scenarios=[
            {"model_id": "m1", "settlement_probabilities": p},
            {"model_id": "m2", "settlement_probabilities":
                 {"full_win": .25, "half_win": .05, "push": 0, "half_loss": .1, "full_loss": .6}}])
        row = screen({"quotes": [q]}, NOW)["candidates"][0]
        self.assertEqual(row["ev_sensitivity_status"], "NO_POSITIVE_NUMERIC_EDGE_IN_SCENARIOS")
        self.assertLess(row["scenario_ev_max"], 0)
        self.assertFalse(row["positive_ev_verified"])


    def test_uncertified_positive_ev_does_not_determine_candidate_order(self):
        positive = {"full_win": .8, "half_win": 0, "push": 0,
                    "half_loss": 0, "full_loss": .2}
        negative = {"full_win": .2, "half_win": 0, "push": 0,
                    "half_loss": 0, "full_loss": .8}
        q_high = quote(fixture_id="fixture-z", settlement_probabilities=positive)
        q_low = quote(fixture_id="fixture-a", settlement_probabilities=negative)
        rows = screen({"quotes": [q_high, q_low]}, NOW)["candidates"]
        self.assertEqual([q["fixture_id"] for q in rows], ["fixture-a", "fixture-z"])
        self.assertFalse(any(q["positive_ev_verified"] for q in rows))
        self.assertTrue(all(q["status"] == "RESEARCH_ONLY" for q in rows))


if __name__ == "__main__":
    unittest.main()
