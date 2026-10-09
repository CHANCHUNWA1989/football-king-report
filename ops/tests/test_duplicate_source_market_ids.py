"""Adversarial regression tests for duplicate source and market evidence."""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_archive_guard import check
from source_publish_guard import verify
from secondary_sources import collect

NOW=datetime(2026,10,9,14,tzinfo=timezone.utc)

def market():
    return {"schema":"football-king-market-consensus-v1",
            "provider":"the-odds-api.com/v4","status":"RESEARCH_ONLY",
            "as_of_utc":NOW.isoformat(),"event_count":1,
            "raw_bookmaker_quotes_redistributed":False,
            "production_recommendations":"DISABLED",
            "events":[{"league":"epl","source_event_id":"event1",
                       "home":"Home FC","away":"Away FC",
                       "kickoff_utc":(NOW+timedelta(days=1)).isoformat(),
                       "market_last_update_utc":(NOW-timedelta(minutes=2)).isoformat(),
                       "contributing_bookmakers":3,
                       "p_home":0.4,"p_draw":0.3,"p_away":0.3,
                       "probabilities_are_no_vig_consensus":True,
                       "prediction_or_value_bet":False}]}

class DuplicateMarketTests(unittest.TestCase):
    def test_single_market_event_still_valid(self):
        self.assertEqual(check(market()),NOW)

    def test_duplicate_market_event_rejected(self):
        doc=market()
        doc["events"].append(copy.deepcopy(doc["events"][0]))
        doc["event_count"]=2
        with self.assertRaisesRegex(ValueError,"DUPLICATE_MARKET_EVENT"):
            check(doc)

    def test_same_id_in_different_leagues_has_separate_scope(self):
        doc=market()
        doc["events"].append(dict(doc["events"][0],league="bundesliga"))
        doc["event_count"]=2
        self.assertEqual(check(doc),NOW)

    def test_blank_market_identity_rejected(self):
        doc=market()
        doc["events"][0]["source_event_id"]=" "
        with self.assertRaisesRegex(ValueError,"INVALID_MARKET_EVENT_IDENTITY"):
            check(doc)

    def test_home_equal_away_rejected(self):
        doc=market()
        doc["events"][0]["away"]="Home FC"
        with self.assertRaisesRegex(ValueError,"INVALID_MARKET_EVENT_IDENTITY"):
            check(doc)

class DuplicateSourceTests(unittest.TestCase):
    def payload(self):
        import json
        class Response:
            def __init__(self,doc):
                self.body=json.dumps(doc).encode()
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self,size): return self.body[:size]
        def fake(req,timeout):
            ident=int(req.full_url.rsplit("=",1)[-1])
            return Response({"events":[{
                "idEvent":str(ident),"idLeague":str(ident),
                "strHomeTeam":"Home","strAwayTeam":"Away",
                "strTimestamp":(datetime.now(timezone.utc)+timedelta(days=2)).isoformat(),
                "strStatus":"NS"}]})
        return collect(now=datetime.now(timezone.utc),keys={},requester=fake)

    def test_unmodified_source_passes(self):
        self.assertIsNotNone(verify(self.payload()))

    def test_duplicate_source_cannot_inflate_coverage(self):
        doc=self.payload()
        row=copy.deepcopy(doc["sampled_fixtures"][0])
        doc["sampled_fixtures"].append(row)
        provider=next(p for p in doc["providers"] if p["provider"]==row["provider"])
        provider["counts_by_league"][row["league"]]+=1
        provider["sampled_fixture_count"]+=1
        with self.assertRaisesRegex(ValueError,"DUPLICATE_SOURCE_FIXTURE"):
            verify(doc)

    def test_same_provider_event_id_different_league_is_not_duplicate(self):
        doc=self.payload()
        ids=[(r["provider"],r["league"],r["provider_event_id"]) for r in doc["sampled_fixtures"]]
        self.assertEqual(len(ids),len(set(ids)))

if __name__=="__main__":
    unittest.main()
