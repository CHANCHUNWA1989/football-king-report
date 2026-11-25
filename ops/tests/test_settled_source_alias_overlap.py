import copy
import json
import unittest
from pathlib import Path
from hashlib import sha1
from ops.settled_source_alias_overlap import compare
from ops.source_publish_guard import LEAGUES, PROVIDERS

def example():
    k="2026-11-22T16:30:00+00:00"
    f={"provider":"thesportsdb","league":"bundesliga","home":"Werder Bremen","away":"Hamburg","kickoff_utc":k,"provider_event_id":"1","status":"FINISHED","score_ft":[4,0]}
    providers=[]
    for p in PROVIDERS:
        n=int(p=="thesportsdb")
        providers.append({"provider":p,"status":"PARTIAL" if n else "NOT_CONFIGURED","configured":bool(n),"production_recommendations":"DISABLED","can_replace_1x2_market":False,"original_bookmaker_odds_redistributed":False,"league_result_verification_complete":False,"calls_attempted":n,"counts_by_league":{l:n if l=="bundesliga" else 0 for l in LEAGUES},"sampled_fixture_count":n})
    source={"schema":"football-king-extra-source-audit-v1","production_recommendations":"DISABLED","six_league_independent_results_verified":False,"odds_fallback_confirmed":False,"coverage_is_complete":False,"original_api_payload_redistributed":False,"started_utc":"2026-11-25T04:34:45+00:00","collected_utc":"2026-11-25T04:39:51+00:00","providers":providers,"sampled_fixtures":[f]}
    row={"key":json.dumps(["bundesliga","svwerderbremen","hamburgersv",k]),"league":"bundesliga","kickoff_utc":k,"forecast_utc":"2026-11-21T15:00:00+00:00","market_utc":"2026-11-21T14:00:00+00:00","y":0,"production_recommendations":"DISABLED","fixture_result_source_independently_verified":False}
    settled={"n":1,"samples":[row],"production_recommendations":"DISABLED","results_independently_verified":False,"profitability_verified":False}
    return source,settled

class OverlapTests(unittest.TestCase):
    def test_alias_only_and_no_promotion(self):
        s,d=example()
        r=compare(s,d)
        self.assertEqual(r["candidate_records"][0]["status"],"OUTCOME_AGREEMENT_UNVERIFIED")
        self.assertEqual(r["certified_samples"],0)
        self.assertIs(r["independently_verified"],False)
    def test_conflict(self):
        s,d=example()
        d["samples"][0]["y"]=2
        self.assertEqual(compare(s,d)["candidate_records"][0]["status"],"OUTCOME_CONFLICT")
    def test_reversed_teams(self):
        s,d=example()
        f=s["sampled_fixtures"][0]
        f["home"],f["away"]=f["away"],f["home"]
        self.assertEqual(compare(s,d)["unmatched"],1)
    def test_duplicate_alias(self):
        s,d=example()
        row=copy.deepcopy(d["samples"][0])
        row["key"]=json.dumps(["bundesliga","Werder Bremen","Hamburg",row["kickoff_utc"]])
        d["samples"].append(row);d["n"]=2
        self.assertEqual(compare(s,d)["candidate_records"][0]["status"],"AMBIGUOUS")
    def test_forecast_at_kickoff(self):
        s,d=example()
        d["samples"][0]["forecast_utc"]=d["samples"][0]["kickoff_utc"]
        with self.assertRaises(ValueError):
            compare(s,d)
    def test_promoted_row(self):
        s,d=example()
        d["samples"][0]["fixture_result_source_independently_verified"]=True
        with self.assertRaises(ValueError):
            compare(s,d)
    def test_pinned_archives_if_present(self):
        def blob(path):
            raw=Path(path).read_bytes()
            return sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest(),json.loads(raw)
        a,s=blob("sources/latest.json")
        b,d=blob("evidence/settled.json")
        if (a,b)!=("842b0302bf143ce0f0537244ff476e4d58c8ac46","8f926d2c1aa9739f89975bd561c18239cb0cf28c"):
            self.skipTest("Historical pinned archive has changed")
        r=compare(s,d)
        self.assertEqual((r["archive_rows"],r["finished_observations"],r["unmatched"],r["certified_samples"]),(128,8,7,0))
        self.assertEqual(r["candidate_records"],[{"provider":"thesportsdb","provider_event_id":"2508415","league":"bundesliga","status":"OUTCOME_AGREEMENT_UNVERIFIED","observation_count":1}])
        print(json.dumps(r,sort_keys=True))

if __name__=="__main__":
    unittest.main()
