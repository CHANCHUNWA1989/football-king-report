"""SSH forced-command stdio bridge: strictly offline test cases."""
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from inplay_openligadb_ssh_stdio_bridge import (
    inspect_ssh_forced_context, relay_stdio_once, main,
    BRIDGE_SCHEMA, MAX_STDIN_BYTES,
)
from inplay_openligadb_central_broker import (
    _hold as broker_hold, REQUEST_SCHEMA, SCHEMA as BROKER_SCHEMA,
    open_private_broker,
)


GOOD_SSH={
    "SSH_CONNECTION":"192.0.2.10 44220 192.0.2.20 22",
    "SSH_ORIGINAL_COMMAND":"",
}
CMD={"schema":REQUEST_SCHEMA,"action":"probe","season":2026,"group":8}


def request_bytes(command=None):
    return json.dumps(CMD if command is None else command,
                      sort_keys=True,separators=(",",":")).encode()+b"\n"


def good_reply():
    return {
        **broker_hold("UNATTESTED_LOCAL_PROBE"),
        "status":"RESEARCH_ONLY",
        "central_private_broker_used":True,
        "request_count":1,
        "change_status":"BASELINE_ONLY",
        "source_token_sha256_unattested":"a"*64,
    }


class ForcedSSHStdioBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"private"
        self.root.mkdir(mode=0o700)
        self.seen=[]

    def inspect(self,env=None,uid=1001):
        with patch("inplay_openligadb_ssh_stdio_bridge.os.geteuid",
                   return_value=uid):
            return inspect_ssh_forced_context(
                GOOD_SSH if env is None else env)

    def run_one(self,data=None,env=None,broker_reply=None):
        input_bytes=io.BytesIO(request_bytes() if data is None else data)
        output_bytes=io.BytesIO()
        calls=self.seen
        def backend(root,cmd):
            calls.append((root,cmd))
            return good_reply() if broker_reply is None else broker_reply
        with patch("inplay_openligadb_ssh_stdio_bridge.os.geteuid",
                   return_value=1001):
            result=relay_stdio_once(self.root,input_bytes,output_bytes,
                                    environ=GOOD_SSH if env is None else env,
                                    broker_request=backend)
        decoded=json.loads(output_bytes.getvalue())
        self.assertEqual(decoded,result)
        self.assertEqual(decoded["production_recommendations"],"DISABLED")
        self.assertFalse(decoded["eligible_for_model_input"])
        self.assertEqual(decoded["certified_forward_samples"],0)
        self.assertFalse(decoded["ssh_authentication_independently_verified"])
        self.assertFalse(decoded["cross_host_firewall_verified"])
        self.assertFalse(decoded["positive_ev_verified"])
        self.assertIsNone(decoded["recommendation"])
        return decoded

    def test_missing_ssh_context_defaults_hold(self):
        out=self.inspect({})
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["reason"],"SSH_FORCED_SESSION_NOT_PRESENT")
        self.assertFalse(out["ssh_authentication_independently_verified"])

    def test_well_formed_forced_ssh_env_is_only_local_syntax_not_authentication(self):
        out=self.inspect()
        self.assertEqual(out["status"],"RESEARCH_ONLY")
        self.assertTrue(out["ssh_session_structure_checked"])
        self.assertFalse(out["sshd_forced_command_policy_verified"])
        self.assertFalse(out["ssh_authentication_independently_verified"])
        self.assertFalse(out["cross_host_firewall_verified"])
        self.assertEqual(out["production_recommendations"],"DISABLED")

    def test_original_remote_shell_command_rejected(self):
        for injected in ("sh -c id",";cat /secrets","probe"," ", "bash"):
            with self.subTest(injected=injected):
                out=self.inspect({**GOOD_SSH,"SSH_ORIGINAL_COMMAND":injected})
                self.assertEqual(out["status"],"HOLD")
                self.assertEqual(out["reason"],"SSH_ORIGINAL_COMMAND_FORBIDDEN")

    def test_pty_agent_x11_ci_and_forwarding_markers_rejected(self):
        for name in ("SSH_TTY","SSH_AUTH_SOCK","DISPLAY","GITHUB_ACTIONS",
                     "CI","RUNNER_OS","ACTIONS_RUNTIME_TOKEN"):
            env={**GOOD_SSH,name:"false"}
            self.assertEqual(self.inspect(env)["status"],"HOLD")

    def test_bad_ssh_connection_ip_or_port_rejected(self):
        bad=("","not-an-ip 10 192.0.2.20 22",
             "192.0.2.10 nope 192.0.2.20 22",
             "192.0.2.10 0 192.0.2.20 22",
             "192.0.2.10 44220 192.0.2.20 65536",
             "192.0.2.10 44220 localhost 22",
             "192.0.2.10 44220 192.0.2.20 22 EXTRA")
        for value in bad:
            with self.subTest(value=value):
                self.assertEqual(self.inspect({**GOOD_SSH,"SSH_CONNECTION":value})["status"],"HOLD")

    def test_root_execution_rejected(self):
        out=self.inspect(uid=0)
        self.assertEqual(out["reason"],"PRIVILEGED_SSH_RELAY_FORBIDDEN")

    def test_valid_single_probe_relays_exact_command_and_safe_status(self):
        out=self.run_one()
        self.assertEqual(out["status"],"RESEARCH_ONLY")
        self.assertEqual(out["change_status"],"BASELINE_ONLY")
        self.assertEqual(out["source_token_sha256_unattested"],"a"*64)
        self.assertTrue(out["central_private_broker_used"])
        self.assertEqual(self.seen,[(self.root,CMD)])

    def test_unknown_fields_url_api_key_and_unapproved_actions_rejected(self):
        for value in ({**CMD,"url":"https://evil.example"},
                      {**CMD,"api_key":"DONOTPRINT"},
                      {**CMD,"action":"run_shell"},
                      {**CMD,"match_id":12345}):
            self.seen.clear()
            out=self.run_one(request_bytes(value))
            self.assertEqual(out["status"],"HOLD")
            self.assertEqual(self.seen,[])
            self.assertNotIn("DONOTPRINT",str(out))
            self.assertNotIn("evil.example",str(out))

    def test_duplicate_json_keys_nan_garbage_and_newlines_rejected(self):
        bad=(b'{"schema":"x","action":"probe","action":"capture"}\n',
             b'{"schema":"x","season":NaN}\n',
             b'ENCRYPTED_SECRET\n',b'\xff\n',b'[]\n',
             request_bytes()+request_bytes(),
             request_bytes()+b"evil")
        for data in bad:
            with self.subTest(data=data[:18]):
                self.seen.clear()
                out=self.run_one(data)
                self.assertEqual(out["status"],"HOLD")
                self.assertEqual(self.seen,[])
                self.assertNotIn("ENCRYPTED_SECRET",str(out))

    def test_oversized_input_rejected_without_broker(self):
        out=self.run_one(b"x"*(MAX_STDIN_BYTES+1)+b"\n")
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(self.seen,[])

    def test_empty_input_and_non_newline_payload_rejected(self):
        for raw in (b"", b"{}",request_bytes().rstrip(b"\n")):
            with self.subTest(raw=raw):
                self.seen.clear()
                self.assertEqual(self.run_one(raw)["status"],"HOLD")
                self.assertEqual(self.seen,[])

    def test_env_denial_before_read_or_broker(self):
        env={**GOOD_SSH,"SSH_TTY":"/dev/pts/0"}
        out=self.run_one(env=env)
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(self.seen,[])

    def test_malicious_broker_text_and_fields_do_not_leak(self):
        untrusted={**good_reply(),
                   "raw_source_response":"TOP_SECRET_PROVIDER_BODY",
                   "source_url":"https://secret.example/path"}
        out=self.run_one(broker_reply=untrusted)
        self.assertEqual(out["status"],"HOLD")
        self.assertNotIn("TOP_SECRET_PROVIDER_BODY",str(out))
        self.assertNotIn("secret.example",str(out))

    def test_invalid_broker_status_digest_and_schema_fail_closed(self):
        for change in ({"status":"PRODUCTION"},
                       {"source_token_sha256_unattested":"BAD"},
                       {"schema":"other"},
                       {"production_recommendations":"ENABLED"},
                       {"eligible_for_model_input":True}):
            reply={**good_reply(),**change}
            out=self.run_one(broker_reply=reply)
            self.assertEqual(out["status"],"HOLD")

    def test_backend_exception_no_secret_leak(self):
        inp=io.BytesIO(request_bytes())
        output=io.BytesIO()
        def failure(root,cmd):
            raise RuntimeError("API_TOKEN_NEVER_ECHO")
        with patch("inplay_openligadb_ssh_stdio_bridge.os.geteuid",
                   return_value=1001):
            result=relay_stdio_once(self.root,inp,output,environ=GOOD_SSH,
                                    broker_request=failure)
        self.assertEqual(result["status"],"HOLD")
        self.assertNotIn("API_TOKEN_NEVER_ECHO",str(result))

    def test_cli_refuses_ci_without_trying_real_broker(self):
        with patch.dict(os.environ,{"CI":"true"},clear=True):
            with patch("inplay_openligadb_ssh_stdio_bridge.request_private_broker",
                       side_effect=AssertionError("SHOULD_NOT_CALL")) as backend:
                with patch("inplay_openligadb_ssh_stdio_bridge.sys.stdin") as stdin:
                    with patch("inplay_openligadb_ssh_stdio_bridge.sys.stdout") as stdout:
                        stdin.buffer=io.BytesIO(request_bytes())
                        stdout.buffer=io.BytesIO()
                        with self.assertRaises(SystemExit) as stopped:
                            main(["--private-root",str(self.root),
                                  "--forced-ssh-stdio"])
                        self.assertEqual(stopped.exception.code,2)
                        backend.assert_not_called()
                        report=json.loads(stdout.buffer.getvalue())
                        self.assertEqual(report["status"],"HOLD")

if __name__=="__main__":
    unittest.main()
