import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from circuit_checkpoint import save,restore
from circuit_policy import start,advance,snapshot
from test_circuit_policy import at,observation

class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"checkpoint.json"
    def ready(self):
        s=start("football",at(0))
        for t in (300,330,360):s=advance(s,observation("football",t),at(t))
        return s
    def assert_open(self,s):
        self.assertEqual((s.phase,s.successes),("OPEN",0))
        self.assertFalse(snapshot(s)["model_input_allowed"])
    def test_restart_reopens_ready(self):
        save(self.path,self.ready())
        s,status=restore(self.path,"football",at(400))
        self.assert_open(s);self.assertEqual(status,"RESTORED_OPEN")
        self.assertEqual(s.reopen_until,at(700))
        self.assertEqual(s.last_source_captures,(at(360),at(360)))
    def test_missing(self):
        s,status=restore(self.path,"football",at(400))
        self.assert_open(s);self.assertEqual(status,"RESET_OPEN")
    def test_corrupt(self):
        save(self.path,self.ready());self.path.write_text("{")
        s,status=restore(self.path,"football",at(400))
        self.assert_open(s);self.assertEqual(status,"RESET_OPEN")
    def test_tampered(self):
        save(self.path,self.ready())
        d=json.loads(self.path.read_text());d["payload"]["domain"]="quant"
        self.path.write_text(json.dumps(d))
        s,status=restore(self.path,"quant",at(400))
        self.assert_open(s);self.assertEqual(status,"RESET_OPEN")
    def test_wrong_domain(self):
        save(self.path,self.ready())
        s,status=restore(self.path,"quant",at(400))
        self.assert_open(s);self.assertEqual(status,"RESET_OPEN")
    def test_clock_rollback(self):
        save(self.path,self.ready())
        s,status=restore(self.path,"football",at(100))
        self.assert_open(s);self.assertEqual(s.last_checked,at(360))
        self.assertEqual(s.reopen_until,at(660))
    def test_oversize(self):
        self.path.write_bytes(b"x"*8193)
        s,status=restore(self.path,"football",at(400))
        self.assert_open(s);self.assertEqual(status,"RESET_OPEN")
    def test_replace(self):
        save(self.path,start("football",at(0)));save(self.path,self.ready())
        s,status=restore(self.path,"football",at(400))
        self.assertEqual(s.last_capture,at(360))
        self.assertEqual(list(self.path.parent.iterdir()),[self.path])
if __name__=="__main__":unittest.main(verbosity=2)
