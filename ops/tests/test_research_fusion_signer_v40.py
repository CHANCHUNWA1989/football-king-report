import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from ops.tests.test_research_prospective_fusion_v38 import example,NOW
from ops.research_prospective_fusion_v38 import sha,canonical,replay
from ops.research_fusion_signer_v40 import prepare

def draft():
    d=example();d.pop("forecast_utc");d["schema"]="prospective-fusion-draft-v40"
    d["market"]["source_id"]="the-odds-api.com:v4"
    return d
def write(root,d):
    p=root/"research"/"fusion-inputs";p.mkdir(parents=True,exist_ok=True)
    b=canonical(d);h=sha(b);(p/(h+".json")).write_bytes(b)
    return h
class FusionSignerTests(unittest.TestCase):
    def test_prepare_and_replay(self):
        with TemporaryDirectory() as t:
            root=Path(t);h=write(root,draft())
            raw,receipt=prepare(root,h,now=NOW)
            self.assertEqual(json.loads(raw)["forecast_utc"],NOW)
            self.assertEqual(replay(json.loads(receipt),raw),json.loads(receipt))
    def test_injected_forecast_rejected(self):
        with TemporaryDirectory() as t:
            root=Path(t);d=draft();d["forecast_utc"]=NOW
            with self.assertRaises(ValueError):prepare(root,write(root,d),now=NOW)
    def test_private_provider_rejected(self):
        with TemporaryDirectory() as t:
            root=Path(t);d=draft();d["market"]["source_id"]="propline:v1"
            with self.assertRaises(ValueError):prepare(root,write(root,d),now=NOW)
    def test_modified_file_rejected(self):
        with TemporaryDirectory() as t:
            root=Path(t);h=write(root,draft())
            (root/"research"/"fusion-inputs"/(h+".json")).write_text("{}")
            with self.assertRaises(ValueError):prepare(root,h,now=NOW)
    def test_stale_market_rejected(self):
        with TemporaryDirectory() as t:
            root=Path(t);d=draft();d["market"]["captured_utc"]="2026-11-28T10:59:59Z"
            with self.assertRaises(ValueError):prepare(root,write(root,d),now=NOW)
    def test_path_traversal_rejected(self):
        with TemporaryDirectory() as t:
            with self.assertRaises(ValueError):prepare(Path(t),"../x",now=NOW)
    def test_workflow_permissions_and_trigger(self):
        root=Path(__file__).resolve().parents[2]
        w=(root/".github/workflows/football-king-fusion-witness.yml").read_text()
        self.assertIn("workflow_dispatch:",w)
        self.assertIn("github.ref == 'refs/heads/main'",w)
        self.assertIn("persist-credentials: false",w)
        self.assertIn("contents: read",w)
        self.assertNotIn("contents: write",w)
        self.assertNotIn("pull_request:",w)
        self.assertNotIn("schedule:",w)
