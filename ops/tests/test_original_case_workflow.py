"""Execute the real workflow script and CLIs; gh responses are MOCKS, not proof."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
RUN = '39531309964'
SOURCE = '99a855861d5836a85097de3271905412a632f636'
CASE = '32760f90f88632237a2184f309f033d1d382d992dcf62cc53c53e9a85134266f'
PAIRED = '666628a233176eaf22e79c69ee847793127fcd4b924ca0f4e40b2c6306409830'
WORKFLOWS = ('four-model-shadow-daily.yml', 'four-model-shadow-ci.yml')
FLAGS = ('independently_verified', 'eligible_for_model_scoring',
         'eligible_for_betting_promotion', 'raw_source_authenticated',
         'raw_capture_time_authenticated', 'original_endpoint_verified',
         'source_freshness_verified', 'forecast_team_ids_verified',
         'actual_kickoff_independently_authenticated',
         'regulation_90_minute_ft_authenticated', 'outcomes_independently_authenticated')


def review_script(filename):
    text = (ROOT/'.github/workflows'/filename).read_text()
    marker = '  original-case-review:\n'
    if marker not in text:
        raise AssertionError('No independent original-case review job; only latest is reviewed')
    job = text.split(marker, 1)[1]
    marker = '      - name: Reverify original admission case using existing raw bytes\n'
    if marker not in job:
        raise AssertionError('No executable original-case review step')
    step = job.split(marker, 1)[1].split('\n      - ', 1)[0]
    script = step.split('        run: |\n', 1)[1]
    return textwrap.dedent(script)


class OriginalCaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'ops').symlink_to(ROOT/'ops', target_is_directory=True)
        self.runtemp = self.root/'runner-temp'
        self.runtemp.mkdir()
        self.rawdir = self.runtemp/'original-case-input'/'raw_sources'
        self.rawdir.mkdir(parents=True)
        self.original = self.root/'forecast_provenance/2026/10/21/39531309964-1'
        self.original.mkdir(parents=True)
        archive = ROOT/'forecast_provenance/2026/10/21/39531309964-1'
        for name in ('shadow.json', 'paired.json', 'slate.json', 'research.sigstore.json'):
            shutil.copyfile(archive/(name+'.gz'), self.original/(name+'.gz'))
        # The app never reads saved verification files. Only the fake gh below
        # emits this fixture, to test actual subprocess/API/verification wiring.
        verification = json.loads(gzip.decompress((archive/'paired.verification.json.gz').read_bytes()))
        self.config = self.root/'fake-gh-config.json'
        self.log = self.root/'fake-gh-invocations.jsonl'
        self.control = {'verification': verification, 'metadata': {
            'id': int(RUN), 'run_attempt': 1, 'head_sha': SOURCE,
            'head_branch': 'main', 'path': '.github/workflows/football-king-iphone.yml',
            'status': 'completed', 'conclusion': 'success',
            'repository': {'id': 1411226578, 'full_name': 'CHANCHUNWA1989/football-king-report'},
            'head_repository': {'id': 1411226578, 'full_name': 'CHANCHUNWA1989/football-king-report'}}}
        self.bin = self.root/'bin'
        self.bin.mkdir()
        gh = self.bin/'gh'
        gh.write_text('#!'+sys.executable+'\n'+textwrap.dedent('''
            import json,os,sys
            from pathlib import Path
            args=sys.argv[1:]
            with Path(os.environ['FAKE_GH_LOG']).open('a') as stream:
                stream.write(json.dumps(args)+'\\n')
            config=json.loads(Path(os.environ['FAKE_GH_CONTROL']).read_text())
            if args[0]=='api':
                if config.get('api_failure'): sys.exit(1)
                print(json.dumps(config['metadata']))
            elif args[:2]==['attestation','verify']:
                if config.get('verify_failure')==Path(args[2]).name: sys.exit(1)
                print(json.dumps(config['verification']))
            else:
                sys.exit('UNEXPECTED_GH_COMMAND')
        '''))
        gh.chmod(0o755)
        self.raw = [{'matchID': 83212, 'matchDateTimeUTC': '2026-10-23T18:30:00Z',
                     'matchIsFinished': True,
                     'team1': {'teamId': 16, 'teamName': 'VfB Stuttgart'},
                     'team2': {'teamId': 87, 'teamName': 'Borussia Mönchengladbach'},
                     'matchResults': [{'resultTypeID': 2, 'resultTypeKind': 'After90Minutes',
                                       'pointsTeam1': 2, 'pointsTeam2': 3}]}]
        self.write_raw()
        (self.root/'latest-report.json').write_bytes(b'LATEST_OUTPUT_MUST_NOT_CHANGE')

    def write_raw(self):
        body = json.dumps(self.raw).encode()
        (self.rawdir/'openligadb.json').write_bytes(body)
        self.manifest = {'schema': 'football-king-raw-ft-source-candidates-v1',
                         'status': 'HOLD', 'production_recommendations': 'DISABLED',
                         'independently_verified': False, 'season_start': 2026,
                         'captured_utc': '2026-10-24T00:45:00.932915+00:00',
                         'sources': [{'provider': 'OpenLigaDB', 'status': 'FETCHED_UNVERIFIED',
                                      'source_url': 'https://api.openligadb.de/getmatchdata/bl1/2026',
                                      'raw_file': 'openligadb.json', 'bytes': len(body),
                                      'raw_sha256': hashlib.sha256(body).hexdigest()}]}
        (self.rawdir/'manifest.json').write_text(json.dumps(self.manifest))

    def run_step(self, workflow=WORKFLOWS[0]):
        shutil.rmtree(self.runtemp/'original-case-forecast-proof', ignore_errors=True)
        shutil.rmtree(self.root/'original_case_review', ignore_errors=True)
        self.log.write_text('')
        self.config.write_text(json.dumps(self.control))
        workflow_text = (ROOT/'.github/workflows'/workflow).read_text()
        job = workflow_text.split('  original-case-review:\n', 1)[1]
        match = re.search(r'^          ORIGINAL_RAW_SUBDIR: ([a-z_]+)$', job, re.M)
        self.assertIsNotNone(match, 'The actual workflow must provide its raw subdirectory')
        subdir = match.group(1)
        artifact_raw = self.runtemp/'original-case-input'/subdir
        if artifact_raw != self.rawdir:
            shutil.copytree(self.rawdir, artifact_raw, dirs_exist_ok=True)
        env = dict(os.environ, RUNNER_TEMP=str(self.runtemp),
                   PATH=str(self.bin)+os.pathsep+os.environ.get('PATH', ''),
                   ORIGINAL_RAW_SUBDIR=subdir, FAKE_GH_CONTROL=str(self.config),
                   FAKE_GH_LOG=str(self.log), PYTHONDONTWRITEBYTECODE='1')
        return subprocess.run(['bash', '-euo', 'pipefail', '-c', review_script(workflow)],
                              cwd=self.root, env=env, capture_output=True, timeout=20)

    def invocations(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def report(self, name):
        return json.loads((self.root/'original_case_review'/name).read_text())

    def test_review_failure_cannot_block_existing_capture_archive_jobs(self):
        for workflow, parent in zip(WORKFLOWS, ('shadow-daily', 'live-source-smoke')):
            text = (ROOT/'.github/workflows'/workflow).read_text()
            jobs = dict(re.findall(r'^  ([a-z][a-z0-9_-]*):\n(.*?)(?=^  [a-z]|\Z)',
                                   text, re.M | re.S))
            self.assertIn('original-case-review', jobs)
            review = jobs['original-case-review']
            self.assertIn('    needs: '+parent+'\n', review)
            self.assertNotIn('continue-on-error', review)
            self.assertIn('        if: success()\n', review)
            for name, job in jobs.items():
                if name != 'original-case-review':
                    needs = re.findall(r'^    needs:.*$', job, re.M)
                    self.assertFalse(any('original-case-review' in line for line in needs), name)
            self.assertNotIn('shadow_raw_source_collector.py', review_script(workflow))

    def test_each_workflow_executes_real_preparer_and_linker_for_original_case(self):
        newest = self.root/'forecast_provenance/2026/10/24/40046584265-1'
        newest.mkdir(parents=True)
        newest.joinpath('paired.json.gz').write_bytes(gzip.compress(b'{"comparisons":[]}'))
        original_bytes = {p.name: p.read_bytes() for p in self.original.iterdir()}
        raw_before = (self.rawdir/'openligadb.json').read_bytes()
        for workflow in WORKFLOWS:
            with self.subTest(workflow=workflow):
                result = self.run_step(workflow)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                selection = self.report('selection.json')
                summary = self.report('summary.json')
                report = self.report('raw_fixed_identity_linkage.json')
                self.assertEqual(selection['run_id'], RUN)
                self.assertEqual(selection['paired_sha256'], PAIRED)
                self.assertEqual(summary['case_id'], CASE)
                self.assertIs(summary['case_linked'], True)
                self.assertIs(summary['ft_candidate'], True)
                self.assertEqual(summary['case']['score_ft_candidate'], [2, 3])
                self.assertEqual(summary['claimed_raw_capture_utc'], self.manifest['captured_utc'])
                self.assertEqual(report['raw_sha256'], hashlib.sha256(raw_before).hexdigest())
                self.assertEqual([call[:2] for call in self.invocations()],
                                 [['api', 'repos/CHANCHUNWA1989/football-king-report/actions/runs/'+RUN+'/attempts/1']]
                                 + [['attestation', 'verify']] * 3)
                for item in [report, summary]+report['cases']:
                    self.assertEqual(item['status'], 'HOLD')
                    self.assertEqual(item['production_recommendations'], 'DISABLED')
                    for flag in FLAGS:
                        self.assertIs(item[flag], False, flag)
        self.assertEqual(raw_before, (self.rawdir/'openligadb.json').read_bytes())
        self.assertEqual(original_bytes, {p.name: p.read_bytes() for p in self.original.iterdir()})
        self.assertEqual((self.root/'latest-report.json').read_bytes(), b'LATEST_OUTPUT_MUST_NOT_CHANGE')

    def test_missing_original_never_substitutes_a_newer_batch(self):
        self.original.rename(self.original.with_name('40046584265-1'))
        result = self.run_step()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.invocations(), [])
        self.assertFalse((self.root/'original_case_review/summary.json').exists())

    def test_changed_original_bytes_rejected_before_any_metadata_or_signature_call(self):
        p = self.original/'paired.json.gz'
        p.write_bytes(gzip.compress(gzip.decompress(p.read_bytes())+b'\n'))
        result = self.run_step()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.invocations(), [])

    def test_fresh_api_failure_never_uses_saved_success(self):
        self.control['api_failure'] = True
        (self.original/'paired.verification.json.gz').write_bytes(gzip.compress(b'{"verified":true}'))
        result = self.run_step()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.invocations()), 1)
        self.assertFalse((self.root/'original_case_review/summary.json').exists())

    def test_each_subject_verification_failure_stops_original_review(self):
        for index, name in enumerate(('shadow.json', 'paired.json', 'slate.json')):
            with self.subTest(subject=name):
                self.control['verify_failure'] = name
                result = self.run_step()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(self.invocations()), index+2)
                report = self.report('raw_fixed_identity_linkage.json')
                self.assertIs(report['audit_completed'], False)
                self.assertEqual(report['linked_count'], 0)
                self.assertFalse((self.root/'original_case_review/summary.json').exists())

    def test_wrong_source_metadata_is_rejected_before_signature_replay(self):
        self.control['metadata']['head_sha'] = '0'*40
        result = self.run_step()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.invocations()), 1)
        self.assertFalse((self.root/'original_case_review/summary.json').exists())

    def test_corrupt_raw_hash_cannot_become_an_original_case_observation(self):
        (self.rawdir/'openligadb.json').write_bytes(b'[]')
        result = self.run_step()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.invocations()), 4)
        self.assertFalse((self.root/'original_case_review/summary.json').exists())

    def test_absent_or_conflicting_raw_case_remains_unlinked_hold(self):
        for change in ('absent', 'conflict'):
            with self.subTest(change=change):
                self.raw[0]['matchID'] = 83213 if change=='absent' else 83212
                self.raw[0]['team1']['teamName'] = 'Wrong team' if change=='conflict' else 'VfB Stuttgart'
                self.write_raw()
                result = self.run_step()
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                summary = self.report('summary.json')
                self.assertIs(summary['case_linked'], False)
                self.assertIs(summary['ft_candidate'], False)
                self.assertEqual(summary['status'], 'HOLD')


if __name__ == '__main__':
    unittest.main()
