"""Offline Unix-socket central research broker tests; no real provider requests."""
import contextlib
import io
from datetime import timedelta
import json
import os
from pathlib import Path
import socket
import stat
import tempfile
import threading
import time
import unittest
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from inplay_openligadb_central_broker import (
    open_private_broker, request_private_broker, BROKER_SOCKET, REQUEST_SCHEMA,
    BrokerError,
)
from test_inplay_openligadb_one_shot import NOW, EVENT_ID, URL, raw
from test_inplay_openligadb_conditional_capture import valid_match
from test_inplay_openligadb_lastchange_probe import ENDPOINT, TOKEN1, TOKEN2


def command(action="probe", **additional):
    body={"schema":REQUEST_SCHEMA,"action":action,"season":2026,"group":8}
    body.update(additional)
    return body


class CentralBrokerOfflineTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)/"private"
        self.root.mkdir(mode=0o700)
        self.clock=[NOW]
        self.probe_calls=[]
        self.match_calls=[]
        self.tokens=[TOKEN1,TOKEN2]
        self.broker=None
        self.thread=None

    def probe_getter(self,url):
        self.probe_calls.append(url)
        token=self.tokens.pop(0) if self.tokens else TOKEN2
        return token.encode(),200,"application/json",ENDPOINT

    def match_getter(self,url):
        self.match_calls.append(url)
        return raw(valid_match()),200,"application/json",URL

    def start(self):
        self.broker=open_private_broker(
            self.root,probe_getter=self.probe_getter,
            match_getter=self.match_getter,now=lambda:self.clock[0])
        self.thread=threading.Thread(target=self.broker.serve_forever,
                                     kwargs={"poll_interval":0.01},daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        return self.broker

    def stop(self):
        if self.broker is None:
            return
        self.broker.shutdown()
        self.broker.server_close()
        self.thread.join(timeout=3)
        self.broker=None

    def query(self,cmd):
        return request_private_broker(self.root,cmd)

    def test_private_socket_created_owner_only_with_no_http(self):
        self.start()
        path=self.root/BROKER_SOCKET
        info=path.lstat()
        self.assertTrue(stat.S_ISSOCK(info.st_mode))
        self.assertEqual(stat.S_IMODE(info.st_mode),0o600)
        self.assertEqual(self.probe_calls,[])
        self.assertEqual(self.match_calls,[])
        self.assertEqual(list(self.root.iterdir()),[path])

    def test_two_probes_then_one_conditional_capture_centralized(self):
        self.start()
        baseline=self.query(command())
        self.assertEqual(baseline["status"],"RESEARCH_ONLY")
        self.assertEqual(baseline["change_status"],"BASELINE_ONLY")
        self.assertFalse(baseline["source_authenticated"])
        self.assertFalse(baseline["cross_host_firewall_verified"])
        self.assertFalse(baseline["eligible_for_model_input"])
        self.assertFalse(baseline["positive_ev_verified"])
        self.assertEqual(baseline["certified_forward_samples"],0)
        self.assertEqual(baseline["production_recommendations"],"DISABLED")
        self.clock[0]+=timedelta(seconds=90)
        changed=self.query(command())
        self.assertEqual(changed["change_status"],"CHANGED_UNATTESTED")
        self.clock[0]+=timedelta(seconds=90)
        captured=self.query(command("capture",match_id=EVENT_ID))
        self.assertEqual(captured["status"],"RESEARCH_ONLY")
        self.assertTrue(captured["local_raw_response_readback_verified"])
        self.assertEqual(len(captured["archive_sha256_unattested"]),64)
        self.assertEqual(self.probe_calls,[ENDPOINT,ENDPOINT])
        self.assertEqual(self.match_calls,[URL])
        self.assertFalse(captured["source_authenticated"])
        self.assertFalse(captured["eligible_for_model_input"])
        self.assertFalse(captured["cross_host_firewall_verified"])
        self.assertNotIn("Synthetic Home",str(captured))
        self.assertNotIn("api.openligadb.de",str(captured))

    def test_capture_before_changed_token_does_not_request_or_create_archive(self):
        self.start()
        result=self.query(command("capture",match_id=EVENT_ID))
        self.assertEqual(result["status"],"HOLD")
        self.assertFalse(result["local_raw_response_readback_verified"])
        self.assertEqual(self.probe_calls,[])
        self.assertEqual(self.match_calls,[])
        self.assertFalse(any(p.name.endswith(".tar") for p in self.root.iterdir()))

    def test_two_clients_share_one_source_gate_not_independent_limits(self):
        self.start()
        outcomes=[]
        threads=[threading.Thread(target=lambda:outcomes.append(self.query(command())),
                                  daemon=True) for _ in range(2)]
        for worker in threads: worker.start()
        for worker in threads: worker.join(timeout=5)
        self.assertTrue(all(not worker.is_alive() for worker in threads))
        self.assertEqual(len(outcomes),2)
        self.assertEqual(sorted(x["status"] for x in outcomes),["HOLD","RESEARCH_ONLY"])
        self.assertEqual(self.probe_calls,[ENDPOINT])
        self.assertEqual(self.match_calls,[])

    def test_client_cannot_supply_arbitrary_url_provider_or_secrets(self):
        self.start()
        for payload in (
            command(url="https://evil.example"),
            command(provider="evil"),
            command(api_key="SHOULD_NOT_PRINT"),
            command("get_url",url="https://evil.example"),
            command("capture",match_id=EVENT_ID,token="fake"),
        ):
            result=self.query(payload)
            self.assertEqual(result["status"],"HOLD")
            self.assertEqual(result["reason"],"INVALID_BROKER_COMMAND")
            self.assertNotIn("SHOULD_NOT_PRINT",str(result))
        self.assertEqual(self.probe_calls,[])
        self.assertEqual(self.match_calls,[])

    def test_invalid_types_and_unknown_fields_fail_closed(self):
        self.start()
        for invalid in (
            command(season=True),command(group=0),command(group="8"),
            command("capture",match_id=True),
            command("capture",match_id="12345"),
            command("capture",match_id=0),
            command("probe",match_id=EVENT_ID),
        ):
            self.assertEqual(self.query(invalid)["status"],"HOLD")
        self.assertEqual(self.probe_calls,[])

    def test_duplicate_json_keys_nonfinite_and_non_object_refused(self):
        self.start()
        for payload in (
            b'{"schema":"x","action":"probe","action":"capture"}\n',
            b'{"schema":"x","group":NaN}\n',b'[]\n',
            b'SECRET_CANNOT_LEAK\n',b'\xff\xff\n',
        ):
            reply=request_private_broker(self.root,payload)
            self.assertEqual(reply["status"],"HOLD")
            self.assertNotIn("SECRET_CANNOT_LEAK",str(reply))

    def test_request_size_bound_and_no_multicommand_privilege(self):
        self.start()
        too_big=b"X"*2000+b"\n"
        result=request_private_broker(self.root,too_big)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(self.probe_calls,[])

    def test_private_root_public_mode_rejected_on_each_connection(self):
        self.start()
        self.root.chmod(0o755)
        try:
            result=self.query(command())
            self.assertEqual(result["status"],"HOLD")
            self.assertEqual(result["reason"],"BROKER_ENDPOINT_NOT_PRIVATE")
            self.assertEqual(self.probe_calls,[])
        finally:
            self.root.chmod(0o700)

    def test_socket_permission_changed_refused(self):
        self.start()
        path=self.root/BROKER_SOCKET
        path.chmod(0o666)
        try:
            result=self.query(command())
            self.assertEqual(result["status"],"HOLD")
            self.assertEqual(self.probe_calls,[])
        finally:
            path.chmod(0o600)

    def test_preexisting_symlink_socket_path_is_not_removed(self):
        target=self.root/"outside-do-not-touch"
        target.write_bytes(b"SAFE")
        (self.root/BROKER_SOCKET).symlink_to(target)
        with self.assertRaises(BrokerError):
            open_private_broker(self.root,
                                probe_getter=self.probe_getter,
                                match_getter=self.match_getter)
        self.assertEqual(target.read_bytes(),b"SAFE")
        self.assertTrue((self.root/BROKER_SOCKET).is_symlink())

    def test_git_repo_or_wrong_permission_directory_rejected(self):
        self.root.chmod(0o755)
        with self.assertRaises(BrokerError):
            open_private_broker(self.root,probe_getter=self.probe_getter,
                                match_getter=self.match_getter)
        self.root.chmod(0o700)
        (self.root.parent/".git").mkdir()
        with self.assertRaises(BrokerError):
            open_private_broker(self.root,probe_getter=self.probe_getter,
                                match_getter=self.match_getter)

    def test_socket_removed_safely_on_server_stop(self):
        self.start()
        filename=self.root/BROKER_SOCKET
        self.assertTrue(filename.exists())
        self.stop()
        self.assertFalse(filename.exists())

    def test_no_provider_get_without_injected_fake_callbacks_in_ci(self):
        # The server process checks the same manual-egress gate as PR552
        # before it can start serving real transport requests.
        from unittest.mock import patch
        from inplay_openligadb_central_broker import main
        with patch.dict(os.environ,{"CI":"true"},clear=True):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(SystemExit) as stop:
                    main(["--private-root",str(self.root),"--serve-manual-broker"])
        self.assertEqual(stop.exception.code,2)
        self.assertEqual(list(self.root.iterdir()),[])
        report=json.loads(output.getvalue())
        self.assertEqual(report["status"],"HOLD")
        self.assertIsNone(report["source_token_sha256_unattested"])
        self.assertFalse(report["central_private_broker_used"])
        self.assertNotIn(TOKEN1.strip('"'),output.getvalue())

if __name__=="__main__":
    unittest.main()
