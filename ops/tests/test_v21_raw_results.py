import json
import unittest
from datetime import timedelta
from ops.v21_raw_results import compare,sha,crosswalk
from ops.tests.test_v6_forward_comparison import NOW,KO,result

def enc(d):return json.dumps(d).encode()
def inputs():
    mapping={"schema":"v21-bl1-crosswalk-v1","season":2026,"frozen_utc":NOW.isoformat(),
             "pairs":[{"openligadb_team_id":a,"football_data_team_id":b,"evidence_reference":"https://example.invalid/test"} for a,b in (("2","20"),("3","30"))]}
    fd={"competition":{"code":"BL1"},"matches":[{"id":111,"competition":{"code":"BL1"},
        "season":{"startDate":"2026-08-01"},"homeTeam":{"id":20},"awayTeam":{"id":30},"utcDate":KO.isoformat(),
        "status":"FINISHED","score":{"duration":"REGULAR","fullTime":{"home":2,"away":1}}}]}
    return result(),fd,mapping
def run_case(ol,fd,m):
    obs=(KO+timedelta(hours=3)).isoformat();raw=enc(m)
    return compare(enc(ol),enc(fd),fixture_id="1",home_id="2",away_id="3",kickoff_utc=KO.isoformat(),
        open_observed_utc=obs,fd_observed_utc=obs,mapping_raw=raw,mapping_sha256=sha(raw))
class RawResultTests(unittest.TestCase):
    def test_raw_semantics(self):
        r=run_case(*inputs())
        self.assertEqual(r["score"],[2,1]);self.assertTrue(r["raw_score_semantics_checked"])
        self.assertEqual(r["verified_forward_sample_credit"],0)
    def test_conflict(self):
        ol,fd,m=inputs();fd["matches"][0]["score"]["fullTime"]["home"]=3
        with self.assertRaisesRegex(ValueError,"DUAL_RESULT_CONFLICT"):run_case(ol,fd,m)
    def test_wrong_clock_and_scope(self):
        ol,fd,m=inputs();fd["matches"][0]["utcDate"]=(KO+timedelta(minutes=1)).isoformat()
        with self.assertRaisesRegex(ValueError,"MISSING_OR_AMBIGUOUS"):run_case(ol,fd,m)
        ol,fd,m=inputs();fd["matches"][0]["score"]["duration"]="EXTRA_TIME"
        with self.assertRaisesRegex(ValueError,"RESULT_FINAL"):run_case(ol,fd,m)
    def test_crosswalk_conflict_and_late(self):
        ol,fd,m=inputs();m["pairs"][1]["football_data_team_id"]="20"
        with self.assertRaisesRegex(ValueError,"CROSSWALK_CONFLICT"):run_case(ol,fd,m)
        ol,fd,m=inputs();m["frozen_utc"]=KO.isoformat()
        with self.assertRaisesRegex(ValueError,"CROSSWALK_CLOCK"):run_case(ol,fd,m)
        with self.assertRaisesRegex(ValueError,"CROSSWALK_DIGEST"):crosswalk(enc(m),"0"*64,KO)
