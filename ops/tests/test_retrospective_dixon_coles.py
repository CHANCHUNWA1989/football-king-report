"""An isolated fixed-rate correction must not reuse inspected labels for fitting."""
import copy
import json
import math
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retrospective_dixon_coles import (
    MODEL_ID, RHO_GRID, probabilities, fit_development, build_report,
)
from shadow_forecast import poisson_1x2


def independent_grid(home, away, rho):
    values = [0.0, 0.0, 0.0]
    for h in range(12):
        for a in range(12):
            mass = math.exp(-home-away)*home**h*away**a/math.factorial(h)/math.factorial(a)
            tau = {(0, 0): 1-home*away*rho, (0, 1): 1+home*rho,
                   (1, 0): 1+away*rho, (1, 1): 1-rho}.get((h, a), 1)
            values[0 if h > a else 1 if h == a else 2] += mass*tau
    return [v/sum(values) for v in values]


def row(n=0, season="2024-25", *, y=1, league="epl", home=1.2, away=.9):
    start = date(2024 if season == "2024-25" else 2025, 8, 1)
    return {"league": league, "season": season,
            "date": (start+timedelta(days=n*7)).isoformat(),
            "replay_case_id": f"{season}|{league}|{n}", "y": y,
            "original": poisson_1x2(home, away), "league_frequency": [.45,.27,.28],
            "expected_home_goals": home, "expected_away_goals": away}


class DixonColesProbabilityTests(unittest.TestCase):
    def test_zero_rho_exactly_reproduces_same_input_poisson(self):
        for home in (.1, .33333, 1., 1.23456, 3.6, 5.5):
            for away in (.1, .45678, 1., 2.45678, 5.5):
                with self.subTest(home=home, away=away):
                    self.assertEqual(probabilities(home, away, 0), poisson_1x2(home, away))

    def test_low_score_adjustment_matches_independent_grid_and_preserves_mass(self):
        self.assertEqual(RHO_GRID, (-.15, -.1, -.05, 0., .025))
        for home, away in ((.1,.1),(1.2,.9),(5.5,5.5),(5.5,.1)):
            for rho in RHO_GRID:
                p = probabilities(home, away, rho)
                expected = independent_grid(home, away, rho)
                self.assertEqual(p, [round(v,7) for v in expected])
                self.assertLess(abs(sum(p)-1), 2e-7)
                self.assertTrue(all(0 < v < 1 for v in p))
        old = probabilities(1.2,.9,0)
        corrected = probabilities(1.2,.9,-.1)
        self.assertGreater(corrected[1], old[1])
        self.assertLess(corrected[0], old[0])
        self.assertLess(corrected[2], old[2])

    def test_bad_rates_rho_and_nonpositive_tau_are_rejected(self):
        for bad in (True, False, None, "1.2", .099999, 5.50001,
                    float("nan"), float("inf"), 10**1000):
            for rates in ((bad,1.2),(1.2,bad)):
                with self.subTest(rates=repr(rates)[:80]):
                    with self.assertRaises(ValueError): probabilities(*rates,0)
        for bad in (True, None, "-.1", float("nan"), float("inf"), 10**1000):
            with self.assertRaises(ValueError): probabilities(1.2,.9,bad)
        for home, away, rho in ((1,1,1),(5.5,5.5,.1),(5.5,1,-1),(1,5.5,-1)):
            with self.assertRaises(ValueError): probabilities(home,away,rho)


class DixonColesFitTests(unittest.TestCase):
    def test_development_log_loss_uses_unrounded_distributions(self):
        rows=[row(i,y=i%3,home=.81234+i*.071,away=1.82345-i*.031) for i in range(18)]
        result=fit_development(rows)
        expected=[]
        for rho in RHO_GRID:
            loss=math.fsum(-math.log(independent_grid(
                r["expected_home_goals"],r["expected_away_goals"],rho)[r["y"]])
                for r in rows)/len(rows)
            expected.append((loss,abs(rho),rho))
            actual=next(s for s in result["scores"] if s["rho"]==rho)
            self.assertAlmostEqual(actual["development_mean_log_loss"],loss,14)
        self.assertEqual(result["rho"], min(expected)[2])
        self.assertEqual(result["basis"], "2024_25_DEVELOPMENT_UNROUNDED_LOG_LOSS_ONLY")
        self.assertEqual(result["n"],len(rows))

    def test_fit_direction_and_empty_input(self):
        self.assertEqual(fit_development([row(i,y=1) for i in range(9)])["rho"],-.15)
        self.assertEqual(fit_development([row(i,y=0) for i in range(9)])["rho"],.025)
        empty=fit_development([])
        self.assertIsNone(empty["rho"])
        self.assertEqual(empty["scores"],[])
        self.assertEqual(empty["status"],"HOLD")

    def test_wrong_season_invalid_rows_and_duplicate_cases_fail(self):
        bad_rows=[row(season="2025-26")]
        for key,value in (("y",True),("y",3),("season",None),
                          ("expected_home_goals",True),("expected_away_goals",float("nan")),
                          ("original",[.4,.3,.9]),("original",[True,.2,.8]),
                          ("league_frequency",[.4,float("nan"),.6]),
                          ("league_frequency",[10**1000,.3,.2]),
                          ("date","bad"),("league","unknown")):
            case=row();case[key]=value;bad_rows.append(case)
        for bad in bad_rows+[None,{},[]]:
            with self.subTest(bad=repr(bad)[:100]):
                with self.assertRaises(ValueError):fit_development([bad])
        with self.assertRaises(ValueError):fit_development([row(),row()])


class DixonColesReportTests(unittest.TestCase):
    def setUp(self):
        self.development=[row(i,y=i%3) for i in range(24)]
        self.assessment=[row(i,"2025-26",y=i%3,league="epl" if i%2 else "laliga")
                         for i in range(24)]

    def test_report_keeps_rho_fit_separate_from_inspected_assessment(self):
        result=build_report(self.development,self.assessment)
        changed=copy.deepcopy(self.assessment)
        for case in changed:
            case["y"]=(case["y"]+1)%3
            case["expected_home_goals"]=4.8
            case["expected_away_goals"]=.3
        other=build_report(self.development,changed)
        self.assertEqual(result["development_fit"],other["development_fit"])
        self.assertEqual(result["selected_rho"],other["selected_rho"])
        self.assertEqual(result["model_id"],MODEL_ID)
        self.assertFalse(result["assessment_is_unseen_holdout"])
        self.assertTrue(result["development_rho_score_is_in_sample"])
        self.assertFalse(result["uses_assessment_labels_for_rho_selection"])
        self.assertFalse(result["automatic_model_promotion"])
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_existing_scorers_calibration_rps_and_fixed_rho_per_league(self):
        from retrospective_backtest import summary,block_ci
        from research_center import calibration,score_rps
        result=build_report(self.development,self.assessment)
        rho=result["selected_rho"]
        rows=copy.deepcopy(self.assessment)
        for case in rows:
            case["candidate"]=probabilities(case["expected_home_goals"],case["expected_away_goals"],rho)
            case["derived_rho0"]=probabilities(case["expected_home_goals"],case["expected_away_goals"],0)
        scope=result["cohorts"]["2025-26"]
        expected=summary(rows,"candidate")
        for key,value in expected.items(): self.assertEqual(scope["models"]["candidate"][key],value)
        self.assertEqual(scope["models"]["candidate"]["probability_calibration"],
                         calibration([{"p":r["candidate"],"y":r["y"]} for r in rows]))
        self.assertEqual(scope["models"]["candidate"]["mean_normalized_rps"],
                         round(sum(score_rps(r["candidate"],r["y"]) for r in rows)/len(rows),6))
        self.assertEqual(scope["paired_week_bootstrap_candidate_vs_original"],block_ci(rows,"candidate"))
        aliases=[{**r,"original":r["derived_rho0"]} for r in rows]
        self.assertEqual(scope["paired_week_bootstrap_candidate_vs_derived_rho0"],block_ci(aliases,"candidate"))
        for league in ("epl","laliga"):
            sub=[r for r in rows if r["league"]==league]
            self.assertEqual(result["by_league"][league]["2025-26"]["models"]["candidate"]["n"],len(sub))
            self.assertEqual(result["by_league"][league]["selected_rho"],rho)

    def test_rounded_rate_baseline_difference_is_reported_separately(self):
        changed=copy.deepcopy(self.assessment)
        changed[0]["original"]=[.1,.8,.1]
        scope=build_report(self.development,changed)["cohorts"]["2025-26"]
        approximation=scope["rho0_original_approximation"]
        self.assertEqual(approximation["argmax_disagreements"],1)
        self.assertAlmostEqual(approximation["maximum_absolute_probability_difference"],
                               max(abs(a-b) for a,b in zip([.1,.8,.1],poisson_1x2(1.2,.9))),7)
        self.assertNotEqual(scope["models"]["original"],scope["models"]["derived_rho0"])

    def test_partial_or_empty_archive_has_no_fitted_candidate(self):
        for dev,assessment,complete in (([],[],True),(self.development,[],True),
                                       ([],self.assessment,True),
                                       (self.development,self.assessment,False)):
            result=build_report(dev,assessment,archive_complete=complete)
            self.assertEqual(result["status"],"HOLD")
            self.assertIsNone(result["selected_rho"])
            self.assertIsNone(result["development_fit"]["rho"])
            for scope in result["cohorts"].values():
                self.assertIsNone(scope["models"]["candidate"])
                self.assertIsNone(scope["paired_week_bootstrap_candidate_vs_original"])
            json.dumps(result,allow_nan=False)

    def test_report_does_not_mutate_or_return_aliases_to_input_rows(self):
        before=copy.deepcopy((self.development,self.assessment))
        result=build_report(self.development,self.assessment)
        self.assertEqual((self.development,self.assessment),before)
        result["cohorts"]["2024-25"]["models"]["original"]["probability_calibration"][0]["bins"][0]["n"]=999
        self.assertEqual((self.development,self.assessment),before)
        with self.assertRaises(ValueError):build_report(self.assessment,self.development)


if __name__ == "__main__":
    unittest.main()
