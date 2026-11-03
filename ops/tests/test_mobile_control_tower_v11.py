"""Mobile V11: a green badge requires every mandatory exact-head CI check.

This is an offline Node evaluation of the actual browser function extracted
from the HTML. No GitHub API, deployment or production capabilities used.
"""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

PAGE = Path(__file__).resolve().parents[2] / "docs/control-tower-mobile/index.html"


class MobileV11RequiredCIGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = PAGE.read_text(encoding="utf-8")

    def test_mandatory_ci_names_and_checks_only_come_from_github_actions(self):
        html = self.html
        for token in (
                "const REQUIRED_CI_CHECKS=Object.freeze(",
                "'regression':2", "'stress':1",
                "'safety (3.11)':1", "'safety (3.12)':1",
                "'ledger-tests':1", "'validate':1",
                "c.app?.slug!=='github-actions'",
                "c.status!=='completed'", "c.conclusion!=='success'",
                "c.head_sha!==sha",
                "checks.total_count!==checks.check_runs.length",
                "checks.total_count>=100",
                "checksReadyForCurrentHead(check.value,prTarget?.head)",
                "status:'UNVERIFIED'", "production_recommendations:'DISABLED'",
                "S.site={status:'HOLD'",
        ):
            with self.subTest(token=token):
                self.assertIn(token, html)

    @unittest.skipUnless(shutil.which("node"), "Node.js is unavailable")
    def test_real_browser_check_function_rejects_false_green(self):
        html = self.html
        gate = ("const REQUIRED_CI_CHECKS=" + html.split(
            "const REQUIRED_CI_CHECKS=", 1)[1].split(
                "const SNAPSHOT_AT=", 1)[0])
        javascript = gate + r"""
const sha='a'.repeat(40);
const names=['regression','regression','stress','safety (3.11)',
             'safety (3.12)','ledger-tests','validate'];
const make=(name)=>({name,head_sha:sha,app:{slug:'github-actions'},
                     status:'completed',conclusion:'success'});
const valid=names.map(make);
const payload=(rows,override={})=>({total_count:rows.length,check_runs:rows,...override});
const modify=(index,changes)=>valid.map((row,i)=>i===index?{...row,...changes}:row);
const results={
 success:checksReadyForCurrentHead(payload(valid),sha),
 missing_ledger:checksReadyForCurrentHead(payload(modify(5,{name:'regression'})),sha),
 missing_one_regression:checksReadyForCurrentHead(payload(modify(1,{name:'other'})),sha),
 wrong_sha:checksReadyForCurrentHead(payload(modify(2,{head_sha:'b'.repeat(40)})),sha),
 forged_app:checksReadyForCurrentHead(payload(modify(4,{app:{slug:'third-party'}})),sha),
 pending_check:checksReadyForCurrentHead(payload(modify(6,{status:'in_progress'})),sha),
 failed_check:checksReadyForCurrentHead(payload(modify(1,{conclusion:'failure'})),sha),
 skipped_check:checksReadyForCurrentHead(payload(modify(6,{conclusion:'skipped'})),sha),
 truncated_page:checksReadyForCurrentHead(payload(valid,{total_count:8}),sha),
 empty:checksReadyForCurrentHead(payload([]),sha),
 missing_sha:checksReadyForCurrentHead(payload(valid),''),
 malformed_count:checksReadyForCurrentHead(payload(valid,{total_count:'7'}),sha),
 unknown_failure:checksReadyForCurrentHead(payload([...valid,make('optional').name==='x'
 ? make('x'):{...make('optional'),conclusion:'failure'}]),sha),
 optional_success:checksReadyForCurrentHead(payload([...valid,make('optional')]),sha)
};
process.stdout.write(JSON.stringify(results));
"""
        result = subprocess.run(
            ["node", "-e", javascript],
            capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        observed = json.loads(result.stdout)
        self.assertTrue(observed.pop("success"))
        self.assertTrue(observed.pop("optional_success"))
        self.assertTrue(all(not outcome for outcome in observed.values()),
                        observed)

    def test_page_stays_research_only_and_not_deployed(self):
        self.assertIn("ai-control-tower-mobile-v11-snapshot.json", self.html)
        self.assertIn("release_authorized:false", self.html)
        self.assertIn("deploy_allowed:false", self.html)
        self.assertIn("live_execution_allowed:false", self.html)
        self.assertIn("verified_positive_ev:false", self.html)


if __name__ == "__main__":
    unittest.main()
