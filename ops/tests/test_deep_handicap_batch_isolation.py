"""Synthetic batch collision, mutation and replay safety tests."""
import copy
import hashlib
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_private_capture import _digest
from deep_handicap_batch_isolation import isolate
from test_deep_handicap_replay_bridge import fixture,FINAL


def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()


def item(n=0):
    r,m,o=fixture()
    c=r["candidate"]
    # Distinct synthetic identities and digests. No authentication implied.
    for obj in (c,c["baseline"],c["challenger"]):
        obj.update(fixture_id=f"synthetic-{n}",home_id=f"home-{n}",away_id=f"away-{n}")
    c["evidence"].update(market_event_id=f"market-{n}",
        shadow_projection_sha256=digest(f"shadow-{n}"),private_quote_report_sha256=digest(f"quote-{n}"))
    r["candidate_sha256"]=_digest(c)
    m.update(candidate_sha256=r["candidate_sha256"],fixture_id=c["fixture_id"],
             home_id=c["home_id"],away_id=c["away_id"])
    for obs in o:
        p=obs["provider"]
        m["provider_event_ids"][p]=f"{p}-{n}"
        m["provider_event_urls"][p]=f"https://www.{p}.com/matches/{n}"
        obs.update(home_id=c["home_id"],away_id=c["away_id"],
                   source_event_id=m["provider_event_ids"][p],source_url=m["provider_event_urls"][p],
                   evidence_sha256=digest(f"{p}-result-{n}"))
    return dict(capture_report=r,mapping=m,observations=o,
                expected_candidate_sha256=r["candidate_sha256"],data_kind="SYNTHETIC")


class BatchIsolationTests(unittest.TestCase):
    def test_clean_and_duplicate_batches(self):
        a,b,c=item(1),item(2),item(3)
        original=copy.deepcopy([a,b,c])
        r=isolate([a,b,c],as_of_utc=FINAL)
        self.assertEqual(r["accepted_count"],3)
        self.assertEqual([a,b,c],original)
        self.assertEqual(r["true_forward_sample_count"],0)
        self.assertFalse(r["qualifies_for_betting"])
        r=isolate([a,a,b],as_of_utc=FINAL)
        self.assertEqual(r["accepted_count"],1)
        self.assertEqual(r["rejections"],{"BATCH_COLLISION":2})

    def test_reused_source_event_digest_and_invalid_collision(self):
        for kind in ("provider","result","market","projection"):
            a,b,c=item(1),item(2),item(3)
            if kind=="provider":
                b["mapping"]["provider_event_ids"]["fotmob"]=a["mapping"]["provider_event_ids"]["fotmob"]
            elif kind=="result":
                b["observations"][0]["evidence_sha256"]=a["observations"][0]["evidence_sha256"]
            elif kind=="market":
                b["capture_report"]["candidate"]["evidence"]["market_event_id"]=a["capture_report"]["candidate"]["evidence"]["market_event_id"]
            else:
                b["capture_report"]["candidate"]["evidence"]["shadow_projection_sha256"]=a["capture_report"]["candidate"]["evidence"]["shadow_projection_sha256"]
            # b is deliberately malformed too; its claims still isolate a.
            b["data_kind"]="VERIFIED"
            r=isolate([a,b,c],as_of_utc=FINAL)
            self.assertEqual(r["accepted_count"],1)
            self.assertEqual(r["rejections"],{"BATCH_COLLISION":2})
            self.assertEqual(r["evaluation_rows"][0]["fixture_id"],"synthetic-3")

    def test_mixed_labels_and_invalid_inputs_never_promote(self):
        a,b=item(1),item(2)
        b["data_kind"]="EXTERNAL_UNAUTHENTICATED"
        r=isolate([a,b,None,{}],as_of_utc=FINAL)
        self.assertEqual(r["cohort_counts"],{"SYNTHETIC":1,"EXTERNAL_UNAUTHENTICATED":1})
        self.assertEqual(r["rejections"],{"INVALID_BATCH_ITEM":2})
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(isolate([None]*1001,as_of_utc=FINAL)["reason"],"INVALID_BATCH")
        self.assertEqual(isolate([],as_of_utc="bad")["reason"],"INVALID_CLOCK")

    def test_256_adversarial_batches(self):
        # Each batch contains two colliding items; reverse order changes nothing.
        a,b=item(1),item(2)
        for mask in range(256):
            x=copy.deepcopy(a)
            y=copy.deepcopy(b)
            y["expected_candidate_sha256"]=x["expected_candidate_sha256"]
            if mask&1: y["data_kind"]="VERIFIED"
            if mask&2: y["observations"][0]["score_home"]=99
            if mask&4: y["mapping"]["league"]="wrong"
            if mask&8: y["mapping"]["expected_identity_sealed_utc"]="2026-11-27T11:00:00Z"
            if mask&16: y["capture_report"]["status"]="READY"
            if mask&32: y["observations"][0]["result_scope"]="AFTER_EXTRA_TIME"
            if mask&64: y["observations"][0]["source_updated_utc"]="bad"
            if mask&128: y["capture_report"]["candidate"]["baseline"]["probabilities"]["FULL_WIN"]=2
            batch=[y,x] if mask%2 else [x,y]
            r=isolate(batch,as_of_utc=FINAL)
            self.assertEqual(r["accepted_count"],0)
            self.assertEqual(r["rejections"],{"BATCH_COLLISION":2})
            self.assertEqual(r["true_forward_sample_count"],0)
