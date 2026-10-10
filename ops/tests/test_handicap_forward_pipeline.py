"""Test true pre-match snapshot ordering and exact 2-publisher FT settlement."""
import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from handicap_forward_pipeline import analyze, publish


class AsianForwardPaperTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,10,16,tzinfo=timezone.utc)
        self.kick=self.now-timedelta(hours=3)
        self.capture=self.kick-timedelta(hours=2)
        self.quote={
            "schema":"football-king-quote-freshness-v1",
            "production_recommendations":"DISABLED",
            "executable_bookmaker_price_verified":False,
            "market_snapshot_research_only":True,
            "captured_utc":self.capture.isoformat(),
            "league":"soccer_epl", "home":"Arsenal", "away":"Chelsea",
            "quotes":[{
                "event_id":"evt_9", "bookmaker":"book-a", "market":"spreads",
                "status":"FRESH_OBSERVATION_NOT_EXECUTABLE",
                "source":"the_odds_api_v4",
                "outcome":"Chelsea", "point":0.25, "decimal_odds":2.0,
                "market_last_update_utc":(self.capture-timedelta(seconds=30)).isoformat(),
                "kickoff_utc":self.kick.isoformat()
            }]
        }
        fixture={
            "provider":"thesportsdb","league":"epl","home":"Arsenal",
            "away":"Chelsea","kickoff_utc":self.kick.isoformat(),
            "status":"FINISHED","score_ft":[1,1]
        }
        self.sources={
            "production_recommendations":"DISABLED",
            "sampled_fixtures":[fixture, dict(fixture,provider="football_data_org")]
        }

    def audit(self, quote=None, sources=None):
        return analyze(quote if quote is not None else self.quote,
                       sources if sources is not None else self.sources,
                       now=self.now, verifier=lambda source: self.now)

    def test_two_exact_scores_pre_match_quote_produces_half_win_paper_only(self):
        d=self.audit()
        self.assertEqual(d["status"],"RESEARCH_ONLY")
        self.assertEqual(d["qualified_pre_match_quote_count"],1)
        self.assertEqual(d["two_publisher_exact_score_matches"],1)
        self.assertEqual(d["paper_five_grade_counts"]["HALF_WIN"],1)
        self.assertAlmostEqual(d["paper_net_units_per_one_unit_quote"],.5)
        self.assertFalse(d["licensed_executable_prices_confirmed"])
        self.assertFalse(d["genuine_forward_market_roi_verified"])
        self.assertFalse(d["independent_quote_provenance_authenticated"])
        self.assertEqual(d["bets_authorized"],0)
        self.assertEqual(d["production_recommendations"],"DISABLED")
        self.assertNotIn("book-a",json.dumps(d))
        self.assertNotIn('"decimal_odds"',json.dumps(d))

    def test_only_one_publisher_cannot_settle(self):
        self.sources["sampled_fixtures"].pop()
        d=self.audit()
        self.assertEqual(d["status"],"HOLD")
        self.assertEqual(d["qualified_pre_match_quote_count"],0)
        self.assertEqual(d["rejected"].get("LESS_THAN_TWO_INDEPENDENT_SCORE_PUBLISHERS"),1)

    def test_same_winner_different_score_is_quarantined(self):
        self.sources["sampled_fixtures"][0]["score_ft"]=[0,2]
        self.sources["sampled_fixtures"][1]["score_ft"]=[1,2]
        d=self.audit()
        self.assertEqual(d["status"],"HOLD")
        self.assertEqual(d["rejected"].get("DIFFERENT_FULL_TIME_SCORE_ACROSS_PUBLISHERS"),1)

    def test_quote_taken_after_kickoff_is_never_accepted_for_forward_backtest(self):
        self.quote["captured_utc"]=(self.kick+timedelta(seconds=3)).isoformat()
        self.quote["quotes"][0]["market_last_update_utc"]=(
            self.kick-timedelta(seconds=50)).isoformat()
        d=self.audit()
        self.assertEqual(d["status"],"HOLD")
        self.assertEqual(d["rejected"].get("NO_SEALED_PREMATCH_PRICE"),1)

    def test_stale_market_quote_not_accepted(self):
        self.quote["quotes"][0]["market_last_update_utc"]=(
            self.capture-timedelta(hours=2)).isoformat()
        d=self.audit()
        self.assertEqual(d["status"],"HOLD")
        self.assertEqual(d["rejected"].get("STALE_MARKET_PRICE"),1)

    def test_source_envelope_not_verified(self):
        d=analyze(self.quote,self.sources,now=self.now,
                  verifier=lambda source: (_ for _ in ()).throw(ValueError("BAD")))
        self.assertEqual(d["reason"],"UNVERIFIED_RESULT_SOURCE_ENVELOPE")
        self.assertFalse(d["genuine_forward_market_roi_verified"])

    def test_in_progress_game_cannot_be_settled(self):
        self.quote["quotes"][0]["kickoff_utc"]=(self.now+timedelta(hours=2)).isoformat()
        d=self.audit()
        self.assertEqual(d["status"],"HOLD")
        self.assertEqual(d["qualified_pre_match_quote_count"],0)

    def test_wrong_market_or_team_can_not_create_paper_return(self):
        self.quote["quotes"][0]["market"]="h2h"
        d=self.audit()
        self.assertEqual(d["rejected"].get("NOT_ELIGIBLE_SPREAD"),1)
        self.assertEqual(d["qualified_pre_match_quote_count"],0)

    def test_duplicate_bookmaker_quote_rejected(self):
        self.quote["quotes"].append(copy.deepcopy(self.quote["quotes"][0]))
        d=self.audit()
        self.assertEqual(d["qualified_pre_match_quote_count"],1)
        self.assertEqual(d["rejected"].get("DUPLICATE_PRICE"),1)

    def test_missing_optional_quote_input_produces_public_hold_only(self):
        with tempfile.TemporaryDirectory() as temp:
            d=publish(temp, quotes=Path(temp)/"no-private-quotes.json",
                      sources=Path(temp)/"no-sources.json", now=self.now)
            self.assertEqual(d["status"],"HOLD")
            out=json.loads((Path(temp)/"handicap_forward_audit.json").read_text())
            self.assertEqual(out["bets_authorized"],0)
            self.assertFalse(out["licensed_executable_prices_confirmed"])

    def test_malformed_forged_quote_source_never_authenticates(self):
        self.quote["executable_bookmaker_price_verified"]=True
        d=self.audit()
        self.assertEqual(d["reason"],"NO_VALID_PROSPECTIVE_ASIAN_QUOTE_SNAPSHOT")
        self.assertEqual(d["qualified_pre_match_quote_count"],0)


if __name__=="__main__":
    unittest.main()
