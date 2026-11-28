import unittest
from copy import deepcopy
from unittest.mock import patch
from ops.tests.test_research_live_pipeline_v10 import case
from ops.tests.test_research_unified_live_v2 import NOW
from ops.research_live_pipeline_v10 import capture,replay,review
from ops.research_live_release_binding import source_manifest,FILES
from ops.research_unified_live_v2 import digest

def bound_case():
    c=case(True)
    c["receipt"]=capture(c["raw_captures"],c["policy"],event_id="synthetic",as_of=NOW,
                         model_release="test",probability_only=True,source_bound=True)
    return c

def strict(cases):
    return review(cases,model_release="test",train_start="2026-11-27T00:00:00Z",
                  train_cutoff="2026-11-28T00:00:00Z",test_end="2026-11-29T00:00:00Z",
                  as_of="2026-11-30T00:00:00Z",require_source_binding=True)

class SourceBindingTests(unittest.TestCase):
    def test_manifest(self):
        m=source_manifest()
        self.assertEqual(set(m["files"]),set(FILES))
        self.assertTrue(all(len(x)==64 for x in m["files"].values()))
    def test_bound(self):
        c=bound_case();r=strict([c])
        self.assertTrue(r["pipeline_replay_passed"])
        self.assertEqual(r["source_bound_candidates"],1)
        self.assertEqual(r["authenticated_samples"],0)
    def test_legacy_rejected_in_strict_mode(self):
        self.assertFalse(strict([case()])["pipeline_replay_passed"])
    def test_changed_source(self):
        c=bound_case();m=source_manifest()
        m["files"][FILES[0]]="0"*64
        with patch("ops.research_live_pipeline_v10.source_manifest",return_value=m):
            self.assertFalse(strict([c])["pipeline_replay_passed"])
    def test_tampered_rehash(self):
        c=bound_case()
        c["receipt"]["source_manifest"]["files"][FILES[0]]="0"*64
        c["receipt"]["sha256"]=digest({k:v for k,v in c["receipt"].items() if k!="sha256"})
        with self.assertRaises(ValueError):replay(c["receipt"],c["raw_captures"],c["policy"])
