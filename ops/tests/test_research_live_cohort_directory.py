import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ops.tests.test_research_live_pipeline_v10 import case
from ops.research_live_cohort_directory import load,run,public_summary,SCHEMA
NOW="2026-11-30T00:00:00Z"

def write(root,cases):
    members=[]
    for c in cases:
        row=dict(c)
        row["raw_captures"]=[x.hex() for x in c["raw_captures"]]
        raw=json.dumps(row,sort_keys=True).encode()
        sha=hashlib.sha256(raw).hexdigest()
        (root/(sha+".json")).write_bytes(raw);members.append(sha)
    m=dict(schema=SCHEMA,model_release="test",train_start="2026-11-27T00:00:00Z",
           train_cutoff="2026-11-28T00:00:00Z",test_end="2026-11-29T00:00:00Z",members=members)
    (root/"manifest.json").write_text(json.dumps(m),encoding="utf-8")
    return members
class DirectoryTests(unittest.TestCase):
    def test_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);write(root,[case(True)])
            r=run(root,as_of=NOW)
            self.assertTrue(r["pipeline_replay_passed"])
            self.assertEqual(r["candidate_pairs"],1)
            self.assertEqual(r["authenticated_samples"],0)
    def test_mutation_and_extra(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ids=write(root,[case()])
            path=root/(ids[0]+".json")
            path.write_bytes(path.read_bytes()+b" ")
            self.assertFalse(run(root,as_of=NOW)["pipeline_replay_passed"])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);write(root,[case()])
            (root/"extra.json").write_text("{}")
            self.assertFalse(run(root,as_of=NOW)["pipeline_replay_passed"])
    def test_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ids=write(root,[case()])
            path=root/(ids[0]+".json");path.unlink();path.symlink_to(root/"manifest.json")
            self.assertFalse(run(root,as_of=NOW)["pipeline_replay_passed"])
    def test_aggregate_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);write(root,[case()])
            with patch("ops.research_live_cohort_directory.MAX_TOTAL",100):
                self.assertFalse(run(root,as_of=NOW)["pipeline_replay_passed"])
    def test_large_directory_loader_only(self):
        # Deliberately synthetic padding to exercise >2MB loading, not real matches.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            rows=[]
            for i in range(200):
                rows.append(dict(raw_captures=[b"{}"]*5,padding="x"*12000,index=i))
            write(root,rows)
            _,loaded,size,_=load(root)
            self.assertEqual(len(loaded),200)
            self.assertGreater(size,2_000_000)
            # These are not valid cases and must never be scored.
            self.assertFalse(run(root,as_of=NOW)["pipeline_replay_passed"])
    def test_redacted_policy(self):
        report={"calibration_research":{"frozen_policy":{"weight":.25,"train_cutoff":NOW,
                    "sha256":"test","training_event_ids":["private"]}}}
        result=public_summary(report)["calibration_research"]
        self.assertNotIn("frozen_policy",result)
        self.assertTrue(result["policy_summary"]["redacted_not_replayable"])
        self.assertNotIn('"private"',json.dumps(result))
