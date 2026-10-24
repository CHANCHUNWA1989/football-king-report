"""Proof-bound replay tests; mocked CLI stdout is NOT cryptographic proof."""
import copy
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from ops.tests import test_controlled_case_intake as intake_tests
from ops import model_ab, model_market_challenger


class ControlledCaseReplayTests(unittest.TestCase):
    def setUp(self):
        self.fixture = intake_tests.ControlledCaseIntakeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.pair = self.fixture.link.fixture.pair
        self.pair.update(
            ab=model_ab.candidate(self.pair['model']), ab_model=model_ab.MODEL,
            c=model_market_challenger.candidate(self.pair['model'], self.pair['market']),
            c_model=model_market_challenger.MODEL,
            c_uses_only_prior_de_vigged_market=True,
            c_research_only_not_calibrated_or_executable=True,
            result=None, historical_outcome=None)
        self.fixture.link.fixture.write_inputs()
        self.options = dict(self.fixture.options)
        self.refresh_pin()

    def refresh_pin(self):
        self.options['paired_sha256'] = hashlib.sha256(
            (self.fixture.link.proof / 'paired.json').read_bytes()).hexdigest()

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('ops.controlled_case_replay'),
                             'No fresh proof-bound four-way case scoring replay exists')
        return importlib.import_module('ops.controlled_case_replay')

    def run_replay(self, **overrides):
        with patch('subprocess.run', side_effect=self.fixture.cli) as cli:
            result = self.module().audit_replay(
                self.fixture.link.proof, self.fixture.capture.proof,
                **dict(self.options, **overrides))
        return result, cli

    def assert_held(self, report, completed=False):
        self.fixture.link.assert_held(dict(report, cases=[], sealed_exclusions=[]))
        self.assertIs(report['replay_completed'], completed)
        self.assertIs(report['candidate_score_replay_completed'], completed)
        self.assertEqual(report['certified_case_count'], 0)
        self.assertIs(report['candidate_only'], True)
        self.assertIs(report['derived_review_not_a_trust_input'], True)
        if not completed:
            self.assertIsNone(report['scoring'])
            self.assertIsNone(report['models'])
            self.assertIsNone(report['case'])

    def protected(self):
        return {p: p.read_bytes() for folder in (self.fixture.link.proof, self.fixture.capture.proof)
                for p in folder.iterdir()}

    def test_real_pack_bound_four_way_replay_uses_only_four_fresh_cli_and_preserves_files(self):
        before = self.protected()
        result, cli = self.run_replay()
        self.assert_held(result, True)
        self.assertEqual(cli.call_count, 4)
        self.assertTrue(result['intake']['intake_completed'])
        self.assertEqual(result['scoring']['score_ft_candidate'], [2, 1])
        self.assertEqual(result['scoring']['y'], 0)
        for label, key in (('A', 'model'), ('B', 'ab'), ('C', 'c'), ('market', 'market')):
            self.assertEqual(result['models'][label]['probabilities'], self.pair[key])
        self.assertEqual(result['models'], result['scoring']['models'])
        self.assertEqual(result['forecast_reference']['subject_sha256']['paired.json'],
                         self.options['paired_sha256'])
        self.assertEqual(result['capture_reference']['raw_sha256'], result['raw_sha256'])
        self.assertEqual(result['case']['case_id'], self.options['case_id'])
        self.assertEqual(result['blockers'], result['intake']['blockers'])
        self.assertIn('TRUSTED_RESULT_ADMISSION_NOT_IMPLEMENTED', result['blockers'])
        self.assertEqual(self.protected(), before)

    def test_each_failed_fresh_cli_cannot_reuse_saved_success(self):
        for name in ('openliga-capture.tar', 'shadow.json', 'paired.json', 'slate.json'):
            with self.subTest(name=name):
                def cli(argv, **kwargs):
                    if Path(argv[3]).name == name:
                        return subprocess.CompletedProcess(argv, 1, b'[]', b'PRIVATE_SECRET')
                    return self.fixture.cli(argv, **kwargs)
                with patch('subprocess.run', side_effect=cli):
                    result = self.module().audit_replay(self.fixture.link.proof,
                                                       self.fixture.capture.proof, **self.options)
                self.assert_held(result)
                self.assertNotIn('PRIVATE_SECRET', json.dumps(result))

    def test_exact_case_digest_run_and_source_pins_never_fall_back(self):
        for change in ({'case_id': 'b' * 64}, {'paired_sha256': '0' * 64},
                       {'capture_source_sha': '0' * 40}, {'forecast_source_sha': '0' * 40},
                       {'capture_run_id': '99'}, {'forecast_run_id': '99'}):
            with self.subTest(change=change):
                result, _ = self.run_replay(**change)
                self.assert_held(result)

    def test_future_proof_and_invalid_clock_are_rejected_without_freshness_claims(self):
        for clock in (datetime(2026, 10, 17, tzinfo=timezone.utc), datetime(2026, 10, 20), 'bad'):
            with self.subTest(clock=clock):
                result, _ = self.run_replay(now=clock)
                self.assert_held(result)

    def test_missing_each_original_proof_file_rejects(self):
        before = self.protected()
        for path, raw in before.items():
            with self.subTest(name=path.name):
                path.unlink()
                try:
                    result, _ = self.run_replay()
                    self.assert_held(result)
                finally:
                    path.write_bytes(raw)

    def test_unfinished_or_other_period_never_scores(self):
        original = copy.deepcopy(self.fixture.raw)
        for change in ('unfinished', 'extra-time', 'missing-period'):
            with self.subTest(change=change):
                self.fixture.raw = copy.deepcopy(original)
                if change == 'unfinished':
                    self.fixture.raw[0].update(matchIsFinished=False, matchResults=[])
                else:
                    self.fixture.raw[0]['matchResults'][0]['resultTypeKind'] = (
                        'AfterExtraTime' if change == 'extra-time' else None)
                self.fixture.repack()
                result, _ = self.run_replay()
                self.assert_held(result)

    def test_cannot_swap_raw_teams_or_duplicate_final(self):
        original = copy.deepcopy(self.fixture.raw)
        for change in ('swap', 'duplicate'):
            with self.subTest(change=change):
                self.fixture.raw = copy.deepcopy(original)
                if change == 'swap':
                    row = self.fixture.raw[0]
                    row['team1'], row['team2'] = row['team2'], row['team1']
                else:
                    self.fixture.raw[0]['matchResults'].append(
                        copy.deepcopy(self.fixture.raw[0]['matchResults'][0]))
                self.fixture.repack()
                result, _ = self.run_replay()
                self.assert_held(result)

    def test_each_proof_replaced_after_fresh_intake_is_rejected(self):
        module = self.module()
        before = self.protected()
        original = module.controlled_case_intake.audit_case
        for path, raw in before.items():
            with self.subTest(name=path.name):
                def replace(*args, **kwargs):
                    result = original(*args, **kwargs)
                    path.write_bytes(raw + b' ')
                    return result
                try:
                    with patch('subprocess.run', side_effect=self.fixture.cli), patch.object(
                            module.controlled_case_intake, 'audit_case', side_effect=replace):
                        result = module.audit_replay(self.fixture.link.proof,
                                                     self.fixture.capture.proof, **self.options)
                    self.assert_held(result)
                    self.assertEqual(result['reason'], 'PROOF_BYTES_CHANGED_DURING_CASE_REPLAY')
                finally:
                    path.write_bytes(raw)

    def test_proof_changed_during_scoring_cannot_leave_partial_scores(self):
        module = self.module()
        original = module.case_fourway_scoring.score_case
        path = self.fixture.link.proof / 'paired.json'
        before = path.read_bytes()
        def replace(*args, **kwargs):
            result = original(*args, **kwargs)
            path.write_bytes(before + b' ')
            return result
        try:
            with patch('subprocess.run', side_effect=self.fixture.cli), patch.object(
                    module.case_fourway_scoring, 'score_case', side_effect=replace):
                result = module.audit_replay(self.fixture.link.proof,
                                             self.fixture.capture.proof, **self.options)
            self.assert_held(result)
            self.assertEqual(result['reason'], 'PROOF_BYTES_CHANGED_DURING_CASE_REPLAY')
        finally:
            path.write_bytes(before)

    def test_fresh_intake_handoff_must_match_subject_context_and_raw_candidate(self):
        module = self.module()
        original = module.controlled_case_intake.audit_case
        for change in ('forecast-ref', 'capture-ref', 'paired-ref', 'raw-ref',
                       'manifest-ref', 'case-score', 'case-index'):
            with self.subTest(change=change):
                def corrupt(*args, **kwargs):
                    result = copy.deepcopy(original(*args, **kwargs))
                    if change == 'forecast-ref':
                        result['forecast_reference']['run_id'] = '99'
                    elif change == 'capture-ref':
                        result['capture_reference']['subject_sha256']['openliga-capture.tar'] = '0' * 64
                    elif change == 'paired-ref':
                        result['forecast_reference']['subject_sha256']['paired.json'] = '0' * 64
                    elif change == 'raw-ref':
                        result['capture_reference']['raw_sha256'] = '0' * 64
                    elif change == 'manifest-ref':
                        result['manifest_sha256'] = '0' * 64
                    elif change == 'case-score':
                        result['case']['score_ft_candidate'] = [9, 8]
                    else:
                        result['case']['pair_index'] = 99
                    return result
                with patch('subprocess.run', side_effect=self.fixture.cli), patch.object(
                        module.controlled_case_intake, 'audit_case', side_effect=corrupt):
                    result = module.audit_replay(self.fixture.link.proof,
                                                 self.fixture.capture.proof, **self.options)
                self.assert_held(result)

    def test_invalid_or_absent_sealed_challenger_is_not_reconstructed(self):
        for change in ('missing-b', 'wrong-c', 'unknown-model'):
            with self.subTest(change=change):
                original = copy.deepcopy(self.pair)
                try:
                    if change == 'missing-b':
                        self.pair.pop('ab')
                    elif change == 'wrong-c':
                        self.pair['c'] = [.1, .2, .7]
                    else:
                        self.pair['c_model'] = 'invented-v1'
                    self.fixture.link.fixture.write_inputs()
                    self.refresh_pin()
                    result, _ = self.run_replay()
                    self.assert_held(result)
                finally:
                    self.pair.clear()
                    self.pair.update(original)
                    self.fixture.link.fixture.write_inputs()
                    self.refresh_pin()

    def test_cli_new_output_and_intake_diagnostic_but_no_saved_report_input(self):
        module = self.module()
        output = self.fixture.root / 'replay.json'
        args = ['--forecast-proof', str(self.fixture.link.proof),
                '--capture-proof', str(self.fixture.capture.proof)]
        for key, value in self.options.items():
            if key != 'now': args += ['--' + key.replace('_', '-'), str(value)]
        with patch('subprocess.run', side_effect=self.fixture.cli):
            self.assertEqual(module.main(args + ['--output', str(output)]), 0)
        report = json.loads(output.read_bytes())
        self.assert_held(report, True)
        before = output.read_bytes()
        for path in (output, self.fixture.link.proof / 'new.json',
                     self.fixture.capture.proof / 'new.json'):
            with self.subTest(path=path), self.assertRaises(SystemExit):
                module.main(args + ['--output', str(path)])
        with self.assertRaises(SystemExit):
            module.main(args + ['--output', str(self.fixture.root / 'new.json'),
                                '--intake-json', str(output)])
        self.assertEqual(output.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
