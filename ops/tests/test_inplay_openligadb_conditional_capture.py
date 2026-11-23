"""Synthetic conditional single-match GET tests; never contact live OpenLigaDB."""
import json
import os
import stat
import tempfile
import threading
import time
import unittest
from datetime import timedelta
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inplay_openligadb_conditional_capture import (
    conditional_capture_once, _reservation_name,
)
from inplay_openligadb_lastchange_probe import (
    probe_once, PROBE_FILE, _read_checkpoint,
)
from inplay_openligadb_league_pacing import RATE_FILE
from test_inplay_openligadb_lastchange_probe import (
    NOW,TOKEN1,TOKEN2,source as probe_source,
)
from test_inplay_openligadb_one_shot import EVENT_ID,URL,raw,response


SEASON=2026
GROUP=8

def valid_match():
    case=response()
    case["group"]={"groupOrderID":GROUP,"groupName":"Synthetic Round"}
    return case


def match_getter(calls,body=None,status=200,media="application/json",final=URL):
    def get(url):
        calls.append(url)
        return (raw(valid_match()) if body is None else body,status,media,final)
    return get


class ConditionalMatchCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"private"
        self.root.mkdir(mode=0o700)

    def probe(self,dt,token):
        return probe_once(SEASON,GROUP,self.root,now=lambda:dt,getter=probe_source([],token))

    def capture(self,dt,mid=EVENT_ID,getter=None,season=SEASON,group=GROUP):
        return conditional_capture_once(mid,season,group,self.root,
                                        getter=getter,now=lambda:dt)

    def changed(self):
        first=self.probe(NOW,TOKEN1)
        second=self.probe(NOW+timedelta(seconds=90),TOKEN2)
        self.assertEqual(first["change_status"],"BASELINE_ONLY")
        self.assertEqual(second["change_status"],"CHANGED_UNATTESTED")
        return NOW+timedelta(seconds=180)

    def test_baseline_does_not_allow_full_get(self):
        self.probe(NOW,TOKEN1)
        calls=[]
        result=self.capture(NOW+timedelta(seconds=90),getter=match_getter(calls))
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(result["reason"],"CHANGE_NOT_DEMONSTRATED")
        self.assertEqual(result["requests_attempted"],0)
        self.assertEqual(calls,[])

    def test_changed_probe_allows_exactly_one_full_get_with_private_readback(self):
        at=self.changed()
        calls=[]
        out=self.capture(at,getter=match_getter(calls))
        self.assertEqual(calls,[URL])
        self.assertEqual(out["status"],"RESEARCH_ONLY")
        self.assertEqual(out["requests_attempted"],1)
        self.assertTrue(out["local_original_response_bytes_readback_verified"])
        self.assertTrue(out["same_host_change_probe_required"])
        self.assertTrue(out["token_consumption_reservation_persisted"])
        self.assertFalse(out["source_authenticated"])
        self.assertFalse(out["token_to_match_body_causality_proven"])
        self.assertFalse(out["provider_issued_time_authenticated"])
        self.assertFalse(out["eligible_for_model_input"])
        self.assertFalse(out["externally_witnessed"])
        self.assertFalse(out["positive_ev_verified"])
        self.assertEqual(out["certified_forward_samples"],0)
        self.assertEqual(out["production_recommendations"],"DISABLED")
        self.assertIsNone(out["recommendation"])
        self.assertEqual(len(out["archive_sha256_unattested"]),64)
        self.assertIn(RATE_FILE,{p.name for p in self.root.iterdir()})
        self.assertEqual(len([x for x in self.root.iterdir() if "reserve" in x.name]),1)

    def test_repeated_same_token_same_match_blocked_even_after_cooldown(self):
        at=self.changed()
        self.capture(at,getter=match_getter([]))
        calls=[]
        out=self.capture(at+timedelta(seconds=90),getter=match_getter(calls))
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["reason"],"TOKEN_ALREADY_RESERVED_OR_CAPTURED")
        self.assertEqual(calls,[])

    def test_changed_token_later_returns_to_unchanged_never_fetch(self):
        at=self.changed()
        self.probe(at,TOKEN2)
        calls=[]
        out=self.capture(at+timedelta(seconds=90),getter=match_getter(calls))
        self.assertEqual(out["reason"],"CHANGE_NOT_DEMONSTRATED")
        self.assertEqual(calls,[])

    def test_expired_change_checkpoint_does_not_fetch(self):
        at=self.changed()
        calls=[]
        out=self.capture(at+timedelta(minutes=10),getter=match_getter(calls))
        self.assertEqual(out["reason"],"CHANGE_CHECKPOINT_TOO_OLD")
        self.assertEqual(calls,[])

    def test_early_read_after_probe_within_90_seconds_no_get(self):
        self.changed()
        calls=[]
        at=NOW+timedelta(seconds=90, milliseconds=500)
        out=self.capture(at,getter=match_getter(calls))
        self.assertEqual(out["reason"],"SHARED_LEAGUE_RATE_WINDOW")
        self.assertEqual(calls,[])

    def test_invalid_native_group_even_with_correct_match_id_no_private_archive(self):
        at=self.changed()
        bad=valid_match()
        bad["group"]["groupOrderID"]=9
        calls=[]
        out=self.capture(at,getter=match_getter(calls,body=raw(bad)))
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(calls,[URL])
        self.assertFalse(any(p.name.startswith("openligadb-bl1-") and p.name.endswith(".tar")
                             for p in self.root.iterdir()))

    def test_mismatched_season_group_missing_group_rejected(self):
        for field,value in (("leagueSeason",2025),("group",None),("group",{"groupOrderID":True})):
            with self.subTest(field=field,value=value):
                self.setUp()
                at=self.changed()
                bad=valid_match()
                bad[field]=value
                out=self.capture(at,getter=match_getter([],body=raw(bad)))
                self.assertEqual(out["status"],"HOLD")

    def test_wrong_native_match_id_does_not_archive(self):
        at=self.changed()
        bad=valid_match()
        bad["matchID"]=EVENT_ID+1
        out=self.capture(at,getter=match_getter([],body=raw(bad)))
        self.assertEqual(out["status"],"HOLD")
        self.assertFalse(any(p.name.endswith(".tar") for p in self.root.iterdir()))

    def test_first_request_failure_consumes_token_no_retry(self):
        at=self.changed()
        calls=[]
        def bad(url):
            calls.append(url)
            raise OSError("SECRET_NEVER_ECHO")
        out=self.capture(at,getter=bad)
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["requests_attempted"],1)
        self.assertNotIn("SECRET_NEVER_ECHO",str(out))
        later=self.capture(at+timedelta(seconds=600),getter=match_getter(calls))
        self.assertEqual(later["reason"],"TOKEN_ALREADY_RESERVED_OR_CAPTURED")
        self.assertEqual(calls,[URL])

    def test_wrong_group_argument_or_invalid_id_before_http(self):
        at=self.changed()
        calls=[]
        for kwargs in ({"group":GROUP+1},{"season":2025},{"mid":0},{"mid":"12345"}):
            out=self.capture(at,getter=match_getter(calls),**kwargs)
            self.assertEqual(out["status"],"HOLD")
        self.assertEqual(calls,[])

    def test_altered_change_checkpoint_does_not_fetch(self):
        at=self.changed()
        target=self.root/PROBE_FILE
        value=json.loads(target.read_text())
        value["transition"]="CHANGED_UNATTESTED"
        value["previous_token_sha256"]=value["token_sha256"]
        target.write_text(json.dumps(value,sort_keys=True,separators=(",",":")))
        calls=[]
        out=self.capture(at,getter=match_getter(calls))
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(calls,[])

    def test_symlink_reservation_fails_before_http_and_does_not_modify_target(self):
        at=self.changed()
        checkpoint=json.loads((self.root/PROBE_FILE).read_text())
        name=_reservation_name(SEASON,GROUP,EVENT_ID,checkpoint["token_sha256"])
        target=Path(self.root.parent)/"outside"
        target.write_bytes(b"IMPORTANT_DO_NOT_MODIFY")
        (self.root/name).symlink_to(target)
        calls=[]
        out=self.capture(at,getter=match_getter(calls))
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(calls,[])
        self.assertEqual(target.read_bytes(),b"IMPORTANT_DO_NOT_MODIFY")

    def test_unsafe_directory_disables_attempt(self):
        at=self.changed()
        self.root.chmod(0o755)
        calls=[]
        out=self.capture(at,getter=match_getter(calls))
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(calls,[])

    def test_single_shared_host_two_threads_never_double_get(self):
        at=self.changed()
        calls=[]
        entered=threading.Event()
        release=threading.Event()
        outs=[]
        def slow(url):
            calls.append(url)
            entered.set()
            if not release.wait(4):
                raise TimeoutError("NO_COMPLETION")
            return (raw(valid_match()),200,"application/json",URL)
        a=threading.Thread(target=lambda:outs.append(self.capture(at,getter=slow)),daemon=True)
        b=threading.Thread(target=lambda:outs.append(self.capture(at,getter=match_getter(calls))),daemon=True)
        a.start()
        self.assertTrue(entered.wait(3))
        b.start()
        time.sleep(.04)
        release.set()
        a.join(5);b.join(5)
        self.assertEqual(calls,[URL])
        self.assertEqual(sorted(x["status"] for x in outs),["HOLD","RESEARCH_ONLY"])

    def test_first_change_checkpoint_carries_previous_digest_and_transition(self):
        self.changed()
        state=json.loads((self.root/PROBE_FILE).read_text())
        self.assertEqual(state["transition"],"CHANGED_UNATTESTED")
        self.assertEqual(len(state["previous_token_sha256"]),64)
        self.assertNotEqual(state["previous_token_sha256"],state["token_sha256"])

    def test_no_automatic_request_even_on_change_without_explicit_capture(self):
        self.changed()
        self.assertFalse(any(p.name.endswith(".tar") for p in self.root.iterdir()))


if __name__=="__main__":
    unittest.main()
