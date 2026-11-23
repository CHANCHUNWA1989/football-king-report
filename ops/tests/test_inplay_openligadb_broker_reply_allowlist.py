"""Fail-closed local broker reply boundary; OFFLINE fake Unix server only.

Security regression: the client previously checked only four reply fields,
then returned the entire untrusted JSON unchanged. Extra fields (provider
raw body, URL, secrets) or false security attestation could reach callers.
"""
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from inplay_openligadb_central_broker import (
    _hold, _validated_broker_reply, request_private_broker,
    REQUEST_SCHEMA, BROKER_SOCKET,
)

REQUEST={"schema":REQUEST_SCHEMA,"action":"probe","season":2026,"group":8}
SHA="a"*64

def good_probe():
    return {
        **_hold("UNATTESTED_LOCAL_PROBE"),
        "status":"RESEARCH_ONLY",
        "central_private_broker_used":True,
        "request_count":1,
        "change_status":"BASELINE_ONLY",
        "source_token_sha256_unattested":SHA,
    }

def good_capture():
    return {
        **_hold("UNATTESTED_LOCAL_CAPTURE"),
        "status":"RESEARCH_ONLY",
        "central_private_broker_used":True,
        "request_count":1,
        "archive_sha256_unattested":"b"*64,
        "local_raw_response_readback_verified":True,
    }


class BrokerReplyAllowlistTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"private"
        self.root.mkdir(mode=0o700)

    def client_via_fake_unix_socket(self,reply,command=None):
        """A malicious same-UID fake server, not real source HTTP."""
        path=self.root/BROKER_SOCKET
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
            server.bind(str(path))
            path.chmod(0o600)
            server.listen(1)
            server.settimeout(3)
            finished=[]
            def speak():
                try:
                    peer,_=server.accept()
                    with peer:
                        peer.settimeout(3)
                        peer.recv(1024)
                        peer.sendall(json.dumps(reply,ensure_ascii=False).encode()+b"\n")
                except Exception as exc:
                    finished.append(type(exc).__name__)
            worker=threading.Thread(target=speak,daemon=True)
            worker.start()
            result=request_private_broker(self.root,REQUEST if command is None else command)
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(finished,[])
            return result

    def test_good_probe_is_kept_safe_and_consistent(self):
        out=self.client_via_fake_unix_socket(good_probe())
        self.assertEqual(out["status"],"RESEARCH_ONLY")
        self.assertEqual(out["change_status"],"BASELINE_ONLY")
        self.assertEqual(out["source_token_sha256_unattested"],SHA)
        self.assertFalse(out["source_authenticated"])
        self.assertFalse(out["eligible_for_model_input"])
        self.assertFalse(out["positive_ev_verified"])
        self.assertEqual(out["production_recommendations"],"DISABLED")

    def test_good_capture_valid_when_action_is_capture(self):
        command={**REQUEST,"action":"capture","match_id":12345}
        out=self.client_via_fake_unix_socket(good_capture(),command)
        self.assertEqual(out["status"],"RESEARCH_ONLY")
        self.assertEqual(out["archive_sha256_unattested"],"b"*64)
        self.assertTrue(out["local_raw_response_readback_verified"])

    def test_reject_extra_fields_in_untrusted_local_reply_without_leaking(self):
        reply={**good_probe(),
               "raw_source_response":"PRIVATE_MATCH_JSON_NEVER_EXPOSE",
               "provider_url":"https://not-a-safe-host.example/private"}
        out=self.client_via_fake_unix_socket(reply)
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["reason"],"BROKER_REPLY_INVALID")
        self.assertNotIn("PRIVATE_MATCH_JSON_NEVER_EXPOSE",repr(out))
        self.assertNotIn("not-a-safe-host",repr(out))
        self.assertEqual(set(out),set(_hold()))

    def test_reject_missing_mandatory_fields_or_wrong_response_schema(self):
        for mutation in ({"schema":"untrusted"},{"eligible_for_model_input":True},
                         {"production_recommendations":"ENABLED"}):
            with self.subTest(mutation=mutation):
                out=_validated_broker_reply({**good_probe(),**mutation},"probe")
                self.assertEqual(out["reason"],"BROKER_REPLY_INVALID")
        missing=good_probe()
        del missing["provider_time_authenticated"]
        self.assertEqual(_validated_broker_reply(missing,"probe")["status"],"HOLD")

    def test_reject_forged_host_firewall_and_forward_sample_claims(self):
        changes=[
            {"centralized_across_hosts_verified":True},
            {"cross_host_firewall_verified":True},
            {"socket_authentication_is_cross_host_mtls":True},
            {"source_authenticated":True},
            {"provider_time_authenticated":True},
            {"eligible_for_model_scoring":True},
            {"positive_ev_verified":True},
            {"certified_forward_samples":1},
            {"certified_forward_samples":False},  # Python bool equals int zero!
            {"recommendation":"BUY NOW"},
            {"roi":999},
        ]
        for change in changes:
            with self.subTest(change=change):
                out=_validated_broker_reply({**good_probe(),**change},"probe")
                self.assertEqual(out["status"],"HOLD")
                self.assertEqual(out["reason"],"BROKER_REPLY_INVALID")

    def test_reject_malicious_reason_and_status_mismatch(self):
        for mutated in (
            {**good_probe(),"reason":"SENSITIVE_TOKEN_SECRET"},
            {**good_probe(),"reason":"BROKER_PEER_NOT_AUTHORIZED"},
            {**good_probe(),"status":"HOLD"},
            {**_hold("UNATTESTED_LOCAL_PROBE")},
            {**_hold("SENSITIVE_SOURCE_SERVER_ERROR")},
        ):
            with self.subTest(status=mutated["status"],reason=mutated["reason"]):
                out=_validated_broker_reply(mutated,"probe")
                self.assertEqual(out["status"],"HOLD")
                self.assertNotIn("SENSITIVE",repr(out))

    def test_reject_bad_types_digests_metadata_and_fake_capture(self):
        changes=[
            {"request_count":True},{"request_count":"1"},{"request_count":-1},
            {"central_private_broker_used":1},
            {"change_status":"CHANGED_IN_PRODUCTION"},
            {"source_token_sha256_unattested":"not-a-sha"},
            {"source_token_sha256_unattested":"A"*64},
            {"archive_sha256_unattested":"b"*64},
            {"local_raw_response_readback_verified":True},
        ]
        for change in changes:
            with self.subTest(change=change):
                out=_validated_broker_reply({**good_probe(),**change},"probe")
                self.assertEqual(out["status"],"HOLD")

    def test_wrong_action_or_incomplete_capture_fails_closed(self):
        self.assertEqual(_validated_broker_reply(good_probe(),"capture")["status"],"HOLD")
        self.assertEqual(_validated_broker_reply(good_capture(),"probe")["status"],"HOLD")
        self.assertEqual(_validated_broker_reply(good_probe(),None)["status"],"HOLD")
        for change in ({"archive_sha256_unattested":None},
                       {"local_raw_response_readback_verified":False},
                       {"change_status":"BASELINE_ONLY"}):
            self.assertEqual(_validated_broker_reply({**good_capture(),**change},
                                                     "capture")["status"],"HOLD")

    def test_request_with_invalid_command_cannot_get_research_reply(self):
        malformed={**REQUEST,"url":"https://untrusted.example"}
        out=self.client_via_fake_unix_socket(good_probe(),malformed)
        self.assertEqual(out["status"],"HOLD")
        self.assertNotIn("untrusted.example",repr(out))

    def test_valid_broker_hold_reason_preserved_without_extra_fields(self):
        for reason in ("INVALID_BROKER_COMMAND","BROKER_ENDPOINT_NOT_PRIVATE",
                       "UPSTREAM_RESEARCH_GATE_HOLD","BROKER_REQUEST_UNAVAILABLE"):
            report=_validated_broker_reply(_hold(reason),None)
            self.assertEqual(report["status"],"HOLD")
            self.assertEqual(report["reason"],reason)
            self.assertEqual(set(report),set(_hold()))

    def test_unknown_hold_reason_or_untrusted_reply_shape_is_rejected(self):
        for reply in (
            {**_hold(),"reason":"TOKEN_TOP_SECRET"},
            {**_hold(),"request_count":"1"},
            {**_hold(),"source_token_sha256_unattested":SHA},
            ["HOLD"], None, "SECRET", 123,
        ):
            out=_validated_broker_reply(reply,"probe")
            self.assertEqual(out["reason"],"BROKER_REPLY_INVALID")
            self.assertNotIn("TOKEN_TOP_SECRET",repr(out))

    def test_client_never_exposes_fake_socket_secret_reason(self):
        out=self.client_via_fake_unix_socket({**_hold(),"reason":"MY_SENSITIVE_KEY"})
        self.assertEqual(out["reason"],"BROKER_REPLY_INVALID")
        self.assertNotIn("MY_SENSITIVE_KEY",repr(out))


if __name__=="__main__":
    unittest.main()
