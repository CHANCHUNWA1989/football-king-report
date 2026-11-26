import unittest
import test_six_league_free_upgrade as existing
from live_core_credentialed_acceptance import accept,summarize
from live_core_same_batch_collection import run
class CredentialedAcceptanceTests(unittest.TestCase):
    def setup_case(self):
        f=existing.SixFreeUpgradeTests();f.setUp();return f
    def test_missing_keys_no_network(self):
        f=self.setup_case()
        def bomb(*a,**k):self.fail("network called")
        r=accept(now=lambda:f.now,fixed_now=f.now,market_fetcher=bomb,schedule_fetcher=bomb,fd_collector=bomb)
        self.assertEqual(r["market_state"],"NOT_CONFIGURED")
        self.assertEqual(r["market_requests"],0);self.assertEqual(r["football_data_requests"],0)
    def test_standalone_probe_when_no_market_token(self):
        f=self.setup_case();calls=[]
        def fd(leagues,**kwargs):
            calls.append(leagues)
            return [],{"requests_attempted":1,"attempts":{"epl":{"status":"KEY_REJECTED","rows":0}}}
        r=accept(fd_token="private-test-token",now=lambda:f.now,fixed_now=f.now,fd_collector=fd)
        self.assertEqual(calls,[["epl"]]);self.assertTrue(r["standalone_epl_probe"])
        self.assertEqual(r["football_data_state"],"NO_LOCAL_SCHEDULE")
        self.assertNotIn("private-test-token",str(r))
    def test_joint_injected_market_and_schedule(self):
        f=self.setup_case()
        def mf(path,key):return ([f.market] if "soccer_epl/odds" in path else [],990)
        def fd(*args):
            return {"matches":[{"id":1,"competition":{"code":"PL"},"status":"TIMED","utcDate":f.kickoff,"homeTeam":{"name":"Arsenal"},"awayTeam":{"name":"Chelsea"},"score":{"fullTime":{"home":None,"away":None}}}]},"OK"
        r=accept(market_token="market-test",fd_token="fd-test",now=lambda:f.now,fixed_now=f.now,market_fetcher=mf,schedule_fetcher=lambda *a:({"events":[]},"OK"),football_data_fetcher=fd,pause=lambda _:None)
        self.assertEqual(r["football_data_local_market_agreements"],1)
        self.assertEqual(r["market_state"],"FRESH_MARKET_OBSERVED")
        self.assertFalse(r["source_independence_authenticated"]);self.assertEqual(r["authenticated_forward_samples"],0)
        self.assertNotIn("Arsenal",str(r));self.assertNotIn("market-test",str(r))
    def test_unsafe_gate_rejected(self):
        f=self.setup_case();s,o,g=run(token="",now=lambda:f.now,fixed_now=f.now)
        g["can_promote_model"]=True
        with self.assertRaisesRegex(ValueError,"UNSAFE_GATE"):summarize(s,o,g,market_configured=False,fd_configured=False,now=f.now)

    def test_unrecorded_joint_observation_rejected(self):
        f=self.setup_case()
        def mf(path,key):return ([f.market] if "soccer_epl/odds" in path else [],990)
        s,o,g=run(token="test",now=lambda:f.now,fixed_now=f.now,market_fetcher=mf,
                    schedule_fetcher=lambda *a:({"events":[]},"OK"),pause=lambda _:None)
        o["football_data_schedule_research"]["local_agreements"]=1
        with self.assertRaisesRegex(ValueError,"UNRECORDED_FD_JOIN"):
            summarize(s,o,g,market_configured=True,fd_configured=False,now=f.now)
    def test_standalone_probe_scope_rejected(self):
        f=self.setup_case();s,o,g=run(token="",now=lambda:f.now,fixed_now=f.now)
        standalone={"requests_attempted":1,"attempts":{"laliga":{"status":"OK","rows":1}}}
        with self.assertRaisesRegex(ValueError,"STANDALONE_SCOPE"):
            summarize(s,o,g,market_configured=False,fd_configured=True,standalone=standalone,now=f.now)

    def test_consensus_summary_rejects_invalid_partition(self):
        f=self.setup_case();s,o,g=run(token="",now=lambda:f.now,fixed_now=f.now)
        r=summarize(s,o,g,market_configured=False,fd_configured=False,now=f.now)
        self.assertEqual(sum(r["unified_schedule_disposition"].values()),0)
        self.assertTrue(r["unified_schedule_counts_not_authenticated"])
        o["unified_schedule_consensus_research"]["disposition"]["ONE_SCHEDULE_LABEL_AGREES"]=1
        with self.assertRaisesRegex(ValueError,"COUNT_BOUND"):
            summarize(s,o,g,market_configured=False,fd_configured=False,now=f.now)
    def test_consensus_summary_rejects_authentication_claim(self):
        f=self.setup_case();s,o,g=run(token="",now=lambda:f.now,fixed_now=f.now)
        o["unified_schedule_consensus_research"]["canonical_identity_authenticated"]=True
        with self.assertRaisesRegex(ValueError,"UNSAFE_CONSENSUS"):
            summarize(s,o,g,market_configured=False,fd_configured=False,now=f.now)

    def test_joint_patterns_reconstruct_consensus_and_reject_forgery(self):
        f=self.setup_case()
        def mf(path,key):return ([f.market] if "soccer_epl/odds" in path else [],990)
        s,o,g=run(token="test",now=lambda:f.now,fixed_now=f.now,market_fetcher=mf,
                    schedule_fetcher=lambda *a:({"events":[]},"OK"),pause=lambda _:None)
        r=summarize(s,o,g,market_configured=True,fd_configured=False,now=f.now)
        self.assertEqual(r["unified_schedule_disposition"]["NO_SCHEDULE_AGREEMENT"],1)
        q=o["unified_schedule_consensus_research"]
        q["joint_source_patterns_by_league"]["epl"]={"AGREE|OUTSIDE_SCOPE|AGREE":1}
        with self.assertRaisesRegex(ValueError,"CONSENSUS_PATTERN_PARTITION"):
            summarize(s,o,g,market_configured=True,fd_configured=False,now=f.now)
    def test_source_marginal_mismatch_rejected(self):
        f=self.setup_case()
        def mf(path,key):return ([f.market] if "soccer_epl/odds" in path else [],990)
        s,o,g=run(token="test",now=lambda:f.now,fixed_now=f.now,market_fetcher=mf,
                    schedule_fetcher=lambda *a:({"events":[]},"OK"),pause=lambda _:None)
        o["unified_schedule_consensus_research"]["source_disposition_by_league"]["epl"]["thesportsdb"]={"AGREE":1}
        with self.assertRaisesRegex(ValueError,"CONSENSUS_SOURCE_PARTITION"):
            summarize(s,o,g,market_configured=True,fd_configured=False,now=f.now)
