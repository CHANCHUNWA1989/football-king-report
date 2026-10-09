"""No-network tests for Asian quarter-goal payouts and in-play timing gates."""
import copy
import json
import math
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from live_market_research import (
    analyze, example, payout, quarter_legs, totals_ev, poisson_weights,
)

ASOF=datetime(2026,10,9,13,30,10,tzinfo=timezone.utc)


class InPlayAsianResearchTests(unittest.TestCase):
    def test_screenshot_has_all_twelve_manual_markets_and_hold(self):
        result=analyze(example(),now=ASOF)
        self.assertEqual(result["market_count"],12)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(result["reason"],
                         "SCREENSHOT_HAS_NO_VERIFIABLE_BOOKMAKER_QUOTE_TIMESTAMP")
        self.assertIsNone(result["recommended_market"])
        self.assertFalse(result["execution_permission"])
        self.assertFalse(result["live_odds_verified"])
        self.assertFalse(result["league_covered_by_main_calibrated_model"])
        self.assertEqual(result["production_recommendations"],"DISABLED")
        self.assertTrue(result["no_bookmaker_or_api_contact"])

    def test_under_one_three_quarters_is_half_loss_on_exactly_two(self):
        m={"kind":"totals","side":"under","line":1.75,"odds":1.74}
        self.assertEqual(quarter_legs(1.75),(1.5,2.0))
        self.assertAlmostEqual(payout(m,0,0),.74)
        self.assertAlmostEqual(payout(m,1,0),.74)
        self.assertAlmostEqual(payout(m,1,1),-.5)
        self.assertAlmostEqual(payout(m,2,1),-1.)

    def test_over_one_three_quarters_is_half_win_on_exact_two(self):
        m={"kind":"totals","side":"over","line":1.75,"odds":2.06}
        self.assertAlmostEqual(payout(m,1,1),.53)
        self.assertAlmostEqual(payout(m,0,0),-1)
        self.assertAlmostEqual(payout(m,2,1),1.06)

    def test_under_one_and_quarter_half_win_exactly_one(self):
        m={"kind":"totals","side":"under","line":1.25,"odds":2.38}
        self.assertAlmostEqual(payout(m,0,0),1.38)
        self.assertAlmostEqual(payout(m,1,0),.69)
        self.assertAlmostEqual(payout(m,1,1),-1.)

    def test_over_one_quarter_half_loss_exactly_one(self):
        m={"kind":"totals","side":"over","line":1.25,"odds":1.52}
        self.assertAlmostEqual(payout(m,1,0),-.5)
        self.assertAlmostEqual(payout(m,1,1),.52)

    def test_home_plus_quarter_and_away_minus_quarter_at_draw(self):
        home={"kind":"handicap","side":"home","line":.25,"odds":1.76}
        away={"kind":"handicap","side":"away","line":-.25,"odds":2.06}
        self.assertAlmostEqual(payout(home,0,0),.38)
        self.assertAlmostEqual(payout(away,0,0),-.5)
        self.assertAlmostEqual(payout(home,0,1),-1)
        self.assertAlmostEqual(payout(away,0,1),1.06)

    def test_away_draw_no_bet_is_push_at_draw(self):
        away={"kind":"handicap","side":"away","line":0.,"odds":1.66}
        self.assertEqual(payout(away,0,0),0)
        self.assertAlmostEqual(payout(away,0,1),.66)
        self.assertEqual(payout(away,1,0),-1)

    def test_stale_user_screenshot_never_becomes_live_quote(self):
        case=example()
        case["bookmaker_quote_updated_utc"]="2026-10-09T13:30:00+00:00"
        case["source_time_attested"]=True
        r=analyze(case,now=ASOF+timedelta(minutes=15))
        self.assertEqual(r["reason"],"STALE_LIVE_MARKET_OR_SCREENSHOT")
        self.assertFalse(r["live_odds_verified"])
        self.assertIsNone(r["recommended_market"])

    def test_attested_time_is_still_only_research_not_model(self):
        case=example()
        case["bookmaker_quote_updated_utc"]="2026-10-09T13:30:00+00:00"
        case["source_time_attested"]=True
        r=analyze(case,now=ASOF)
        self.assertTrue(r["live_odds_verified"])
        self.assertEqual(r["reason"],"LIVE_MARKET_RESEARCH_ONLY_NO_CALIBRATED_LEAGUE_MODEL")
        self.assertEqual(r["status"],"HOLD")
        self.assertIsNone(r["recommended_market"])
        self.assertFalse(r["execution_permission"])

    def test_no_attestation_does_not_claim_live_odds_even_if_time_present(self):
        case=example()
        case["bookmaker_quote_updated_utc"]="2026-10-09T13:30:00+00:00"
        case["source_time_attested"]=False
        r=analyze(case,now=ASOF)
        self.assertFalse(r["live_odds_verified"])
        self.assertIsNone(r["recommended_market"])

    def test_forecast_intensity_sensitivity_is_not_confident_prediction(self):
        case=example()
        r=analyze(case,now=ASOF)
        small=next(x for x in r["hypothetical_scenarios"]
                   if x["market_id"]=="under_1_75"
                   and x["remaining_goals_assumption"]==1.7)
        self.assertAlmostEqual(small["hypothetical_ev"],-.01,delta=.012)
        self.assertTrue(r["hypothetical_sensitivity_not_calibrated_probability"])
        self.assertAlmostEqual(sum(poisson_weights(1.7)),1.,delta=1e-9)

    def test_missing_inplay_stats_is_not_faked(self):
        c=example()
        c.pop("home_corners")
        r=analyze(c,now=ASOF)
        self.assertFalse(r["live_shots_xg_verified"])
        self.assertFalse(r["source_independently_verified"])
        self.assertFalse(r["point_in_time_snapshot_attested"])

    def test_invalid_clock_team_and_duplicate_market_ids_fail_closed(self):
        for field,val in (("minute",59),("away","NK Sesvete"),
                          ("home_goals",True)):
            c=example()
            c[field]=val
            self.assertEqual(analyze(c,now=ASOF)["status"],"HOLD")
            self.assertEqual(analyze(c,now=ASOF)["market_count"],0)
        d=example()
        d["markets"].append(dict(d["markets"][0]))
        self.assertEqual(analyze(d,now=ASOF)["reason"],"DUPLICATE_MARKET_IDENTIFIERS")

    def test_bad_asian_line_and_bookmaker_price_rejected(self):
        with self.assertRaises(ValueError):
            quarter_legs(.333)
        with self.assertRaises(ValueError):
            payout({"kind":"totals","side":"under","line":1.75,"odds":1},0,0)
        with self.assertRaises(ValueError):
            payout({"kind":"handicap","side":"under","line":.5,"odds":2},0,0)

    def test_other_league_stays_unsupported_in_live_research(self):
        d=example()
        d["league"]="epl"
        r=analyze(d,now=ASOF)
        self.assertEqual(r["reason"],"LEAGUE_NOT_SUPPORTED_FOR_MANUAL_RESEARCH")
        self.assertIsNone(r["recommended_market"])


if __name__=="__main__":
    unittest.main()
