import json
import tempfile
import unittest
from pathlib import Path
from ops.research_archive_proof_ci_report_v1 import build_report,main

class ArchiveProofCiReportTests(unittest.TestCase):
    def setUp(self):
        batch={"candidate_fixtures":75,"fresh_verified_linked_fixtures":74,
               "authenticated_samples":0,"actual_kickoff_authenticated":False,
               "batch_passed":False,"ledger_sha256":"a"*64}
        overlap={"authenticated_samples":0,"actual_kickoff_authenticated":False,
                 "upstream_independence_proven":False,"ledger_sha256":"a"*64,
                 "witness_and_two_publisher_exact_score":20}
        self.log=("V22_BATCH_VERIFICATION_SUMMARY "+json.dumps(batch)+"\n"
                  "V23_EVIDENCE_OVERLAP_SUMMARY "+json.dumps(overlap)+"\n")
    def test_report_never_promotes(self):
        report=build_report(self.log)
        self.assertFalse(report["ci_evidence_gate_passed"])
        self.assertEqual(report["status"],"HOLD")
        self.assertIsNone(report["audit"]["missing_fixture_ids"])
    def test_cli_writes_json(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"job.log"
            target=Path(d)/"report.json"
            source.write_text(self.log,encoding="utf-8")
            self.assertEqual(main(["--log",str(source),"--output",str(target)]),0)
            self.assertEqual(json.loads(target.read_text())["status"],"HOLD")
    def test_cli_rejects_missing_summary(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"job.log"
            target=Path(d)/"report.json"
            source.write_text("incomplete",encoding="utf-8")
            self.assertEqual(main(["--log",str(source),"--output",str(target)]),2)
            self.assertFalse(target.exists())
    def test_cli_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"job.log"
            target=Path(d)/"report.json"
            source.write_text(self.log,encoding="utf-8")
            target.write_text("existing",encoding="utf-8")
            self.assertEqual(main(["--log",str(source),"--output",str(target)]),2)
            self.assertEqual(target.read_text(),"existing")
if __name__=="__main__":unittest.main()
