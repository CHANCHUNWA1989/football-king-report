import copy
import unittest
from datetime import timedelta
import test_live_core_blend50_forward_settlement as fixture
from live_core_blend50_attempt_ledger import empty,append,audit,key_for,GENESIS
from live_core_blend50_forward_seal import instant,digest

class AttemptLedgerTests(unittest.TestCase):
    def context(self):
        now,c=fixture.Blend50SettlementTests().case()
        t=instant(c["forecast"]["record"]["captured_utc"])
        f=c["original"]["fixture"]
        reg={"league":c["original"]["league"],"home":f["home"],"away":f["away"],"kickoff_utc":f["kickoff_utc"]}
        return now,t,c,reg
    def add(self,d,kind,reg,payload,at,now):
        head=d["events"][-1]["sha256"] if d["events"] else GENESIS
        return append(d,{"kind":kind,"fixture_key":key_for(reg),"observed_utc":at.isoformat(),"payload":payload},now=now,expected_head=head)
    def test_denominator_and_failures(self):
        now,t,c,reg=self.context()
        missing=dict(reg,home="C")
        d=self.add(empty(),"REGISTER",reg,reg,t,now)
        d=self.add(d,"REGISTER",missing,missing,t,now)
        d=self.add(d,"CAPTURE_FAILED",missing,{"reason":"SOURCE_UNAVAILABLE"},t,now)
        d=self.add(d,"CAPTURE",reg,{"original":c["original"],"forecast":c["forecast"]},t,now)
        d=self.add(d,"SETTLE_FAILED",reg,{"reason":"RESULT_CONFLICT"},now,now)
        d=self.add(d,"SETTLE",reg,{"results":c["results"]},now,now)
        r=audit(d,now=now)
        self.assertEqual(r["registered_fixture_count"],2)
        self.assertEqual(r["states"]["SETTLED_LOCAL"],1)
        self.assertEqual(r["states"]["CAPTURE_MISSED"],1)
        self.assertEqual(r["capture_failure_events"],1)
        self.assertEqual(r["settlement_failure_events"],1)
        self.assertEqual(r["authenticated_forward_samples"],0)
        self.assertFalse(r["complete_attempt_denominator_verified"])
    def test_chain_tampering_and_truncation(self):
        now,t,c,reg=self.context()
        d=self.add(empty(),"REGISTER",reg,reg,t,now)
        head=d["events"][-1]["sha256"]
        with self.assertRaisesRegex(ValueError,"EXPECTED_HEAD_MISMATCH"):audit(empty(),now=now,expected_head=head)
        x=copy.deepcopy(d);x["events"][0]["payload"]["home"]="Z"
        with self.assertRaisesRegex(ValueError,"CHAIN_DIGEST"):audit(x,now=now)
        self.assertTrue(audit(d,now=now,expected_head=head)["expected_head_checked"])
    def test_unregistered_and_late_events(self):
        now,t,c,reg=self.context()
        with self.assertRaises(ValueError):self.add(empty(),"CAPTURE_FAILED",reg,{"reason":"SOURCE_UNAVAILABLE"},t,now)
        with self.assertRaises(ValueError):self.add(empty(),"REGISTER",reg,reg,now,now)
        d=self.add(empty(),"REGISTER",reg,reg,t,now)
        with self.assertRaises(ValueError):self.add(d,"CAPTURE_FAILED",reg,{"reason":"SOURCE_UNAVAILABLE"},now,now)
    def test_pending_and_due_partition(self):
        now,t,c,reg=self.context()
        d=self.add(empty(),"REGISTER",reg,reg,t,now)
        self.assertEqual(audit(d,now=t)["states"]["REGISTERED_PENDING_CAPTURE"],1)
        d=self.add(d,"CAPTURE",reg,{"original":c["original"],"forecast":c["forecast"]},t,now)
        self.assertEqual(audit(d,now=t)["states"]["SEALED_PENDING_RESULT"],1)
        self.assertEqual(audit(d,now=now)["states"]["RESULT_DUE_UNSETTLED"],1)
    def test_stale_checkpoint_and_duplicate(self):
        now,t,c,reg=self.context()
        d=self.add(empty(),"REGISTER",reg,reg,t,now)
        with self.assertRaises(ValueError):self.add(d,"REGISTER",reg,reg,t,now)
        with self.assertRaisesRegex(ValueError,"EXPECTED_HEAD_MISMATCH"):
            append(d,{"kind":"REGISTER","fixture_key":key_for(reg),"observed_utc":t.isoformat(),"payload":reg},now=now,expected_head=GENESIS)
    def test_false_settlement_rejected(self):
        now,t,c,reg=self.context()
        d=self.add(empty(),"REGISTER",reg,reg,t,now)
        d=self.add(d,"CAPTURE",reg,{"original":c["original"],"forecast":c["forecast"]},t,now)
        bad=copy.deepcopy(c["results"]);bad[1]["score"]=[2,0]
        with self.assertRaises(ValueError):self.add(d,"SETTLE",reg,{"results":bad},now,now)

    def test_prefix_checkpoint_accepts_extension_not_exact_head(self):
        now,t,c,reg=self.context()
        old=self.add(empty(),"REGISTER",reg,reg,t,now)
        checkpoint={"event_count":1,"head_sha256":old["events"][0]["sha256"]}
        new=self.add(old,"CAPTURE",reg,{"original":c["original"],"forecast":c["forecast"]},t,now)
        r=audit(new,now=now,prefix_checkpoint=checkpoint)
        self.assertTrue(r["caller_prefix_checkpoint_checked"])
        self.assertEqual(r["events_after_caller_prefix"],1)
        self.assertFalse(r["checkpoint_externally_authenticated"])
        self.assertFalse(r["external_timestamp_attested"])
        self.assertEqual(r["authenticated_forward_samples"],0)
    def test_prefix_checkpoint_rejects_rebuilt_fork_and_truncation(self):
        now,t,c,reg=self.context()
        old=self.add(empty(),"REGISTER",reg,reg,t,now)
        checkpoint={"event_count":1,"head_sha256":old["events"][0]["sha256"]}
        other=dict(reg,home="C")
        fork=self.add(empty(),"REGISTER",other,other,t,now)
        with self.assertRaisesRegex(ValueError,"PREFIX_FORK_OR_REWRITE"):
            audit(fork,now=now,prefix_checkpoint=checkpoint)
        with self.assertRaisesRegex(ValueError,"PREFIX_TRUNCATED"):
            audit(empty(),now=now,prefix_checkpoint=checkpoint)
    def test_prefix_checkpoint_genesis_and_invalid_scope(self):
        now,t,c,reg=self.context()
        r=audit(empty(),now=now,prefix_checkpoint={"event_count":0,"head_sha256":GENESIS})
        self.assertEqual(r["events_after_caller_prefix"],0)
        self.assertTrue(r["caller_prefix_checkpoint_checked"])
        for bad in ({"event_count":True,"head_sha256":GENESIS},
                    {"event_count":0,"head_sha256":"z"*64},
                    {"event_count":-1,"head_sha256":GENESIS}):
            with self.assertRaisesRegex(ValueError,"INVALID_PREFIX_CHECKPOINT"):
                audit(empty(),now=now,prefix_checkpoint=bad)
        r=audit(empty(),now=now)
        self.assertIsNone(r["events_after_caller_prefix"])
        self.assertFalse(r["caller_prefix_checkpoint_checked"])
