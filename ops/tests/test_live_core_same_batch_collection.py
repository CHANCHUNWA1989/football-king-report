import copy
import unittest
from datetime import timedelta
import test_six_league_free_upgrade as existing
from live_core_same_batch_collection import run,compare_batch,schedule_rows,collect_schedules,reconcile_projection
from six_league_free_upgrade import extract
from team_identity import team_id
class SameBatchTests(unittest.TestCase):
    def setup_case(self):
        f=existing.SixFreeUpgradeTests();f.setUp();return f
    def test_no_key_no_network(self):
        f=self.setup_case()
        def bomb(*a):self.fail("unexpected call")
        six,o,g=run(token="",market_fetcher=bomb,schedule_fetcher=bomb,now=lambda:f.now,fixed_now=f.now,pause=lambda _:None)
        self.assertEqual(o["schedule_requests_attempted"],0);self.assertFalse(g["can_promote_model"])
    def test_same_batch_end_to_end(self):
        f=self.setup_case()
        def market(path,key):
            return ([f.market] if "soccer_epl/odds" in path else [],990)
        def schedule(provider,url,headers):
            return ({"events":[{"idLeague":"4328","idEvent":"3","strHomeTeam":"Arsenal","strAwayTeam":"Chelsea","strTimestamp":f.kickoff,"strStatus":"Not Started"}]} if "id=4328" in url else {"events":[]}),"OK"
        six,o,g=run(token="synthetic",market_fetcher=market,schedule_fetcher=schedule,now=lambda:f.now,fixed_now=f.now,pause=lambda _:None)
        self.assertEqual(six["coverage"][0]["full_1x2_events"],1)
        self.assertEqual(o["market_sample_count"],1);self.assertEqual(o["at_least_one_other_publisher_agreement"],1)
        self.assertEqual(o["schedule_requests_attempted"],6)
        self.assertFalse(o["canonical_identity_authenticated"]);self.assertFalse(g["can_recommend_bets"])
        self.assertNotIn("Arsenal",str((six,o,g)));self.assertNotIn("book_alpha",str((six,o,g)))
    def test_duplicate_market_id_never_projected(self):
        f=self.setup_case();out=[]
        s=extract([f.market,copy.deepcopy(f.market)],f.league,f.sport,f.now,identity_sink=out)
        self.assertEqual(out,[]);self.assertEqual(s["full_1x2_events"],0)
    def test_stale_and_conflict(self):
        f=self.setup_case();markets=[]
        extract([f.market],f.league,f.sport,f.now,identity_sink=markets)
        c=dict(markets[0],native_id="other",kickoff_utc=(f.now+timedelta(days=2)).isoformat())
        c.pop("oldest_market_update_utc")
        o=compare_batch(markets,[c],finished=f.now,requests=1,failures={})
        self.assertEqual(o["source_schedule_conflict_observations"],1)
        o=compare_batch(markets,[c],finished=f.now+timedelta(minutes=21),requests=1,failures={})
        self.assertEqual(o["time_valid_market_count"],0)
    def test_unknown_status_and_quota_stop(self):
        f=self.setup_case()
        self.assertEqual(schedule_rows({"events":[{"idLeague":"4328","strStatus":"Unknown"}]},"epl",f.now),[])
        rows,n,errors=collect_schedules(fetcher=lambda *a:(None,"RATE_LIMITED"),now=lambda:f.now,pause=lambda _:None)
        self.assertEqual(n,1);self.assertEqual(errors,{"RATE_LIMITED":1})

    def test_projection_marginals_reconciled(self):
        f=self.setup_case();rows=[]
        counts=extract([f.market],f.league,f.sport,f.now,identity_sink=rows)
        six={"coverage":[dict(counts,league=f.league)]}
        d=reconcile_projection(six,rows)
        self.assertEqual(d[f.league]["marginal_intersection_bounds"],[1,1])
        with self.assertRaisesRegex(ValueError,"PROJECTION_ACCOUNTING"):
            reconcile_projection(six,[])
        with self.assertRaisesRegex(ValueError,"PROJECTION_ACCOUNTING"):
            reconcile_projection(six,rows+rows)
    def test_projection_extra_fields_and_request_accounting(self):
        f=self.setup_case();rows=[]
        extract([f.market],f.league,f.sport,f.now,identity_sink=rows)
        with self.assertRaisesRegex(ValueError,"PROJECTION_SCOPE"):
            compare_batch([dict(rows[0],price=2.0)],[],finished=f.now,requests=0,failures={})
        with self.assertRaisesRegex(ValueError,"SCHEDULE_REQUEST_ACCOUNTING"):
            compare_batch(rows,[{k:v for k,v in rows[0].items() if k!="oldest_market_update_utc"}],finished=f.now,requests=0,failures={})
        with self.assertRaisesRegex(ValueError,"SCHEDULE_BUDGET"):
            compare_batch(rows,[],finished=f.now,requests=True,failures={})

    def test_market_ages_out_before_batch_completion(self):
        f=self.setup_case();rows=[]
        extract([f.market],f.league,f.sport,f.now,identity_sink=rows)
        schedules=[{k:v for k,v in rows[0].items() if k!="oldest_market_update_utc"}]
        o=compare_batch(rows,schedules,finished=f.now+timedelta(minutes=19),requests=1,failures={})
        self.assertEqual(o["time_valid_market_count"],0)
        self.assertEqual(o["market_row_disposition"],{"MARKET_UPDATE_STALE_OR_FUTURE":1})
        self.assertEqual(o["status"],"HOLD")
    def test_each_market_disposition_reconciled(self):
        f=self.setup_case();rows=[]
        extract([f.market],f.league,f.sport,f.now,identity_sink=rows)
        schedule={k:v for k,v in rows[0].items() if k!="oldest_market_update_utc"}
        o=compare_batch(rows,[schedule],finished=f.now,requests=1,failures={})
        self.assertEqual(o["market_row_disposition"],{"SCHEDULE_AGREEMENT_UNAUTHENTICATED":1})
        o=compare_batch(rows,[],finished=f.now,requests=1,failures={})
        self.assertEqual(o["market_row_disposition"],{"SECONDARY_UNAVAILABLE_OR_STALE":1})
        self.assertEqual(sum(o["market_row_disposition"].values()),o["market_sample_count"])
