"""Local Git fixtures; no real writes or witness approvals."""
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import tempfile
import unittest
from ops.german_publication_monitor import inspect, REPO, WORKFLOW, POINTER
from ops.archive_witness_qualification import inspect as qualify, SIGNER_PATH


class P0Stage8Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git("init")
        self.git("config","user.name","fixture")
        self.git("config","user.email","fixture@example.invalid")
        self.now = datetime(2026,11,24,12,45,tzinfo=timezone.utc)
        self.runmeta = dict(id=45395491049,repository={"full_name":REPO},head_branch="main",
                            path=WORKFLOW,event="schedule",status="completed",conclusion="success",
                            created_at="2026-11-24T12:38:38Z",updated_at="2026-11-24T12:39:27Z")
        self.oldrun = dict(self.runmeta,id=45311544639,created_at="2026-11-24T02:19:41Z")
        self.doc = dict(schema="football-king-openligadb-hourly-v1",production_recommendations="DISABLED",
                        collected_utc="2026-11-24T12:39:12Z",status="RESEARCH_ONLY",matches=[],
                        league_coverage=[dict(league=l,status="AVAILABLE",production_recommendations="DISABLED")
                                         for l in ("bundesliga","bundesliga2","germany_liga3")])
        self.path = self.root / POINTER
        self.hist = self.root / "sources/live_germany/history/2026/11/24/12-45395491049.json.gz"
        self.path.parent.mkdir(parents=True)
        self.hist.parent.mkdir(parents=True)
        self.write()
        self.sha = self.commit()

    def git(self,*args):
        return subprocess.check_output(["git","-C",str(self.root),*args],stderr=subprocess.DEVNULL).decode().strip()

    def write(self):
        raw = json.dumps(self.doc).encode()
        self.path.write_bytes(raw)
        self.hist.write_bytes(gzip.compress(raw,mtime=0))

    def commit(self):
        self.git("add",".")
        self.git("commit","-m","fixture")
        return self.git("rev-parse","HEAD")

    def test_correlated_recovery_does_not_prove_cadence(self):
        r = inspect(self.root,self.sha,self.runmeta,self.now,self.oldrun)
        self.assertTrue(r["publication_correlated"])
        self.assertEqual(r["status"],"HOLD_FRESH_RESEARCH_PUBLICATION_CORRELATED")
        self.assertTrue(r["schedule_gap_exceeds_two_hours"])
        self.assertFalse(r["scheduled_cadence_restored"])

    def test_fresh_pointer_with_wrong_archive_rejected(self):
        self.hist.write_bytes(gzip.compress(b"wrong",mtime=0))
        self.assertEqual(inspect(self.root,self.commit(),self.runmeta,self.now)["status"],
                         "HOLD_FRESH_POINTER_NOT_RUN_CORRELATED")

    def test_fresh_partial_coverage_stays_hold(self):
        self.doc["league_coverage"][0]["status"]="NETWORK_ERROR"
        self.write()
        self.assertEqual(inspect(self.root,self.commit(),self.runmeta,self.now)["status"],
                         "HOLD_PARTIAL_PROVIDER_COVERAGE")

    def test_forged_repo_and_future_clock_rejected(self):
        bad = dict(self.runmeta,repository={"full_name":"different/repo"})
        with self.assertRaises(ValueError):
            inspect(self.root,self.sha,bad,self.now)
        with self.assertRaises(ValueError):
            inspect(self.root,self.sha,self.runmeta,datetime(2026,11,24,12,0,tzinfo=timezone.utc))

    def test_stale_never_falls_back(self):
        r = inspect(self.root,self.sha,self.runmeta,datetime(2026,11,24,17,tzinfo=timezone.utc))
        self.assertFalse(r["fallback_allowed"])
        self.assertEqual(r["status"],"HOLD_NO_RECENT_RUN_IN_OBSERVED_INVENTORY")

    def test_signer_existence_does_not_qualify(self):
        self.assertFalse(qualify(self.root,self.sha)["signer_workflow_present"])
        p = self.root / SIGNER_PATH
        p.parent.mkdir(parents=True)
        p.write_text("synthetic")
        r = qualify(self.root,self.commit())
        self.assertTrue(r["signer_workflow_present"])
        self.assertFalse(r["hosted_archive_write_authorized"])
        self.assertFalse(r["tsa_ca_independently_pinned"])


if __name__ == "__main__":
    unittest.main()
