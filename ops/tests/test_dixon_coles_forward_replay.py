"""Original-byte replay tests; mocked CLI stdout is NOT cryptographic evidence."""
import copy
import gzip
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_dixon_coles_witness_audit as forecast_tests
from model_ab import apply as add_b
from model_dixon_coles_forward import TOP_KEY, build
from shadow_forecast import poisson_1x2
from ops.tests import test_openliga_capture_provenance as capture_tests
from ops.tests import test_openliga_capture_pack as pack_tests
from ops import openliga_capture_pack


NOW = datetime(2026, 10, 26, 10, tzinfo=timezone.utc)
KICKOFF = NOW + timedelta(hours=2)
CAPTURED = NOW + timedelta(hours=4)
CHECKED = CAPTURED + timedelta(minutes=10)


class DixonColesForwardReplayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.forecast_fixtures, self.capture_fixtures = [], []
        self.forecasts, self.captures = [], []
        self.add_forecast()
        self.add_capture()

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('ops.dixon_coles_forward_replay'),
                             'No replay binds original D captures to later native-ID FT candidates')
        return importlib.import_module('ops.dixon_coles_forward_replay')

    def add_forecast(self, *, own=NOW, change=None, include_d=True):
        helper = forecast_tests.DixonColesWitnessTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        fixture = helper.fixture
        row = fixture.shadow['predictions'][0]
        row.update(league='bundesliga', event_id='openligadb:123',
                   home='Borussia Mönchengladbach', away='RB Leipzig',
                   kickoff_utc=KICKOFF.isoformat())
        fixture.shadow['sources'] = [{'league': 'bundesliga', 'status': 'RESEARCH_ONLY'}]
        if change is not None:
            change(row)
        add_b(fixture.shadow)
        fixture.shadow[TOP_KEY] = build(fixture.shadow, now=own)
        if not include_d:
            del fixture.shadow[TOP_KEY]
        run = str(int(fixture.options['run_id']) + len(self.forecast_fixtures))
        fixture.options['run_id'] = run
        fixture.cert['runInvocationURI'] = (
            forecast_tests.proof_fixture.URI + '/actions/runs/' + run + '/attempts/1')
        helper.witness = own + timedelta(seconds=1)
        fixture.write_inputs()
        entry = {'proof_dir': fixture.proof, **{
            key: value for key, value in fixture.options.items() if key != 'now'}}
        self.forecast_fixtures.append(helper)
        self.forecasts.append(entry)
        return helper

    def add_capture(self, *, captured=CAPTURED, change=None, rows=None):
        fixture = capture_tests.OpenLigaCaptureProvenanceTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        raw_dir = self.root / ('raw-' + str(len(self.capture_fixtures)))
        manifest = pack_tests.fixture(raw_dir)
        raw_rows = rows if rows is not None else [{
            'matchID': 123, 'matchDateTimeUTC': KICKOFF.isoformat(),
            'leagueShortcut': 'bl1', 'leagueSeason': 2026,
            'team1': {'teamId': 18, 'teamName': 'Borussia Mönchengladbach'},
            'team2': {'teamId': 1635, 'teamName': 'RB Leipzig'},
            'matchIsFinished': True,
            'matchResults': [{'resultTypeID': 2, 'resultTypeKind': 'After90Minutes',
                              'pointsTeam1': 2, 'pointsTeam2': 1}],
        }]
        if change is not None:
            change(raw_rows[0])
        holder = {'fixture': fixture, 'raw_dir': raw_dir, 'manifest': manifest,
                  'rows': copy.deepcopy(raw_rows), 'captured': captured,
                  'witness': captured + timedelta(minutes=5)}
        run = str(int(fixture.options['run_id']) + 100 + len(self.capture_fixtures))
        fixture.options['run_id'] = run
        fixture.cert['runInvocationURI'] = capture_tests.URI + '/actions/runs/' + run + '/attempts/1'
        self.capture_fixtures.append(holder)
        entry = {'proof_dir': fixture.proof, **{
            key: value for key, value in fixture.options.items() if key != 'now'}}
        self.captures.append(entry)
        self.repack_capture(holder)
        return holder

    def repack_capture(self, holder):
        raw = pack_tests.encode(holder['rows'])
        (holder['raw_dir'] / 'openligadb.json').write_bytes(raw)
        manifest, captured = holder['manifest'], holder['captured']
        manifest['captured_utc'] = captured.isoformat()
        for index, receipt in enumerate(manifest['sources']):
            receipt['requested_utc'] = (captured + timedelta(seconds=2*index)).isoformat()
            receipt['completed_utc'] = (captured + timedelta(seconds=2*index+1)).isoformat()
        manifest['sources'][0].update(bytes=len(raw), raw_sha256=hashlib.sha256(raw).hexdigest())
        (holder['raw_dir'] / 'manifest.json').write_bytes(pack_tests.encode(manifest))
        target = holder['fixture'].proof / 'openliga-capture.tar'
        target.unlink(missing_ok=True)
        openliga_capture_pack.prepare(holder['raw_dir'], target, now=CHECKED)
        holder['fixture'].raw = target.read_bytes()

    def cli(self, argv, **kwargs):
        subject = Path(argv[3])
        if subject.name == 'openliga-capture.tar':
            holder = next(item for item in self.capture_fixtures
                          if item['fixture'].proof == subject.parent)
            output = holder['fixture'].stdout()
            witness = holder['witness']
        else:
            helper = next(item for item in self.forecast_fixtures
                          if item.fixture.proof == subject.parent)
            output = helper.fixture.stdout()
            witness = helper.witness
        output[0]['verificationResult']['verifiedTimestamps'][0]['timestamp'] = witness.isoformat()
        return subprocess.CompletedProcess(argv, 0, json.dumps(output).encode(), b'')

    def run_replay(self, *, forecasts=None, captures=None, now=CHECKED):
        with patch('subprocess.run', side_effect=self.cli) as cli:
            report = self.module().audit(
                self.forecasts if forecasts is None else forecasts,
                self.captures if captures is None else captures, now=now)
        return report, cli

    def assert_safe(self, report):
        self.assertEqual(report['status'], 'HOLD')
        self.assertEqual(report['production_recommendations'], 'DISABLED')
        self.assertEqual(report['certified_case_count'], 0)
        for field in ('outcomes_independently_authenticated',
                      'recorded_kickoff_independently_authenticated',
                      'model_calibration_verified', 'model_advantage_verified',
                      'automatic_model_promotion', 'eligible_for_betting_promotion'):
            self.assertIs(report[field], False)

    def assert_no_scores(self, report, *, completed=True):
        self.assertIs(report['audit_completed'], completed)
        self.assertEqual(report['settled_candidate_count'], 0)
        self.assertIsNone(report['metrics'])
        self.assert_safe(report)

    def test_fresh_four_cli_score_same_original_vectors_without_mutation(self):
        before = {path: path.read_bytes() for entry in self.forecasts+self.captures
                  for path in Path(entry['proof_dir']).iterdir()}
        report, cli = self.run_replay()
        self.assertTrue(report['audit_completed'])
        self.assertEqual(cli.call_count, 4)
        self.assertEqual(report['unique_candidate_cases'], 1)
        self.assertEqual(report['settled_candidate_count'], 1)
        case = report['cases'][0]
        self.assertEqual(case['result_status'], 'SCORED_UNVERIFIED_CANDIDATE')
        self.assertEqual(case['score_ft_candidate'], [2, 1])
        source = self.forecast_fixtures[0].fixture.shadow[TOP_KEY]['predictions'][0]
        for name in ('original', 'derived_rho0', 'candidate'):
            measured = case['models'][name]
            probabilities = source[name]
            self.assertEqual(measured['probabilities'], probabilities)
            self.assertAlmostEqual(measured['log_loss'], -math.log(probabilities[0]), places=12)
            self.assertAlmostEqual(measured['brier'], sum(
                (value-int(index == 0))**2 for index, value in enumerate(probabilities)), places=12)
            self.assertAlmostEqual(measured['rps'], (
                (probabilities[0]-1)**2+(sum(probabilities[:2])-1)**2)/2, places=12)
            self.assertEqual(report['metrics'][name]['n'], 1)
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        self.assert_safe(report)

    def test_nine_historical_proofs_remain_one_unique_research_case(self):
        for _ in range(8):
            self.add_capture()
        report, cli = self.run_replay()
        self.assertTrue(report['audit_completed'], report.get('reason'))
        self.assertEqual(cli.call_count, 12)
        self.assertEqual(report['settled_candidate_count'], 1)
        self.assertEqual(len(report['capture_references']), 9)
        self.assertEqual(report['metrics']['candidate']['n'], 1)
        self.assert_safe(report)

    def test_history_preparation_routes_prior_day_conflict_to_quarantine(self):
        import prepare_dixon_coles_cohort as adapter
        import prepare_forecast_proof as existing
        import dixon_coles_capture_history as history
        self.add_forecast(own=NOW+timedelta(minutes=1))
        later = CAPTURED+timedelta(days=1)
        def revised(row):
            row['matchResults'][0]['pointsTeam1'] = 3
        with patch.object(sys.modules[__name__], 'CHECKED', later+timedelta(minutes=10)):
            self.add_capture(captured=later, change=revised)
        for entries, fixtures in ((self.forecasts,[h.fixture for h in self.forecast_fixtures]),
                                  (self.captures,[h['fixture'] for h in self.capture_fixtures])):
            for entry, fixture in zip(entries,fixtures):
                entry['workflow_sha']=entry['source_sha']
                fixture.options['workflow_sha']=entry['source_sha']
                for field in ('githubWorkflowSHA','buildSignerDigest','buildConfigDigest'):
                    fixture.cert[field]=entry['source_sha']
        archive, capture_archive = self.root/'forecasts', self.root/'captures'
        archive.mkdir(); capture_archive.mkdir()
        pins = []
        for entry in self.forecasts:
            relative = '2026/10/26/'+entry['run_id']+'-'+entry['attempt']
            folder = archive/relative; folder.mkdir(parents=True)
            for name in existing.PROOF_NAMES:
                (folder/(name+'.gz')).write_bytes(gzip.compress((entry['proof_dir']/name).read_bytes()))
            pins.append({k: entry[k] for k in ('source_sha','workflow_sha','run_id','attempt')})
            pins[-1].update(archive_ref=relative, expected_shadow_sha256=hashlib.sha256(
                (entry['proof_dir']/'shadow.json').read_bytes()).hexdigest())
        for day, entry in zip(('26','27'), self.captures):
            folder = capture_archive/('2026/10/'+day)/(entry['run_id']+'-'+entry['attempt'])
            folder.mkdir(parents=True)
            for name in history.FILE_LIMITS:
                (folder/(name+'.gz')).write_bytes(gzip.compress((entry['proof_dir']/name).read_bytes()))
        baseline = (int(self.captures[0]['run_id']), int(self.captures[0]['attempt']))
        def metadata(argv, **kwargs):
            run, attempt = argv[-1].split('/')[-3::2]
            forecast = next((e for e in self.forecasts if e['run_id']==run), None)
            entry = forecast or next(e for e in self.captures if e['run_id']==run)
            value = {'id':int(run),'run_attempt':int(attempt),'head_sha':entry['source_sha'],
                     'head_branch':'main','status':'completed','conclusion':'success',
                     'workflow_id':history.WORKFLOW_ID,'event':'schedule',
                     'path':existing.WORKFLOW_PATH if forecast else history.WORKFLOW_PATH}
            for key in ('repository','head_repository'):
                value[key]={'id':existing.REPOSITORY_ID,'full_name':existing.REPOSITORY}
            return subprocess.CompletedProcess(argv,0,json.dumps(value).encode(),b'')
        current = self.captures[-1]
        output = self.root/'restored'
        with patch.object(adapter,'FORECASTS',tuple(pins)), patch.object(history,'BASELINE',baseline), \
             patch('subprocess.run',side_effect=metadata) as api:
            prepared=adapter.prepare(archive,output,capture_archives=capture_archive,
                capture_proof=current['proof_dir'],capture_source_sha=current['source_sha'],
                capture_workflow_sha=current['workflow_sha'],capture_run_id=current['run_id'],
                capture_attempt=current['attempt'])
        self.assertEqual(api.call_count,3)
        self.assertEqual(prepared['capture_batches'],2)
        manifest=json.loads((output/'manifest.json').read_text())
        # Route the existing fake verifier to the new exclusive copies; its
        # certificate and byte checks are still the real auditor code.
        for helper, entry in zip(self.forecast_fixtures,manifest['forecasts']):
            helper.fixture.proof=Path(entry['proof_dir'])
        self.capture_fixtures[0]['fixture'].proof=Path(manifest['captures'][0]['proof_dir'])
        report,cli=self.run_replay(forecasts=manifest['forecasts'],captures=manifest['captures'],
                                   now=later+timedelta(minutes=10))
        self.assertEqual(cli.call_count,8)
        self.assertEqual(report['quarantined_candidate_count'],1)
        self.assert_no_scores(report)
        latest,_=self.run_replay(forecasts=manifest['forecasts'],captures=manifest['captures'][-1:],
                                 now=later+timedelta(minutes=10))
        self.assertEqual(latest['settled_candidate_count'],1)
        self.assert_safe(latest)

    def test_repeated_signed_snapshots_select_earliest_before_result_lookup(self):
        self.add_forecast(own=NOW+timedelta(minutes=1))
        report, cli = self.run_replay(forecasts=list(reversed(self.forecasts)))
        self.assertEqual(cli.call_count, 7)
        self.assertEqual(report['total_witnessed_rows'], 2)
        self.assertEqual(report['duplicate_snapshot_rows'], 1)
        self.assertEqual(report['unique_candidate_cases'], 1)
        self.assertEqual(report['settled_candidate_count'], 1)
        self.assertEqual(report['cases'][0]['candidate_generated_utc'], NOW.isoformat())
        self.assertEqual(report['metrics']['candidate']['n'], 1)

    def test_legacy_capture_is_not_reconstructed_and_unfinished_stays_pending(self):
        legacy = self.add_forecast(include_d=False)
        legacy_entry = self.forecasts[-1]
        report, _ = self.run_replay(forecasts=[legacy_entry])
        self.assert_no_scores(report)
        self.assertEqual(report['unique_candidate_cases'], 0)
        self.assertNotIn(TOP_KEY, json.loads((legacy.proof/'shadow.json').read_text()))
        self.capture_fixtures[0]['rows'][0]['matchIsFinished'] = False
        self.capture_fixtures[0]['rows'][0]['matchResults'] = []
        self.repack_capture(self.capture_fixtures[0])
        report, _ = self.run_replay(forecasts=self.forecasts[:1])
        self.assert_no_scores(report)
        self.assertEqual(report['pending_candidate_count'], 1)

    def test_failed_fresh_verification_never_uses_saved_success(self):
        original = self.cli
        for subject in ('shadow.json', 'paired.json', 'slate.json', 'openliga-capture.tar'):
            with self.subTest(subject=subject):
                def fail(argv, **kwargs):
                    if Path(argv[3]).name == subject:
                        return subprocess.CompletedProcess(argv, 1, b'[]', b'PRIVATE_ERROR')
                    return original(argv, **kwargs)
                with patch('subprocess.run', side_effect=fail):
                    report = self.module().audit(self.forecasts, self.captures, now=CHECKED)
                self.assert_no_scores(report, completed=False)
                self.assertEqual(report['cases'], [])
                self.assertNotIn('PRIVATE_ERROR', json.dumps(report))

    def test_expected_shadow_digest_must_bind_original_bytes(self):
        bad = {**self.forecasts[0], 'expected_shadow_sha256': '0'*64}
        report, _ = self.run_replay(forecasts=[bad])
        self.assert_no_scores(report, completed=False)
        good = {**self.forecasts[0], 'expected_shadow_sha256': hashlib.sha256(
            (self.forecast_fixtures[0].proof/'shadow.json').read_bytes()).hexdigest()}
        report, _ = self.run_replay(forecasts=[good])
        self.assertEqual(report['settled_candidate_count'], 1)

    def test_tied_different_source_projections_are_quarantined(self):
        def changed(row):
            row['expected_home_goals'] = 1.5
            p = poisson_1x2(1.5, row['expected_away_goals'])
            row.update(zip(('p_home', 'p_draw', 'p_away'), p))
        self.add_forecast(change=changed)
        for order in (self.forecasts, list(reversed(self.forecasts))):
            report, _ = self.run_replay(forecasts=order)
            self.assert_no_scores(report)
            self.assertTrue(any(row['result_status'] == 'QUARANTINED' for row in report['cases']))

    def test_earlier_forecast_wins_even_if_later_vectors_differ(self):
        def changed(row):
            row['expected_home_goals'] = 1.5
            p = poisson_1x2(1.5, row['expected_away_goals'])
            row.update(zip(('p_home', 'p_draw', 'p_away'), p))
        self.add_forecast(own=NOW+timedelta(minutes=1), change=changed)
        report, _ = self.run_replay()
        original = self.forecast_fixtures[0].fixture.shadow[TOP_KEY]['predictions'][0]
        self.assertEqual(report['settled_candidate_count'], 1)
        self.assertEqual(report['cases'][0]['models']['candidate']['probabilities'], original['candidate'])

    def test_event_or_fixture_identity_collisions_do_not_double_count(self):
        changes = (
            lambda row: row.update(kickoff_utc=(KICKOFF+timedelta(minutes=1)).isoformat()),
            lambda row: row.update(home='Bayern München'),
            lambda row: row.update(event_id='openligadb:124'),
        )
        for change in changes:
            with self.subTest(change=change):
                self.add_forecast(own=NOW+timedelta(minutes=1), change=change)
                report, _ = self.run_replay(forecasts=[self.forecasts[0], self.forecasts[-1]])
                self.assert_no_scores(report)

    def test_duplicate_raw_id_poisoning_precedes_row_validation(self):
        holder = self.capture_fixtures[0]
        holder['rows'].append({'matchID': 123, 'matchIsFinished': True})
        self.repack_capture(holder)
        report, _ = self.run_replay()
        self.assert_no_scores(report)

    def test_full_score_conflicts_across_captures_are_not_resolved_by_outcome(self):
        for first_score, second_score in (([1, 1], [2, 2]), ([2, 1], [3, 1])):
            with self.subTest(scores=(first_score, second_score)):
                first = self.capture_fixtures[0]
                final = first['rows'][0]['matchResults'][0]
                final.update(pointsTeam1=first_score[0], pointsTeam2=first_score[1])
                self.repack_capture(first)
                later = self.add_capture(captured=CAPTURED+timedelta(minutes=1))
                final = later['rows'][0]['matchResults'][0]
                final.update(pointsTeam1=second_score[0], pointsTeam2=second_score[1])
                self.repack_capture(later)
                report, _ = self.run_replay(captures=[self.captures[0], self.captures[-1]])
                self.assert_no_scores(report)

    def test_raw_identity_conflicts_across_captures_are_quarantined(self):
        for change in (
                lambda row: row['team1'].update(teamId=999),
                lambda row: row.update(matchDateTimeUTC=(KICKOFF+timedelta(minutes=1)).isoformat()),
                lambda row: row.update(leagueShortcut='bl2')):
            with self.subTest(change=change):
                self.add_capture(captured=CAPTURED+timedelta(minutes=1), change=change)
                report, _ = self.run_replay(captures=[self.captures[0], self.captures[-1]])
                self.assert_no_scores(report)

    def test_early_conflicting_final_cannot_hide_behind_capture_time_filter(self):
        early = self.add_capture(captured=KICKOFF+timedelta(minutes=30))
        early['rows'][0]['matchResults'][0].update(pointsTeam1=3, pointsTeam2=1)
        self.repack_capture(early)
        report, _ = self.run_replay(captures=[self.captures[0], self.captures[-1]])
        self.assert_no_scores(report)
        # An identical early observation adds no new sample; the genuinely
        # later capture alone may still support one research-only replay.
        early['rows'][0]['matchResults'][0].update(pointsTeam1=2, pointsTeam2=1)
        self.repack_capture(early)
        report, _ = self.run_replay(captures=[self.captures[0], self.captures[-1]])
        self.assertEqual(report['settled_candidate_count'], 1)
        self.assertEqual(report['metrics']['candidate']['n'], 1)

    def test_invalid_regulation_final_and_typed_goals_cannot_score(self):
        holder = self.capture_fixtures[0]
        original = copy.deepcopy(holder['rows'])
        attacks = (
            lambda row: row.update(matchIsFinished=1),
            lambda row: row['matchResults'][0].update(pointsTeam1=True),
            lambda row: row['matchResults'][0].update(pointsTeam2=1.0),
            lambda row: row['matchResults'][0].update(resultTypeID=2.0),
            lambda row: row['matchResults'][0].update(resultTypeKind='AfterExtraTime'),
            lambda row: row['matchResults'].append(copy.deepcopy(row['matchResults'][0])),
        )
        for change in attacks:
            with self.subTest(change=change):
                holder['rows'] = copy.deepcopy(original)
                change(holder['rows'][0]); self.repack_capture(holder)
                report, _ = self.run_replay()
                self.assert_no_scores(report)

    def test_native_id_exact_kickoff_and_source_names_are_required(self):
        holder = self.capture_fixtures[0]
        original = copy.deepcopy(holder['rows'])
        for change in (
                lambda row: row.update(matchID=124),
                lambda row: row.update(matchDateTimeUTC=(KICKOFF+timedelta(seconds=1)).isoformat()),
                lambda row: row['team1'].update(teamName='Borussia Monchengladbach')):
            with self.subTest(change=change):
                holder['rows'] = copy.deepcopy(original)
                change(holder['rows'][0]); self.repack_capture(holder)
                report, _ = self.run_replay()
                self.assert_no_scores(report)

    def test_late_capture_and_match_duration_boundaries(self):
        holder = self.capture_fixtures[0]
        for minutes, seconds, expected in ((99, 59, 0), (100, 0, 1)):
            with self.subTest(capture_minutes=minutes, seconds=seconds):
                holder['captured'] = KICKOFF+timedelta(minutes=minutes, seconds=seconds)
                holder['witness'] = holder['captured']+timedelta(minutes=1)
                self.repack_capture(holder)
                report, _ = self.run_replay()
                self.assertTrue(report['audit_completed'])
                self.assertEqual(report['settled_candidate_count'], expected)
        for now, expected in ((KICKOFF+timedelta(minutes=120)-timedelta(microseconds=1), 0),
                              (KICKOFF+timedelta(minutes=120), 1)):
            with self.subTest(now=now):
                report, _ = self.run_replay(now=now)
                self.assertTrue(report['audit_completed'])
                self.assertEqual(report['settled_candidate_count'], expected)

    def test_forecast_witness_buffer_and_composite_identity_remain_unscored(self):
        helper = self.forecast_fixtures[0]
        for seconds, expected in ((600, 0), (601, 1)):
            with self.subTest(seconds=seconds):
                helper.witness = KICKOFF-timedelta(seconds=seconds)
                report, _ = self.run_replay()
                self.assertEqual(report['settled_candidate_count'], expected)
        self.add_forecast(change=lambda row: row.update(event_id='two-source-utc-example'))
        report, _ = self.run_replay(forecasts=[self.forecasts[-1]])
        self.assert_no_scores(report)
        self.assertEqual(report['pending_candidate_count'], 1)

    def test_post_verification_subject_and_capture_changes_are_rejected(self):
        import dixon_coles_witness_audit
        from ops import openliga_capture_provenance
        for module, target, filename in (
                (dixon_coles_witness_audit, self.forecast_fixtures[0].proof, 'shadow.json'),
                (dixon_coles_witness_audit, self.forecast_fixtures[0].proof, 'paired.json'),
                (openliga_capture_provenance, self.capture_fixtures[0]['fixture'].proof, 'capture.sigstore.json')):
            with self.subTest(filename=filename):
                original_function = module.audit
                path = target/filename; original = path.read_bytes()
                def changed(*args, **kwargs):
                    report = original_function(*args, **kwargs)
                    path.write_bytes(original+b'\n')
                    return report
                with patch.object(module, 'audit', side_effect=changed), \
                     patch('subprocess.run', side_effect=self.cli):
                    report = self.module().audit(self.forecasts, self.captures, now=CHECKED)
                self.assert_no_scores(report, completed=False)
                path.write_bytes(original)

    def test_missing_capture_or_invalid_batch_is_not_a_false_positive(self):
        report, _ = self.run_replay(captures=[])
        self.assert_no_scores(report)
        self.assertEqual(report['pending_candidate_count'], 1)
        for forecasts, captures in ((self.forecasts*17, self.captures),
                                    (self.forecasts, self.captures*33),
                                    ('not-a-batch', self.captures)):
            with self.subTest(forecasts_type=type(forecasts), capture_count=len(captures)):
                report, _ = self.run_replay(forecasts=forecasts, captures=captures)
                self.assert_no_scores(report, completed=False)

    def test_cli_new_output_outside_inputs_and_no_overwrite(self):
        manifest = self.root/'manifest.json'
        document = {'schema': 'football-king-dixon-coles-forward-replay-input-v1',
                    'forecasts': [{**row, 'proof_dir': str(row['proof_dir'])} for row in self.forecasts],
                    'captures': [{**row, 'proof_dir': str(row['proof_dir'])} for row in self.captures]}
        manifest.write_text(json.dumps(document))
        source = self.forecast_fixtures[0].proof/'shadow.json'
        alias = self.root/'alias.json'; os.link(source, alias)
        for output in (manifest, source, self.capture_fixtures[0]['fixture'].proof/'new.json', alias):
            with self.subTest(output=output), patch('sys.stderr', new_callable=io.StringIO):
                with self.assertRaises(SystemExit):
                    self.module().main(['--manifest', str(manifest), '--output', str(output)])
        alias.unlink()
        output = self.root/'report.json'
        with patch('subprocess.run', side_effect=self.cli):
            self.assertEqual(self.module().main(['--manifest', str(manifest), '--output', str(output)]), 0)
        self.assertEqual(json.loads(output.read_text())['settled_candidate_count'], 1)
        with patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit):
            self.module().main(['--manifest', str(manifest), '--output', str(output)])


if __name__ == '__main__':
    unittest.main()
