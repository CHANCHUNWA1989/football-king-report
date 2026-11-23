"""OpenLigaDB lastchangedate shared-league research probe (fake HTTP only)."""
import base64
import json
import os
import stat
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from inplay_openligadb_lastchange_probe import (
    probe_once, PROBE_FILE, _probe_url, _parse_response,
    PROBE_SCHEMA, _parse_token,
)
from inplay_openligadb_league_pacing import (
    RATE_FILE, COOLDOWN_FAILURE, COOLDOWN_SUCCESS, paced_capture_once,
)
from test_inplay_openligadb_one_shot import NOW, EVENT_ID, fake_getter


TOKEN1='"2026-11-23T00:49:20"'
TOKEN2='"2026-11-23T00:51:00"'
ENDPOINT="https://api.openligadb.de/getlastchangedate/bl1/2026/8"


def source(requests, token=TOKEN1, status=200, media="application/json", final=ENDPOINT):
    def getter(url):
        requests.append(url)
        return (token.encode("utf-8") if type(token) is str else token,
                status,media,final)
    return getter


class OpenLigaLastChangeTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)/"private"
        self.root.mkdir(mode=0o700)
    def probe(self,at=NOW,season=2026,group=8,getter=None):
        return probe_once(season,group,self.root,now=lambda:at,getter=getter)

    def test_first_probe_saves_exact_marker_but_is_not_a_change(self):
        requests=[]
        out=self.probe(getter=source(requests))
        self.assertEqual(requests,[ENDPOINT])
        self.assertEqual(out["status"],"RESEARCH_ONLY")
        self.assertEqual(out["change_status"],"BASELINE_ONLY")
        self.assertIsNone(out["change_detected"])
        self.assertEqual(out["requests_attempted"],1)
        self.assertTrue(out["shared_host_league_pacing_applied"])
        self.assertFalse(out["eligible_for_full_match_auto_fetch"])
        self.assertFalse(out["eligible_for_model_input"])
        self.assertFalse(out["source_authenticated"])
        self.assertFalse(out["externally_witnessed"])
        self.assertFalse(out["positive_ev_verified"])
        self.assertEqual(out["certified_forward_samples"],0)
        self.assertEqual(out["production_recommendations"],"DISABLED")
        self.assertIsNone(out["recommendation"])
        self.assertEqual(out["raw_response_sha256_unattested"].__len__(),64)
        checkpoint=json.loads((self.root/PROBE_FILE).read_text())
        self.assertEqual(checkpoint["schema"],PROBE_SCHEMA)
        self.assertEqual(base64.b64decode(checkpoint["raw_response_base64"],validate=True),
                         TOKEN1.encode())
        self.assertEqual(stat.S_IMODE((self.root/PROBE_FILE).stat().st_mode),0o600)
        self.assertEqual(set(p.name for p in self.root.iterdir()),{PROBE_FILE,RATE_FILE})
        self.assertNotIn("2026-11-23T00:49:20",str(out))

    def test_second_probe_unchanged_and_third_changed_without_full_fetch(self):
        requests=[]
        first=self.probe(getter=source(requests))
        same=self.probe(NOW+timedelta(seconds=90),getter=source(requests))
        changed=self.probe(NOW+timedelta(seconds=180),getter=source(requests,TOKEN2))
        self.assertEqual(len(requests),3)
        self.assertEqual([first["change_status"],same["change_status"],changed["change_status"]],
                         ["BASELINE_ONLY","UNCHANGED","CHANGED_UNATTESTED"])
        self.assertIs(same["change_detected"],False)
        self.assertIs(changed["change_detected"],True)
        self.assertFalse(changed["eligible_for_full_match_auto_fetch"])
        self.assertFalse(changed["full_match_get_performed"])
        self.assertFalse(changed["eligible_for_model_scoring"])

    def test_probe_and_existing_full_match_get_share_one_rate_file(self):
        requests=[]
        self.probe(getter=source(requests))
        full=[]
        result=paced_capture_once(EVENT_ID,self.root,
                                  getter=fake_getter(full),
                                  now=lambda:NOW+timedelta(seconds=30))
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(result["reason"],"SHARED_LEAGUE_RATE_WINDOW")
        self.assertEqual(full,[])
        self.assertEqual(requests,[ENDPOINT])

    def test_failed_probe_reserves_600_seconds(self):
        requests=[]
        bad=self.probe(getter=source(requests,status=429))
        self.assertEqual(bad["status"],"HOLD")
        self.assertEqual(bad["requests_attempted"],1)
        early=self.probe(NOW+timedelta(seconds=90),getter=source(requests))
        self.assertEqual(early["reason"],"SHARED_LEAGUE_RATE_WINDOW")
        self.assertEqual(requests,[ENDPOINT])
        later=self.probe(NOW+timedelta(seconds=COOLDOWN_FAILURE),getter=source(requests))
        self.assertEqual(later["status"],"RESEARCH_ONLY")
        self.assertEqual(requests,[ENDPOINT,ENDPOINT])

    def test_invalid_season_group_before_any_request_or_rate_marker(self):
        for season,group in ((True,8),(2026,True),("2026",8),(2026,0),(2026,35),
                             (1999,8),(2026,-1),(2026,"8")):
            requests=[]
            result=self.probe(season=season,group=group,getter=source(requests))
            self.assertEqual(result["status"],"HOLD")
            self.assertEqual(requests,[])
        self.assertEqual(list(self.root.iterdir()),[])

    def test_diff_group_checkpoint_rejected_without_http(self):
        requests=[]
        self.probe(getter=source(requests))
        again=self.probe(NOW+timedelta(seconds=90),group=9,getter=source(requests))
        self.assertEqual(again["status"],"HOLD")
        self.assertEqual(again["requests_attempted"],0)
        self.assertEqual(requests,[ENDPOINT])

    def test_time_without_zone_is_only_opaque_untrusted_token(self):
        assert _parse_token(TOKEN1.encode()) == "2026-11-23T00:49:20"
        requests=[]
        r=self.probe(getter=source(requests))
        self.assertFalse(r["provider_token_timezone_authenticated"])
        self.assertFalse(r["provider_last_update_time_authenticated"])
        self.assertFalse(r["actual_match_updated_verified"])

    def test_malformed_json_and_not_string_and_non_datetime_rejected(self):
        for raw in (b"null",b"{}",b"[1]",b"123",b'"garbage"',
                    b'"2026-99-77T00:00:00"',b"NaN",
                    b'"2026-11-23"',b'""',b'0'*400):
            with self.subTest(raw=raw[:20]):
                self.assertEqual(self.probe(getter=source([],raw))["status"],"HOLD")
                # Each attempt consumes a cooldown; use isolated new directory.
                for item in self.root.iterdir():
                    item.unlink()

    def test_http_redirect_wrong_final_url_or_media_refused(self):
        cases=[{"status":302},{"status":500},
               {"final":"https://evil.test/p"},
               {"media":"text/html"},
               {"token":b"x"*400}]
        for kw in cases:
            calls=[]
            self.assertEqual(self.probe(getter=source(calls,**kw))["status"],"HOLD")
            self.assertEqual(calls,[ENDPOINT])
            for item in self.root.iterdir():
                item.unlink()

    def test_checkpoint_corruption_and_symlink_refuse_before_request(self):
        calls=[]
        self.probe(getter=source(calls))
        (self.root/PROBE_FILE).write_bytes(b'{"token":"wrong"}')
        r=self.probe(NOW+timedelta(seconds=90),getter=source(calls))
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(calls,[ENDPOINT])
        (self.root/PROBE_FILE).unlink()
        outside=Path(self.root.parent)/"outside"
        outside.write_bytes(b"private!")
        (self.root/PROBE_FILE).symlink_to(outside)
        r=self.probe(NOW+timedelta(seconds=90),getter=source(calls))
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(outside.read_bytes(),b"private!")
        self.assertEqual(calls,[ENDPOINT])

    def test_hardlink_and_weak_checkpoint_perms_refused(self):
        self.probe(getter=source([]))
        (self.root/PROBE_FILE).chmod(0o644)
        calls=[]
        self.assertEqual(self.probe(NOW+timedelta(seconds=90),getter=source(calls))["status"],"HOLD")
        (self.root/PROBE_FILE).chmod(0o600)
        os.link(self.root/PROBE_FILE,self.root/"duplicate")
        self.assertEqual(self.probe(NOW+timedelta(seconds=90),getter=source(calls))["status"],"HOLD")
        self.assertEqual(calls,[])

    def test_backwards_clock_and_unsafe_directory_refused(self):
        self.probe(getter=source([]))
        calls=[]
        backwards=self.probe(NOW-timedelta(seconds=1),getter=source(calls))
        self.assertEqual(backwards["reason"],"LOCAL_RATE_CLOCK_MOVED_BACKWARDS")
        self.root.chmod(0o755)
        self.assertEqual(self.probe(NOW+timedelta(seconds=90),getter=source(calls))["status"],"HOLD")
        self.assertEqual(calls,[])

    def test_fetch_exception_safe_hold_and_no_retry(self):
        calls=[]
        def fail(url):
            calls.append(url)
            raise OSError("SENSITIVE_PROVIDER_HEADER")
        r=self.probe(getter=fail)
        self.assertEqual(r["status"],"HOLD")
        self.assertNotIn("SENSITIVE",str(r))
        self.assertEqual(calls,[ENDPOINT])
        self.assertEqual(self.probe(NOW+timedelta(seconds=100),getter=source(calls))["status"],"HOLD")
        self.assertEqual(calls,[ENDPOINT])

    def test_two_threads_same_league_only_one_probe(self):
        started=threading.Event()
        release=threading.Event()
        seen=[]
        answers=[]
        def slow(url):
            seen.append(url)
            started.set()
            release.wait(timeout=5)
            return (TOKEN1.encode(),200,"application/json",ENDPOINT)
        a=threading.Thread(target=lambda:answers.append(self.probe(getter=slow)),daemon=True)
        b=threading.Thread(target=lambda:answers.append(self.probe(getter=source(seen))),daemon=True)
        a.start()
        self.assertTrue(started.wait(timeout=4))
        b.start()
        time.sleep(.03)
        release.set()
        a.join(timeout=5);b.join(timeout=5)
        self.assertFalse(a.is_alive());self.assertFalse(b.is_alive())
        self.assertEqual(seen,[ENDPOINT])
        self.assertEqual(sorted(x["status"] for x in answers),["HOLD","RESEARCH_ONLY"])


if __name__=="__main__":
    unittest.main()
