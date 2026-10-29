"""Exercise the actual daily intake guard without network, providers or credentials."""
import ast
import copy
import json
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import time
import traceback
import unittest
from unittest.mock import call, patch


REPOSITORY = 'CHANCHUNWA1989/football-king-report'
WORKFLOW_PATH = '.github/workflows/four-model-shadow-daily.yml'
RUN_ID = '40806106414'
ATTEMPT = '1'
SOURCE_SHA = 'a' * 40
PRIVATE = 'PRIVATE_RUN_CONTEXT_MUST_NOT_BE_SAVED'
DIAGNOSTIC_KEYS = {'schema', 'run_id', 'attempt', 'status', 'conclusion', 'attempted_reads'}


def workflow_guard():
    """Compile only the function shipped in the controlled intake's Python here-doc."""
    workflow = Path(__file__).resolve().parents[2] / WORKFLOW_PATH
    raw = workflow.read_text(encoding='utf-8')
    job = re.search(r'^  controlled-case-intake:\n(.*?)(?=^  [a-z][a-z0-9-]*:|\Z)',
                    raw, re.M | re.S)
    if job is None:
        raise AssertionError('The daily controlled-case-intake job is missing')
    step = re.search(
        r'^      - name: Bind signed capture bytes to the original forecast\n'
        r'(.*?)(?=^      - |\Z)', job.group(1), re.M | re.S)
    if step is None:
        raise AssertionError('The signed capture binding step is missing')
    heredoc = re.search(r"^          python - <<'PYTHON'\n(.*?)^          PYTHON\s*$",
                        step.group(1), re.M | re.S)
    if heredoc is None:
        raise AssertionError('The signed capture binding Python here-doc is missing')
    tree = ast.parse(textwrap.dedent(heredoc.group(1)))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name == 'load_capture_run_context']
    if len(functions) != 1:
        raise AssertionError('The actual daily workflow must define one load_capture_run_context')
    namespace = {'json': json, 'subprocess': subprocess, 'time': time, 'Path': Path}
    module = ast.Module(body=functions, type_ignores=[])
    exec(compile(module, str(workflow), 'exec'), namespace)
    return namespace['load_capture_run_context']


def run_context(status='in_progress', conclusion=None, **changes):
    # Synthetic payloads test the guard; they do not establish the incident's API status.
    context = {
        'id': int(RUN_ID), 'run_attempt': int(ATTEMPT), 'head_sha': SOURCE_SHA,
        'head_branch': 'main', 'path': WORKFLOW_PATH, 'workflow_id': 383990991,
        'event': 'schedule', 'status': status, 'conclusion': conclusion,
        'repository': {'id': 1411226578, 'full_name': REPOSITORY},
        'head_repository': {'id': 1411226578, 'full_name': REPOSITORY},
        'url': 'https://example.invalid/' + PRIVATE,
        'private_field': {'token': PRIVATE},
    }
    context.update(changes)
    return context


class ControlledCaptureRunContextTests(unittest.TestCase):
    def setUp(self):
        self.guard = workflow_guard()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sequence = 0

    def invoke(self, responses, *, current_run=True, saved=False, **pins):
        self.sequence += 1
        diagnostic_path = self.root / ('diagnostic-' + str(self.sequence) + '.json')
        if saved:
            (self.root / 'saved-run-context.json').write_text(
                json.dumps(run_context('completed', 'success')))
        effects = []
        for response in responses:
            if isinstance(response, Exception):
                effects.append(response)
            elif isinstance(response, subprocess.CompletedProcess):
                effects.append(response)
            else:
                body = response if isinstance(response, bytes) else json.dumps(response).encode()
                effects.append(subprocess.CompletedProcess(['gh'], 0, body, b''))
        arguments = dict(run_id=RUN_ID, attempt=ATTEMPT, source_sha=SOURCE_SHA,
                         current_run=current_run, diagnostic_path=diagnostic_path)
        arguments.update(pins)
        value, error = None, None
        with patch.object(subprocess, 'run', side_effect=effects) as api, \
                patch.object(time, 'sleep') as sleep:
            try:
                value = self.guard(**arguments)
            except Exception as caught:
                error = caught
        diagnostic = json.loads(diagnostic_path.read_text()) if diagnostic_path.exists() else None
        return dict(value=value, error=error, api=api, sleep=sleep, diagnostic=diagnostic)

    def assert_diagnostic(self, outcome, reads, *, status=None, conclusion=None):
        diagnostic = outcome['diagnostic']
        self.assertIsInstance(diagnostic, dict)
        self.assertEqual(set(diagnostic), DIAGNOSTIC_KEYS)
        self.assertEqual(diagnostic['schema'], 'football-king-controlled-capture-run-context-v1')
        self.assertIs(type(diagnostic['attempted_reads']), int)
        self.assertEqual(diagnostic['attempted_reads'], reads)
        self.assertNotIn(PRIVATE, json.dumps(diagnostic))
        self.assertNotIn('https://', json.dumps(diagnostic))
        if status is not None:
            self.assertEqual(diagnostic['status'], status)
            self.assertEqual(diagnostic['conclusion'], conclusion)

    def assert_reads(self, outcome, count, sleeps):
        self.assertEqual(outcome['api'].call_count, count)
        self.assertEqual(outcome['sleep'].call_args_list, [call(2)] * sleeps)
        for read in outcome['api'].call_args_list:
            self.assertEqual(read.args[0], [
                'gh', 'api', 'repos/' + REPOSITORY + '/actions/runs/' + RUN_ID])
            self.assertTrue(read.kwargs.get('capture_output') is True or
                            read.kwargs.get('stdout') is subprocess.PIPE)
            self.assertEqual(read.kwargs.get('timeout'), 30)

    def assert_failure(self, outcome, reason, reads, sleeps=0):
        self.assertIsInstance(outcome['error'], ValueError)
        self.assertEqual(str(outcome['error']), reason)
        self.assertIsNone(outcome['value'])
        self.assertNotIn(PRIVATE, ''.join(traceback.format_exception(outcome['error'])))
        self.assert_reads(outcome, reads, sleeps)
        self.assert_diagnostic(outcome, reads)

    def test_current_in_progress_and_completed_success_accept_validated_identity(self):
        for status, conclusion in (('in_progress', None), ('completed', 'success')):
            for event in ('schedule', 'workflow_dispatch'):
                with self.subTest(status=status, event=event):
                    context = run_context(status, conclusion, event=event)
                    outcome = self.invoke([context])
                    self.assertIsNone(outcome['error'])
                    self.assertEqual(outcome['value'], context)
                    self.assert_reads(outcome, 1, 0)
                    self.assert_diagnostic(outcome, 1, status=status, conclusion=conclusion)
                    self.assertEqual(outcome['diagnostic']['run_id'], RUN_ID)
                    self.assertEqual(outcome['diagnostic']['attempt'], ATTEMPT)

    def test_each_transient_current_status_retries_then_accepts_in_progress(self):
        for status in ('queued', 'pending', 'requested', 'waiting'):
            with self.subTest(status=status):
                context = run_context()
                outcome = self.invoke([run_context(status), context])
                self.assertIsNone(outcome['error'])
                self.assertEqual(outcome['value'], context)
                self.assert_reads(outcome, 2, 1)
                self.assert_diagnostic(outcome, 2, status='in_progress')

    def test_current_run_can_become_completed_success_on_fifth_read(self):
        context = run_context('completed', 'success')
        outcome = self.invoke([run_context(status) for status in
                               ('queued', 'pending', 'requested', 'waiting')] + [context])
        self.assertIsNone(outcome['error'])
        self.assertEqual(outcome['value'], context)
        self.assert_reads(outcome, 5, 4)
        self.assert_diagnostic(outcome, 5, status='completed', conclusion='success')

    def test_exhausted_transient_reads_fail_closed_with_bounded_diagnostic(self):
        outcome = self.invoke([run_context('queued')] * 5 + [run_context()])
        self.assert_failure(outcome, 'CAPTURE_RUN_CONTEXT_NOT_READY', 5, 4)
        self.assert_diagnostic(outcome, 5, status='queued')

    def test_every_identity_pin_is_checked_before_status_on_every_read(self):
        mutations = [
            ('id', int(RUN_ID) + 1), ('id', RUN_ID), ('id', True),
            ('run_attempt', 2), ('run_attempt', ATTEMPT), ('run_attempt', True),
            ('head_sha', 'b' * 40), ('head_sha', 'a' * 39),
            ('head_branch', 'feature'), ('path', '.github/workflows/other.yml'),
            ('workflow_id', 383990992), ('workflow_id', '383990991'),
            ('event', 'pull_request'),
        ]
        for repository in ('repository', 'head_repository'):
            mutations.extend(((repository + '.id', 1),
                              (repository + '.id', '1411226578'),
                              (repository + '.full_name', 'other/repository')))
        for key, value in mutations:
            for position in (0, 1):
                with self.subTest(pin=key, value=value, response=position + 1):
                    bad = run_context('queued' if position == 0 else 'in_progress')
                    if '.' in key:
                        parent, field = key.split('.')
                        bad[parent][field] = value
                    else:
                        bad[key] = value
                    responses = ([run_context('queued')] if position else []) + [bad, run_context()]
                    outcome = self.invoke(responses)
                    self.assert_failure(outcome, 'CAPTURE_RUN_CONTEXT_MISMATCH',
                                        position + 1, position)

    def test_failed_completed_and_unknown_states_never_retry_or_accept(self):
        states = [('completed', conclusion) for conclusion in
                  ('failure', 'cancelled', 'timed_out', 'action_required', None, PRIVATE)]
        states += [('in_progress', conclusion) for conclusion in
                   ('success', 'failure', PRIVATE, [PRIVATE], {'token': PRIVATE})]
        states += [(status, None) for status in
                   ('cancelled', 'unknown', PRIVATE, [PRIVATE], {'token': PRIVATE})]
        for status, conclusion in states:
            with self.subTest(status=status, conclusion=conclusion):
                outcome = self.invoke([run_context(status, conclusion), run_context()])
                self.assert_failure(outcome, 'CAPTURE_RUN_CONTEXT_REJECTED', 1)

    def test_historical_run_requires_completed_success_without_retry(self):
        context = run_context('completed', 'success')
        outcome = self.invoke([context], current_run=False)
        self.assertIsNone(outcome['error'])
        self.assertEqual(outcome['value'], context)
        self.assert_reads(outcome, 1, 0)
        for status, conclusion in [(status, None) for status in
                                   ('queued', 'pending', 'requested', 'waiting', 'in_progress')] + [
                                       ('completed', 'failure')]:
            with self.subTest(status=status, conclusion=conclusion):
                outcome = self.invoke([run_context(status, conclusion), context], current_run=False)
                self.assert_failure(outcome, 'CAPTURE_RUN_CONTEXT_REJECTED', 1)

    def test_api_failures_and_malformed_context_do_not_use_saved_success(self):
        unavailable = [
            subprocess.CompletedProcess(['gh'], 1, PRIVATE.encode(), PRIVATE.encode()),
            subprocess.CalledProcessError(1, ['gh'], output=PRIVATE.encode(), stderr=PRIVATE.encode()),
            subprocess.TimeoutExpired(['gh'], 30, output=PRIVATE.encode(), stderr=PRIVATE.encode()),
            OSError(PRIVATE), b'', b'{', (b' ' * 2000001),
            b'[' * 30000 + b'0' + b']' * 30000,
        ]
        for response in unavailable:
            with self.subTest(response=type(response).__name__, size=(
                    len(response) if isinstance(response, bytes) else None)):
                outcome = self.invoke([response, run_context()], saved=True)
                self.assert_failure(outcome, 'CAPTURE_RUN_CONTEXT_API_UNAVAILABLE', 1)
        malformed = [None, [], 1, {'status': 'in_progress'},
                     run_context(repository=None), run_context(head_repository=[])]
        for key in ('head_sha', 'status', 'conclusion'):
            for state in ('in_progress', 'queued'):
                missing = copy.deepcopy(run_context(state))
                del missing[key]
                malformed.append(missing)
        for response in malformed:
            with self.subTest(context_type=type(response).__name__):
                outcome = self.invoke([response, run_context()], saved=True)
                self.assert_failure(outcome, 'CAPTURE_RUN_CONTEXT_MISMATCH', 1)

    def test_invalid_requested_pins_reject_before_api_and_cannot_leak_to_diagnostic(self):
        invalid = [
            {'run_id': PRIVATE}, {'run_id': '0'}, {'run_id': True},
            {'attempt': PRIVATE}, {'attempt': '0'}, {'attempt': True},
            {'source_sha': 'a' * 39}, {'source_sha': 'g' * 40},
            {'source_sha': PRIVATE}, {'source_sha': True}, {'current_run': 'false'},
        ]
        for pins in invalid:
            with self.subTest(pins=pins):
                outcome = self.invoke([run_context()], **pins)
                self.assert_failure(outcome, 'CAPTURE_RUN_CONTEXT_MISMATCH', 0)


if __name__ == '__main__':
    unittest.main()
