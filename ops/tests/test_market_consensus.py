import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_consensus import analyze

def quote(book,odds,point=1.75,market="totals",outcome="Under",event="game"):
    return {"event_id":event,"bookmaker":book,"decimal_odds":odds,
            "point":point,"market":market,"outcome":outcome,
            "market_last_update_utc":"2026-10-09T14:00:00Z",
            "status":"FRESH_OBSERVATION_NOT_EXECUTABLE"}
def audit(*quotes):
    return {"quotes":list(quotes)}

class ConsensusTests(unittest.TestCase):
    def test_two_bookmakers_same_line_consensus(self):
        r=analyze(audit(quote("a",1.80),quote("b",1.84)))
        self.assertEqual(r["groups_with_research_consensus"],1)
        self.assertEqual(r["groups"][0]["median_decimal_odds"],1.82)
        self.assertFalse(r["groups"][0]["positive_ev_proven"])
        self.assertEqual(r["production_recommendations"],"DISABLED")

    def test_one_bookmaker_cannot_claim_consensus(self):
        r=analyze(audit(quote("a",1.8)))
        self.assertEqual(r["groups"][0]["consensus_status"],"INSUFFICIENT_BOOKMAKERS")

    def test_different_asian_lines_do_not_mix(self):
        r=analyze(audit(quote("a",1.8,1.75),quote("b",1.84,1.5)))
        self.assertEqual(len(r["groups"]),2)
        self.assertEqual(r["groups_with_research_consensus"],0)

    def test_different_fixture_cannot_mix(self):
        r=analyze(audit(quote("a",1.8,event="one"),quote("b",1.84,event="two")))
        self.assertEqual(len(r["groups"]),2)

    def test_large_dispersion_is_hold(self):
        r=analyze(audit(quote("a",1.2),quote("b",2.4)))
        self.assertEqual(r["groups"][0]["consensus_status"],"DISAGREEMENT_HOLD")

    def test_duplicate_bookmaker_cannot_inflate(self):
        r=analyze(audit(quote("a",1.8),quote("a",1.9),quote("b",1.85)))
        self.assertEqual(r["invalid_or_duplicate_quotes"],1)
        self.assertEqual(r["groups"][0]["bookmakers"],2)

    def test_invalid_price_is_ignored(self):
        r=analyze(audit(quote("a",float("nan")),quote("b",1.9)))
        self.assertEqual(r["invalid_or_duplicate_quotes"],1)
        self.assertEqual(r["groups"][0]["bookmakers"],1)

    def test_unvalidated_quote_is_ignored(self):
        q=quote("a",1.8)
        q["status"]="UNVERIFIED"
        r=analyze(audit(q))
        self.assertEqual(r["status"],"HOLD")

    def test_different_markets_or_outcomes_do_not_mix(self):
        r=analyze(audit(quote("a",1.8),quote("b",1.9,market="spreads"),
                        quote("c",1.85,outcome="Over")))
        self.assertEqual(len(r["groups"]),3)

    def test_prematch_and_live_quotes_are_never_combined(self):
        first=quote("a", 1.80)
        first["quote_pre_match_at_capture"]=True
        first["market_phase_at_capture"]="PREMATCH"
        second=quote("b", 1.82)
        second["quote_pre_match_at_capture"]=False
        second["market_phase_at_capture"]="IN_PLAY_OR_TOO_LATE"
        result=analyze(audit(first, second))
        self.assertEqual(len(result["groups"]), 2)
        self.assertEqual(result["groups_with_research_consensus"], 0)
        self.assertEqual(
            {x["market_phase_at_capture"] for x in result["groups"]},
            {"PREMATCH", "IN_PLAY_OR_TOO_LATE"})

    def test_unsafe_and_inconsistent_phase_claims_rejected(self):
        first=quote("a", 1.80)
        first["quote_pre_match_at_capture"]=False
        first["market_phase_at_capture"]="PREMATCH"
        result=analyze(audit(first))
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["invalid_or_duplicate_quotes"], 1)

    def test_explicitly_unsafe_quote_audit_rejected(self):
        body=audit(quote("a", 1.8))
        body["production_recommendations"]="ENABLED"
        with self.assertRaisesRegex(ValueError, "INVALID_QUOTE_AUDIT"):
            analyze(body)

    def test_empty_audit_is_hold(self):
        self.assertEqual(analyze(audit())["status"],"HOLD")

    def test_invalid_config_rejected(self):
        with self.assertRaises(ValueError):
            analyze(audit(),min_bookmakers=1)
        with self.assertRaises(ValueError):
            analyze(audit(),max_spread_ratio=True)

if __name__=="__main__":
    unittest.main()
