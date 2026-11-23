"""One-league shared-host OpenLigaDB rate gate: synthetic only, no HTTP calls."""
import json
import os
import stat
import tempfile
import threading
import time
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from inplay_openligadb_league_pacing import (
    paced_capture_once, RATE_FILE, COOLDOWN_SUCCESS, COOLDOWN_FAILURE,
)
from test_inplay_openligadb_one_shot import EVENT_ID, URL, NOW, raw, fake_getter


class PacingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"private"
        self.root.mkdir(mode=0o700)

    def call(self,dt=NOW,match_id=EVENT_ID, getter=None):
        return paced_capture_once(match_id,self.root,now=lambda:dt,
                                  getter=getter)

    def test_success_calls_real_one_shot_path_once_and_stores_private_record(self):
        calls=[]
        r=self.call(getter=fake_getter(calls))
        self.assertEqual(calls,[URL])
        self.assertEqual(r["status"],"RESEARCH_ONLY")
        self.assertTrue(r["shared_host_league_pacing_applied"])
        self.assertEqual(r["requests_attempted"],1)
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertFalse(r["source_authenticated"])
        self.assertFalse(r["eligible_for_model_input"])
        self.assertFalse(r["positive_ev_verified"])
        self.assertEqual(r["certified_forward_samples"],0)
        self.assertEqual(stat.S_IMODE((self.root/RATE_FILE).stat().st_mode),0o600)
        self.assertEqual(len(list(self.root.iterdir())),2)
        self.assertTrue(r["original_response_readback_verified"])
        self.assertFalse(r["centralized_across_hosts"])

    def test_same_league_same_game_within_90s_no_network(self):
        calls=[]
        self.call(getter=fake_getter(calls))
        r=self.call(NOW+timedelta(seconds=89),getter=fake_getter(calls))
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["reason"],"SHARED_LEAGUE_RATE_WINDOW")
        self.assertEqual(r["requests_attempted"],0)
        self.assertEqual(calls,[URL])

    def test_different_match_id_same_league_shares_limit(self):
        calls=[]
        self.call(getter=fake_getter(calls))
        r=self.call(NOW+timedelta(seconds=30),EVENT_ID+1,
                    getter=fake_getter(calls))
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(calls,[URL])

    def test_after_90s_second_one_shot_is_permitted(self):
        calls=[]
        a=self.call(getter=fake_getter(calls))
        b=self.call(NOW+timedelta(seconds=COOLDOWN_SUCCESS),getter=fake_getter(calls))
        self.assertEqual([a["status"],b["status"]],["RESEARCH_ONLY","RESEARCH_ONLY"])
        self.assertEqual(calls,[URL,URL])
        self.assertEqual(len(list(self.root.iterdir())),3)  # rate state + 2 time-distinct receipts

    def test_failure_consumes_600s_and_does_not_retry(self):
        calls=[]
        def fail(url):
            calls.append(url)
            raise OSError("secret-token-no-echo")
        r=self.call(getter=fail)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["requests_attempted"],1)
        self.assertNotIn("secret-token",str(r))
        b=self.call(NOW+timedelta(seconds=COOLDOWN_SUCCESS+1),
                    getter=fake_getter(calls))
        self.assertEqual(b["reason"],"SHARED_LEAGUE_RATE_WINDOW")
        self.assertEqual(calls,[URL])
        c=self.call(NOW+timedelta(seconds=COOLDOWN_FAILURE),
                    getter=fake_getter(calls))
        self.assertEqual(c["status"],"RESEARCH_ONLY")
        self.assertEqual(calls,[URL,URL])

    def test_backwards_clock_fails_closed(self):
        self.call(getter=fake_getter([]))
        calls=[]
        r=self.call(NOW-timedelta(seconds=1),getter=fake_getter(calls))
        self.assertEqual(r["reason"],"LOCAL_RATE_CLOCK_MOVED_BACKWARDS")
        self.assertEqual(calls,[])

    def test_malformed_rate_state_fails_closed(self):
        self.call(getter=fake_getter([]))
        marker=self.root/RATE_FILE
        marker.write_text('{"schema":"x","schema":"y"}',encoding="utf-8")
        calls=[]
        r=self.call(NOW+timedelta(minutes=20),getter=fake_getter(calls))
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(calls,[])
        self.assertNotIn("www.",str(r))

    def test_truncated_empty_or_invalid_permission_marker_fails(self):
        for bad in (b"", b"CORRUPT"):
            with self.subTest(bad=bad):
                (self.root/RATE_FILE).write_bytes(bad)
                self.assertEqual(self.call(getter=fake_getter([]))["status"],"HOLD")
        (self.root/RATE_FILE).write_bytes(b'{}')
        (self.root/RATE_FILE).chmod(0o644)
        self.assertEqual(self.call(getter=fake_getter([]))["status"],"HOLD")

    def test_symlink_marker_is_rejected_without_modifying_target(self):
        external=Path(self.tmp.name)/"outside"
        external.write_bytes(b"never-overwrite")
        (self.root/RATE_FILE).symlink_to(external)
        calls=[]
        r=self.call(getter=fake_getter(calls))
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(external.read_bytes(),b"never-overwrite")
        self.assertEqual(calls,[])

    def test_hardlink_marker_rejected(self):
        (self.root/RATE_FILE).write_bytes(b"tampered")
        os.chmod(self.root/RATE_FILE,0o600)
        os.link(self.root/RATE_FILE,self.root/"copy")
        self.assertEqual(self.call(getter=fake_getter([]))["status"],"HOLD")

    def test_bad_root_or_repo_path_fails_before_request(self):
        calls=[]
        self.root.chmod(0o755)
        self.assertEqual(self.call(getter=fake_getter(calls))["status"],"HOLD")
        self.root.chmod(0o700)
        (Path(self.tmp.name)/".git").mkdir()
        self.assertEqual(self.call(getter=fake_getter(calls))["status"],"HOLD")
        self.assertEqual(calls,[])
        self.assertEqual(list(self.root.iterdir()),[])

    def test_invalid_id_does_not_leave_rate_file_or_request(self):
        calls=[]
        for val in (0,True,"12345",-1,1_000_000_000):
            r=self.call(match_id=val,getter=fake_getter(calls))
            self.assertEqual(r["status"],"HOLD")
            self.assertEqual(r["requests_attempted"],0)
        self.assertEqual(calls,[])
        self.assertEqual(list(self.root.iterdir()),[])

    def test_manual_cli_retires_unconditional_match_get(self):
        import io
        import contextlib
        import json
        from unittest.mock import patch
        from inplay_openligadb_one_shot import main
        output=io.StringIO()
        with patch("inplay_openligadb_league_pacing.paced_capture_once",
                   side_effect=AssertionError("LEGACY_NETWORK_PATH_MUST_NOT_RUN")) as paced:
            with contextlib.redirect_stdout(output):
                with self.assertRaises(SystemExit) as result:
                    main(["--match-id",str(EVENT_ID),"--private-root",
                          str(self.root),"--manual-one-shot"])
        self.assertEqual(result.exception.code,2)
        paced.assert_not_called()
        report=json.loads(output.getvalue())
        self.assertEqual(report["reason"],"LEGACY_FULL_MATCH_CLI_DISABLED")
        self.assertEqual(report["production_recommendations"],"DISABLED")
        self.assertFalse(report["eligible_for_model_input"])
        self.assertEqual(list(self.root.iterdir()),[])

    def test_parallel_threads_one_request_same_root(self):
        first_entered=threading.Event()
        release_first=threading.Event()
        calls=[]
        outputs=[]
        def slow_getter(url):
            calls.append(url)
            first_entered.set()
            if not release_first.wait(timeout=5):
                raise RuntimeError("TIMED_OUT")
            return (raw(),200,"application/json",URL)
        def first():
            outputs.append(self.call(getter=slow_getter))
        def second():
            outputs.append(self.call(getter=fake_getter(calls)))
        ta=threading.Thread(target=first,daemon=True)
        ta.start()
        self.assertTrue(first_entered.wait(timeout=4))
        tb=threading.Thread(target=second,daemon=True)
        tb.start()
        time.sleep(.03)
        release_first.set()
        ta.join(timeout=5)
        tb.join(timeout=5)
        self.assertFalse(ta.is_alive())
        self.assertFalse(tb.is_alive())
        self.assertEqual(calls,[URL])
        self.assertEqual(sorted(x["status"] for x in outputs),["HOLD","RESEARCH_ONLY"])


if __name__=="__main__":
    unittest.main()
