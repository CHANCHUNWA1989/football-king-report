import json
import unittest
from datetime import timedelta
from ops.research_private_settlement_v49 import settle
from ops.research_private_run_store_v48 import encode_run
from ops.research_integrated_fusion_v45 import prepare
from ops.tests.test_research_archive_score_recovery_v14 import fixture,encode
from ops.tests.test_research_two_publisher_recovery_v15 import secondary
from ops.tests.test_research_private_propline_v43 import fixture as market_fixture,NOW

def inputs():
    raw,p=fixture()
    market=market_fixture()
    market.update(sport_key="soccer_germany_bundesliga",home_team="a",away_team="b")
    for book in market["bookmakers"]:
        for o in book["markets"][0]["outcomes"]:
            if o["name"]=="Arsenal":o["name"]="a"
            elif o["name"]=="Chelsea":o["name"]="b"
    batch={"raw":encode({"events":[market]}),"league":"bundesliga","captured_utc":NOW.isoformat()}
    packets,_=prepare(raw,[("prior",encode(p))],[],None,[batch],as_of=NOW.isoformat())
    ko=market["commence_time"];end=NOW+timedelta(hours=5)
    p["collected_utc"]=end.isoformat()
    p["matches"][0].update(kickoff_utc=ko,provider_match_id=999)
    s=secondary();s["sampled_fixtures"][0].update(kickoff_utc=ko,provider_event_id="new-secondary")
    s["started_utc"]=(end-timedelta(minutes=1)).isoformat()
    s["collected_utc"]=end.isoformat()
    return encode_run(batch,packets),p,s,end.isoformat()

class PrivateSettlementTests(unittest.TestCase):
    def test_dual_exact_candidate(self):
        raw,p,s,now=inputs()
        c,r=settle(raw,[("p",encode(p))],[("s",encode(s))],as_of=now)
        self.assertEqual(r["two_publisher_candidates"],1)
        self.assertEqual(c[0]["score_candidate"],[2,1])
        self.assertEqual(c[0]["outcome_candidate"],0)
        self.assertEqual(len(c[0]["references"]),2)
        self.assertEqual(r["authenticated_samples"],0)
        self.assertFalse(r["publication_allowed"])
    def test_single_not_settled(self):
        raw,p,s,now=inputs()
        c,r=settle(raw,[("p",encode(p))],[],as_of=now)
        self.assertEqual(r["states"],{"SINGLE_PUBLISHER_REVIEW":1})
        self.assertIsNone(c[0]["outcome_candidate"])
    def test_exact_score_conflict(self):
        raw,p,s,now=inputs()
        s["sampled_fixtures"][0]["score_ft"]=[3,1]
        c,r=settle(raw,[("p",encode(p))],[("s",encode(s))],as_of=now)
        self.assertEqual(r["states"],{"RESULT_CONFLICT_REVIEW":1})
        self.assertIsNone(c[0]["score_candidate"])
    def test_schedule_conflict(self):
        raw,p,s,now=inputs()
        s["sampled_fixtures"][0]["kickoff_utc"]=(NOW+timedelta(hours=2,minutes=1)).isoformat()
        c,r=settle(raw,[("p",encode(p))],[("s",encode(s))],as_of=now)
        self.assertEqual(r["states"],{"RESULT_CONFLICT_REVIEW":1})
    def test_future_result_snapshot_rejected(self):
        raw,p,s,now=inputs()
        with self.assertRaises(ValueError):settle(raw,[("p",encode(p))],[],as_of=NOW.isoformat())
    def test_waiting_for_final(self):
        raw,p,s,now=inputs()
        c,r=settle(raw,[],[],as_of=NOW.isoformat())
        self.assertEqual(r["states"],{"AWAITING_FINAL_WINDOW":1})
    def test_early_final_conflict(self):
        raw,p,s,now=inputs()
        p["collected_utc"]=(NOW+timedelta(hours=3)).isoformat()
        c,r=settle(raw,[("p",encode(p))],[("s",encode(s))],as_of=now)
        self.assertEqual(r["states"],{"RESULT_CONFLICT_REVIEW":1})
    def test_duplicate_snapshot_not_second_publisher(self):
        raw,p,s,now=inputs()
        c,r=settle(raw,[("p",encode(p)),("copy",encode(p))],[],as_of=now)
        self.assertEqual(r["states"],{"SINGLE_PUBLISHER_REVIEW":1})
