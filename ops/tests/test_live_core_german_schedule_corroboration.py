import unittest
from datetime import timedelta
import test_six_league_free_upgrade as existing
from live_core_same_batch_collection import run
from live_core_german_schedule_corroboration import review,schedule_only
from team_identity import team_id
class GermanCorroborationTests(unittest.TestCase):
    def data(self):
        f=existing.SixFreeUpgradeTests();f.setUp()
        m={"league":"bundesliga","home_id":team_id("bundesliga","Werder Bremen"),"away_id":team_id("bundesliga","Mainz"),"native_id":"1","kickoff_utc":f.kickoff,"received_utc":f.now.isoformat(),"oldest_market_update_utc":f.updated}
        s={k:v for k,v in m.items() if k!="oldest_market_update_utc"}
        return f,m,s
    def test_separate_source_namespace_and_conflict(self):
        f,m,s=self.data()
        r=review([m],[s],[s],finished=f.now)
        self.assertEqual(r["market_disposition"],{"BOTH_AGREE_UNAUTHENTICATED":1})
        self.assertEqual(r["authenticated_forward_samples"],0)
        c=dict(s,kickoff_utc=(f.now+timedelta(days=2)).isoformat())
        self.assertEqual(review([m],[s],[c],finished=f.now)["market_disposition"],{"SOURCE_CONFLICT_OR_AMBIGUITY":1})
    def test_fallback_only_and_stale(self):
        f,m,s=self.data()
        self.assertEqual(review([m],[],[s],finished=f.now)["market_disposition"],{"OPENLIGA_ONLY_AGREES":1})
        s["received_utc"]=(f.now-timedelta(minutes=21)).isoformat()
        self.assertEqual(review([m],[],[s],finished=f.now)["market_disposition"],{"NO_FRESH_AGREEMENT":1})
    def test_duplicate_conflict_and_expired_quote(self):
        f,m,s=self.data()
        self.assertEqual(review([m],[s],[s,s],finished=f.now)["market_disposition"],{"SOURCE_CONFLICT_OR_AMBIGUITY":1})
        self.assertEqual(review([m],[s],[s],finished=f.now+timedelta(minutes=19))["market_disposition"],{"MARKET_TIME_REJECTED":1})
    def test_public_pair_no_market_or_raw_names(self):
        f,m,s=self.data();calls=[]
        def get(url):
            calls.append(url)
            return [{"leagueShortcut":"bl1","matchID":1,"matchIsFinished":False,"matchResults":[],"matchDateTimeUTC":f.kickoff,"team1":{"teamName":"Werder Bremen"},"team2":{"teamName":"Mainz"}}]
        def fetch(*args):
            calls.append(args[1]);return {"events":[{"idLeague":"4331","idEvent":"2","strHomeTeam":"Werder Bremen","strAwayTeam":"Mainz","strTimestamp":f.kickoff,"strStatus":"Not Started"}]},"OK"
        r=schedule_only(fetcher=fetch,getter=get,now=lambda:f.now)
        self.assertEqual(len(calls),2);self.assertEqual(r["local_exact_schedule_agreements"],1)
        self.assertNotIn("Werder",str(r));self.assertFalse(r["market_collection_attempted"])
    def test_cli_integration_injected_one_openliga_call(self):
        f,m,s=self.data();event=f.market
        event["sport_key"]="soccer_germany_bundesliga"
        event["home_team"]="Werder Bremen";event["away_team"]="Mainz"
        for book in event["bookmakers"]:
            for market in book["markets"]:
                for out in market["outcomes"]:
                    if out["name"]=="Arsenal":out["name"]="Werder Bremen"
                    if out["name"]=="Chelsea":out["name"]="Mainz"
        def mf(path,key):return ([event] if "soccer_germany_bundesliga/odds" in path else [],990)
        calls=[]
        def get(url):
            calls.append(url);return [{"leagueShortcut":"bl1","matchID":1,"matchIsFinished":False,"matchResults":[],"matchDateTimeUTC":f.kickoff,"team1":{"teamName":"Werder Bremen"},"team2":{"teamName":"Mainz"}}]
        _,o,g=run(token="synthetic",market_fetcher=mf,schedule_fetcher=lambda *a:({"events":[]},"OK"),now=lambda:f.now,fixed_now=f.now,pause=lambda _:None,openliga_getter=get)
        self.assertEqual(len(calls),1)
        self.assertEqual(o["german_schedule_research"]["market_disposition"],{"OPENLIGA_ONLY_AGREES":1})
        self.assertEqual(o["at_least_one_other_publisher_agreement"],0)
        self.assertFalse(g["can_promote_model"])

    def test_conflicting_market_pair_never_earns_fallback_agreement(self):
        f,m,s=self.data()
        other=dict(m,native_id="2",kickoff_utc=(f.now+timedelta(days=3)).isoformat())
        r=review([m,other],[],[s],finished=f.now)
        self.assertEqual(r["market_disposition"],{"MARKET_ID_AMBIGUOUS":2})
        self.assertEqual(r["source_disposition"],{"thesportsdb":{},"openligadb":{}})
        self.assertEqual(r["authenticated_forward_samples"],0)
