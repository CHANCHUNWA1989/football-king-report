"""Real pack/replay boundaries; mocked CLI stdout is NOT cryptographic proof."""
import copy
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.tests import test_raw_openligadb_identity_linkage as linkage_tests
from ops.tests import test_openliga_capture_provenance as capture_tests
from ops.tests import test_openliga_capture_pack as pack_tests
from ops import openliga_capture_pack

NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)


class ControlledCaseIntakeTests(unittest.TestCase):
    def setUp(self):
        self.link = linkage_tests.RawOpenLigaDBIdentityLinkageTests()
        self.link.setUp()
        self.addCleanup(self.link.doCleanups)
        self.link.finished()
        self.link.fixture.pair['case_id'] = 'a' * 64
        self.link.fixture.write_inputs()
        self.capture = capture_tests.OpenLigaCaptureProvenanceTests()
        self.capture.setUp()
        self.addCleanup(self.capture.doCleanups)
        self.root = self.link.root
        self.rawdir = self.root / 'controlled-raw'
        self.manifest = pack_tests.fixture(self.rawdir)
        self.raw = copy.deepcopy(self.link.raw)
        self.raw[0].update(leagueShortcut='bl1', leagueSeason=2026)
        self.raw[0]['matchResults'][0]['resultTypeKind'] = 'After90Minutes'
        self.options = {
            **{'forecast_' + key: value for key, value in self.link.fixture.options.items() if key != 'now'},
            **{'capture_' + key: value for key, value in self.capture.options.items() if key != 'now'},
            'case_id': 'a' * 64, 'paired_sha256': hashlib.sha256(
                (self.link.proof / 'paired.json').read_bytes()).hexdigest(), 'now': NOW}
        self.repack()

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('ops.controlled_case_intake'),
                             'No intake binds controlled capture bytes to the original forecast')
        return importlib.import_module('ops.controlled_case_intake')

    def repack(self):
        raw = json.dumps(self.raw).encode()
        (self.rawdir / 'openligadb.json').write_bytes(raw)
        self.manifest['sources'][0].update(bytes=len(raw), raw_sha256=hashlib.sha256(raw).hexdigest())
        (self.rawdir / 'manifest.json').write_bytes(pack_tests.encode(self.manifest))
        target = self.capture.proof / 'openliga-capture.tar'
        target.unlink(missing_ok=True)
        openliga_capture_pack.prepare(self.rawdir, target, now=NOW)
        self.capture.raw = target.read_bytes()

    def cli(self, argv, **kwargs):
        if Path(argv[3]).name == 'openliga-capture.tar':
            output = self.capture.stdout()
            output[0]['verificationResult']['verifiedTimestamps'][0]['timestamp'] = '2026-10-20T11:59:00Z'
        else:
            output = self.link.fixture.stdout()
        return subprocess.CompletedProcess(argv, 0, json.dumps(output).encode(), b'')

    def run_intake(self, **overrides):
        with patch('subprocess.run', side_effect=self.cli) as cli:
            report = self.module().audit_case(self.link.proof, self.capture.proof,
                                              **dict(self.options, **overrides))
        return report, cli

    def assert_held(self, report):
        for item in [report] + ([report['case']] if report.get('case') else []):
            self.link.assert_held(dict(item, cases=[], sealed_exclusions=[]))
        self.assertEqual(report['certified_case_count'], 0)

    def test_exact_controlled_bytes_and_original_forecast_link_with_four_fresh_cli(self):
        before = {p: p.read_bytes() for folder in (self.link.proof, self.capture.proof)
                  for p in folder.iterdir()}
        report, cli = self.run_intake()
        self.assertTrue(report['intake_completed'])
        self.assertTrue(report['controlled_capture_to_forecast_link_verified'])
        self.assertEqual(cli.call_count, 4)
        self.assertEqual(report['case']['score_ft_candidate'], [2, 1])
        self.assertEqual(report['raw_sha256'], hashlib.sha256(
            (self.rawdir / 'openligadb.json').read_bytes()).hexdigest())
        self.assertEqual(report['capture_reference']['raw_sha256'], report['raw_sha256'])
        self.assertEqual(report['source_policy']['sha256'],
                         '33abd884142cc8000844d82cf9886446e4fe27a823f95577d06e4f8d232c6463')
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        self.assert_held(report)

    def test_failed_fresh_capture_or_forecast_cli_cannot_use_saved_success(self):
        for subject in ('openliga-capture.tar', 'shadow.json', 'paired.json', 'slate.json'):
            with self.subTest(subject=subject):
                def run(argv, **kwargs):
                    return (subprocess.CompletedProcess(argv, 1, b'[]', b'PRIVATE')
                            if Path(argv[3]).name == subject else self.cli(argv, **kwargs))
                with patch('subprocess.run', side_effect=run):
                    report = self.module().audit_case(self.link.proof, self.capture.proof, **self.options)
                self.assertFalse(report['intake_completed'])
                self.assertFalse(report['controlled_capture_to_forecast_link_verified'])
                self.assertNotIn('PRIVATE', json.dumps(report))
                self.assert_held(report)

    def test_wrong_case_digest_and_context_never_fall_back(self):
        for options in ({'case_id': 'b' * 64}, {'paired_sha256': '0' * 64},
                        {'capture_source_sha': '0' * 40}, {'forecast_source_sha': '0' * 40},
                        {'capture_run_id': '99'}, {'forecast_run_id': '99'}):
            with self.subTest(options=options):
                report, _ = self.run_intake(**options)
                self.assertFalse(report['intake_completed'])
                self.assertFalse(report['controlled_capture_to_forecast_link_verified'])
                self.assert_held(report)

    def test_wrong_league_season_period_or_order_is_rejected(self):
        original = copy.deepcopy(self.raw)
        changes = ({'leagueShortcut': 'bl2'}, {'leagueSeason': 2025}, {'leagueSeason': True},
                   {'leagueSeason': '2026'}, {'leagueSeason': 2026.0},
                   {'period': 'AfterExtraTime'}, {'period': None}, {'swap': True})
        for change in changes:
            with self.subTest(change=change):
                self.raw = copy.deepcopy(original)
                self.raw[0].update({k: v for k, v in change.items() if k not in ('period', 'swap')})
                if 'period' in change:
                    self.raw[0]['matchResults'][0]['resultTypeKind'] = change['period']
                if change.get('swap'):
                    self.raw[0]['team1'], self.raw[0]['team2'] = self.raw[0]['team2'], self.raw[0]['team1']
                self.repack()
                report, _ = self.run_intake()
                self.assertFalse(report['intake_completed'])
                self.assert_held(report)

    def test_capture_tar_replacement_after_verification_is_rejected(self):
        module = self.module()
        real = module.capture_provenance.audit
        def replace(*args, **kwargs):
            report = real(*args, **kwargs)
            path = self.capture.proof / 'openliga-capture.tar'
            path.write_bytes(path.read_bytes() + b'tamper')
            return report
        with patch('subprocess.run', side_effect=self.cli), patch.object(
                module.capture_provenance, 'audit', side_effect=replace):
            report = module.audit_case(self.link.proof, self.capture.proof, **self.options)
        self.assertFalse(report['intake_completed'])
        self.assert_held(report)

    def test_valid_unfinished_capture_links_without_a_final_candidate(self):
        self.raw[0].update(matchIsFinished=False, matchResults=[])
        self.repack()
        report, _ = self.run_intake()
        self.assertTrue(report['intake_completed'])
        self.assertFalse(report['case']['ft_candidate'])
        self.assertIn('NO_REGULATION_FINAL_CANDIDATE', report['blockers'])
        self.assert_held(report)

    def test_duplicate_final_and_forecast_outside_policy_are_rejected(self):
        final = copy.deepcopy(self.raw[0]['matchResults'][0])
        self.raw[0]['matchResults'].append(final)
        self.repack()
        report, _ = self.run_intake()
        self.assertFalse(report['intake_completed'])
        self.raw[0]['matchResults'].pop()
        self.repack()
        self.link.fixture.pair['league'] = 'epl'
        self.link.fixture.forecast['league'] = 'epl'
        self.link.fixture.write_inputs()
        digest = hashlib.sha256((self.link.proof / 'paired.json').read_bytes()).hexdigest()
        report, _ = self.run_intake(paired_sha256=digest)
        self.assertFalse(report['intake_completed'])
        self.assert_held(report)

    def test_private_handoff_cannot_be_replaced_with_other_raw_bytes(self):
        module = self.module()
        real = module.linkage.audit_linkage
        def replace(raw_dir, *args, **kwargs):
            path = raw_dir / 'openligadb.json'
            changed = path.read_bytes().replace(b'"pointsTeam1": 2', b'"pointsTeam1": 4')
            path.write_bytes(changed)
            manifest = json.loads((raw_dir / 'manifest.json').read_bytes())
            manifest['sources'][0].update(bytes=len(changed), raw_sha256=hashlib.sha256(changed).hexdigest())
            (raw_dir / 'manifest.json').write_text(json.dumps(manifest))
            return real(raw_dir, *args, **kwargs)
        with patch('subprocess.run', side_effect=self.cli), patch.object(
                module.linkage, 'audit_linkage', side_effect=replace):
            report = module.audit_case(self.link.proof, self.capture.proof, **self.options)
        self.assertFalse(report['intake_completed'])
        self.assertEqual(report['reason'], 'LINKAGE_BYTES_DIFFER_FROM_VERIFIED_CAPTURE')
        self.assert_held(report)

    def test_cli_cannot_overwrite_existing_files_or_proof(self):
        module = self.module()
        output = self.root / 'existing.json'
        output.write_bytes(b'ORIGINAL_MUST_NOT_CHANGE')
        args = ['--forecast-proof', str(self.link.proof), '--capture-proof', str(self.capture.proof)]
        for key, value in self.options.items():
            if key != 'now': args += ['--' + key.replace('_', '-'), str(value)]
        for path in (output, self.link.proof / 'new.json', self.capture.proof / 'new.json'):
            with self.subTest(path=path), self.assertRaises(SystemExit):
                module.main(args + ['--output', str(path)])
        self.assertEqual(output.read_bytes(), b'ORIGINAL_MUST_NOT_CHANGE')


class ControlledCaseWorkflowTests(unittest.TestCase):
    def test_actual_workflow_context_variables_and_isolated_dependencies(self):
        root = Path(__file__).resolve().parents[2]
        for name, parent in (('four-model-shadow-daily.yml', 'attest_openliga_capture'),
                             ('four-model-shadow-ci.yml', 'audit-tests')):
            with self.subTest(workflow=name):
                text = (root / '.github/workflows' / name).read_text()
                section = re.search(r'^  controlled-case-intake:\n(.*?)(?=^  [a-z]|\Z)',
                                    text, re.M | re.S)
                self.assertIsNotNone(section)
                job = section.group(1)
                env = dict(re.findall(r'^      ([A-Z_]+): (.+)$', job, re.M))
                for key in ('CAPTURE_SOURCE_SHA', 'CAPTURE_WORKFLOW_SHA', 'CAPTURE_RUN_ID',
                            'CAPTURE_ATTEMPT', 'CAPTURE_RUN_IS_CURRENT', 'PYTHONPATH'):
                    self.assertIn(key, env)
                self.assertIn('    needs: ' + parent + '\n', job)
                self.assertEqual(env['PYTHONPATH'], 'ops')
                if parent == 'attest_openliga_capture':
                    self.assertEqual(env['CAPTURE_SOURCE_SHA'], '${{ github.sha }}')
                    self.assertEqual(env['CAPTURE_WORKFLOW_SHA'], '${{ github.workflow_sha }}')
                    self.assertIn('name: openliga-capture-signed-proof', job)
                else:
                    self.assertEqual(env['CAPTURE_SOURCE_SHA'], "'79cbffadf8155344172a4e92054a3abfda71ab4e'")
                    self.assertEqual(env['CAPTURE_WORKFLOW_SHA'], env['CAPTURE_SOURCE_SHA'])
                    self.assertEqual(env['CAPTURE_RUN_ID'], "'40053042424'")
                for dependency in re.findall(r'^    needs: (.+)$', text, re.M):
                    self.assertNotIn('controlled-case-intake', dependency)
