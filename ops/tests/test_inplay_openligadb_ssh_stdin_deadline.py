"""Adversarial forced-SSH stdin stream tests. No SSH daemon/provider network."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inplay_openligadb_ssh_stdio_bridge import (
    _read_one_command, relay_stdio_once, MAX_STDIN_BYTES,
)
from inplay_openligadb_central_broker import REQUEST_SCHEMA, _hold as broker_hold
from test_inplay_openligadb_ssh_stdio_bridge import GOOD_SSH,request_bytes


class SSHStdinDeadlineTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)/"private"
        self.root.mkdir(mode=0o700)

    def pipe(self):
        r,w=os.pipe()
        read=os.fdopen(r,"rb",buffering=0)
        self.addCleanup(read.close)
        return read,w

    def send_once(self,read,*,timeout=0.12):
        calls=[]
        output=io.BytesIO()
        def backend(root,command):
            calls.append(command)
            return {**broker_hold("UNATTESTED_LOCAL_PROBE"),
                    "status":"RESEARCH_ONLY",
                    "central_private_broker_used":True,
                    "request_count":1,
                    "change_status":"BASELINE_ONLY",
                    "source_token_sha256_unattested":"a"*64}
        with patch("inplay_openligadb_ssh_stdio_bridge.os.geteuid",return_value=1001):
            with patch("inplay_openligadb_ssh_stdio_bridge.READ_DEADLINE_SECONDS",timeout):
                start=time.monotonic()
                result=relay_stdio_once(self.root,read,output,
                                        environ=GOOD_SSH,broker_request=backend)
                duration=time.monotonic()-start
        self.assertEqual(json.loads(output.getvalue()),result)
        self.assertLess(duration,timeout+0.6)
        self.assertEqual(result["production_recommendations"],"DISABLED")
        self.assertFalse(result["eligible_for_model_input"])
        return result,calls

    def test_valid_pipe_closed_after_one_command_dispatches_once(self):
        reader,writer=self.pipe()
        os.write(writer,request_bytes())
        os.close(writer)
        result,calls=self.send_once(reader)
        self.assertEqual(result["status"],"RESEARCH_ONLY")
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]["action"],"probe")

    def test_valid_line_with_open_writer_times_out_and_does_not_dispatch(self):
        reader,writer=self.pipe()
        self.addCleanup(lambda:os.close(writer))
        os.write(writer,request_bytes())
        result,calls=self.send_once(reader,timeout=0.09)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(result["reason"],"INVALID_SSH_STDIO_COMMAND")
        self.assertEqual(calls,[])

    def test_partial_line_writer_kept_open_times_out(self):
        reader,writer=self.pipe()
        self.addCleanup(lambda:os.close(writer))
        os.write(writer,request_bytes()[:12])
        result,calls=self.send_once(reader,timeout=0.08)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(calls,[])

    def test_no_data_open_pipe_times_out(self):
        reader,writer=self.pipe()
        self.addCleanup(lambda:os.close(writer))
        result,calls=self.send_once(reader,timeout=0.07)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(calls,[])

    def test_slow_trickle_uses_absolute_deadline_not_per_byte_reset(self):
        reader,writer=self.pipe()
        closed=threading.Event()
        def trickle():
            try:
                for byte in request_bytes()[:18]:
                    os.write(writer,bytes([byte]))
                    time.sleep(0.025)
            except OSError:
                pass
            finally:
                os.close(writer)
                closed.set()
        thread=threading.Thread(target=trickle,daemon=True)
        thread.start()
        result,calls=self.send_once(reader,timeout=0.085)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(calls,[])
        self.assertTrue(closed.wait(timeout=2))
        thread.join(timeout=2)

    def test_double_command_with_immediate_eof_rejected(self):
        reader,writer=self.pipe()
        os.write(writer,request_bytes()+request_bytes())
        os.close(writer)
        result,calls=self.send_once(reader)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(calls,[])

    def test_oversized_stream_with_open_writer_rejected_immediately(self):
        reader,writer=self.pipe()
        self.addCleanup(lambda:os.close(writer))
        os.write(writer,b"x"*(MAX_STDIN_BYTES+2))
        result,calls=self.send_once(reader,timeout=0.08)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(calls,[])

    def test_eof_without_newline_rejected(self):
        reader,writer=self.pipe()
        os.write(writer,request_bytes().rstrip(b"\n"))
        os.close(writer)
        result,calls=self.send_once(reader)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(calls,[])

    def test_environment_denial_does_not_wait_on_open_pipe(self):
        reader,writer=self.pipe()
        self.addCleanup(lambda:os.close(writer))
        output=io.BytesIO()
        with patch("inplay_openligadb_ssh_stdio_bridge.os.geteuid",return_value=1001):
            start=time.monotonic()
            report=relay_stdio_once(self.root,reader,output,environ={"CI":"true"})
            delta=time.monotonic()-start
        self.assertEqual(report["status"],"HOLD")
        self.assertLess(delta,0.4)

    def test_memory_buffer_keeps_existing_synthetic_test_compatibility(self):
        assert _read_one_command(io.BytesIO(request_bytes()),timeout_seconds=0.01)==request_bytes()
        assert _read_one_command(io.BytesIO(request_bytes()+request_bytes()),
                                 timeout_seconds=0.01) is None
        assert _read_one_command(io.BytesIO(b"SECRETS"*200),
                                 timeout_seconds=0.01) is None

    def test_invalid_timeout_configuration_fails_closed(self):
        data=io.BytesIO(request_bytes())
        for value in (0,-1,True,float("nan"),"bad",None,10000):
            with self.subTest(value=value):
                self.assertIsNone(_read_one_command(data,timeout_seconds=value))
                data.seek(0)

if __name__=="__main__":
    unittest.main()
