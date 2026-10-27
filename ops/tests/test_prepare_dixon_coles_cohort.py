"""Pinned preparation tests; mocked API metadata is not signature evidence."""
import copy
import gzip
import hashlib
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_forecast_proof as existing


class PrepareDixonColesCohortTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.archives = self.base / 'forecast_provenance'
        self.archives.mkdir()
        self.capture = self.base / 'capture-proof'
        self.capture.mkdir()
        (self.capture/'openliga-capture.tar').write_bytes(b'controlled bytes')
        (self.capture/'capture.sigstore.json').write_bytes(b'{}')
        self.output = self.base/'cohort'
        self.raw = {}
        self.pins = []
        for index, run in enumerate(('40295717023', '40377738523')):
            payloads = {name: json.dumps({'input': index, 'subject': name}).encode()
                        for name in existing.PROOF_NAMES}
            folder = self.archives/'2026'/'10'/'26'/(run+'-1')
            folder.mkdir(parents=True)
            for name, raw in payloads.items():
                (folder/(name+'.gz')).write_bytes(gzip.compress(raw))
            self.raw[run] = payloads
            self.pins.append({'run_id': run, 'attempt': '1', 'source_sha': str(index+1)*40,
                              'workflow_sha': str(index+1)*40,
                              'expected_shadow_sha256': hashlib.sha256(payloads['shadow.json']).hexdigest(),
                              'archive_ref': '2026/10/26/'+run+'-1'})
        self.capture_options = {'capture_proof': self.capture, 'capture_source_sha': 'c'*40,
                                'capture_workflow_sha': 'd'*40, 'capture_run_id': '40053042424',
                                'capture_attempt': '1'}

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('prepare_dixon_coles_cohort'),
                             'No adapter restores the registered D forecast cohort without market pairs')
        return importlib.import_module('prepare_dixon_coles_cohort')

    def metadata(self, argv, **kwargs):
        run = argv[-1].split('/')[-3]
        pin = next(p for p in self.pins if p['run_id'] == run)
        value = {'id': int(run), 'run_attempt': 1, 'head_branch': 'main',
                 'path': existing.WORKFLOW_PATH, 'status': 'completed', 'conclusion': 'success',
                 'head_sha': pin['source_sha']}
        for key in ('repository', 'head_repository'):
            value[key] = {'id': existing.REPOSITORY_ID, 'full_name': existing.REPOSITORY}
        return subprocess.CompletedProcess(argv, 0, json.dumps(value).encode(), b'')

    def prepare(self, **overrides):
        module = self.module()
        with patch.object(module, 'FORECASTS', tuple(copy.deepcopy(self.pins))), \
             patch.object(existing.subprocess, 'run', side_effect=self.metadata) as api:
            result = module.prepare(self.archives, self.output,
                                    **dict(self.capture_options, **overrides))
        return result, api

    def test_two_pinned_original_batches_restore_exact_bytes_and_manifest(self):
        before = {p: p.read_bytes() for p in self.archives.rglob('*.gz')}
        result, api = self.prepare()
        self.assertEqual(api.call_count, 2)
        manifest = json.loads((self.output/'manifest.json').read_text())
        self.assertEqual(manifest['schema'], 'football-king-dixon-coles-forward-replay-input-v1')
        self.assertEqual(set(manifest), {'schema', 'forecasts', 'captures'})
        self.assertEqual(len(manifest['forecasts']), 2)
        self.assertEqual(len(manifest['captures']), 1)
        for item in manifest['forecasts']:
            self.assertEqual(set(item), {'proof_dir', 'source_sha', 'workflow_sha', 'run_id',
                                         'attempt', 'expected_shadow_sha256'})
            self.assertEqual({p.name: p.read_bytes() for p in Path(item['proof_dir']).iterdir()},
                             self.raw[item['run_id']])
        self.assertEqual(result['manifest'], str(self.output/'manifest.json'))
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_missing_pinned_run_does_not_fall_back_to_a_newer_run(self):
        original = self.archives/'2026/10/26/40295717023-1'
        for path in original.iterdir():
            path.unlink()
        original.rmdir()
        with self.assertRaises(existing.PreparationError):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_shadow_digest_mismatch_rejects_before_any_publication(self):
        path = self.archives/'2026/10/26/40377738523-1/shadow.json.gz'
        path.write_bytes(gzip.compress(b'{"changed":true}'))
        with self.assertRaisesRegex(existing.PreparationError, 'PINNED_SHADOW_DIGEST_MISMATCH'):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_wrong_fresh_metadata_never_uses_saved_reports(self):
        module = self.module()
        with patch.object(module, 'FORECASTS', tuple(self.pins)), \
             patch.object(existing, '_run_metadata', return_value='f'*40):
            with self.assertRaisesRegex(existing.PreparationError, 'PINNED_FORECAST_COMMIT_MISMATCH'):
                module.prepare(self.archives, self.output, **self.capture_options)
        self.assertFalse(self.output.exists())

    def test_bounded_invalid_gzip_and_json_reject_without_partial_output(self):
        path = self.archives/'2026/10/26/40377738523-1/paired.json.gz'
        original = path.read_bytes()
        for raw in (b'notgzip', gzip.compress(b'{broken'), gzip.compress(b'{"x":1,"x":2}')):
            with self.subTest(raw=raw[:10]):
                path.write_bytes(raw)
                with self.assertRaises(existing.PreparationError):
                    self.prepare()
                self.assertFalse(self.output.exists())
        path.write_bytes(original)
        with patch.object(existing, 'MAX_SUBJECT_BYTES', 8):
            with self.assertRaises(existing.PreparationError):
                self.prepare()
        self.assertFalse(self.output.exists())

    def test_symlinks_and_overlapping_paths_reject_without_writing(self):
        module = self.module()
        alias = self.base/'alias'
        alias.symlink_to(self.archives, target_is_directory=True)
        for root, destination, capture in (
                (alias, self.output, self.capture),
                (self.archives, self.archives/'fresh', self.capture),
                (self.archives, self.capture/'fresh', self.capture),
                (self.archives, self.output, self.output/'nested')):
            with self.subTest(root=root, destination=destination):
                with self.assertRaises(existing.PreparationError):
                    module.prepare(root, destination, **dict(self.capture_options, capture_proof=capture))
        self.assertFalse(self.output.exists())

    def test_existing_output_and_creation_race_are_never_overwritten(self):
        module = self.module()
        self.output.mkdir(); keep=self.output/'keep'; keep.write_bytes(b'original')
        with self.assertRaises(existing.PreparationError):
            self.prepare()
        self.assertEqual(keep.read_bytes(), b'original')
        keep.unlink(); self.output.rmdir()
        real = existing._run_metadata
        def appeared(run, attempt):
            if not self.output.exists():
                self.output.mkdir()
            return next(p['source_sha'] for p in self.pins if p['run_id'] == run)
        with patch.object(module, 'FORECASTS', tuple(self.pins)), \
             patch.object(existing, '_run_metadata', side_effect=appeared):
            with self.assertRaisesRegex(existing.PreparationError, 'OUTPUT_DIRECTORY_ALREADY_EXISTS'):
                module.prepare(self.archives, self.output, **self.capture_options)
        self.assertTrue(self.output.is_dir())

    def test_publication_failure_removes_only_new_owned_output(self):
        module = self.module()
        with patch.object(module.os, 'link', side_effect=PermissionError('SECRET must not escape')):
            with self.assertRaises(existing.PreparationError):
                self.prepare()
        self.assertFalse(self.output.exists())
        self.assertTrue(self.capture.is_dir())

    def test_nonempty_root_replacement_after_mkdir_rejects_before_writing(self):
        module = self.module()
        real_mkdir = os.mkdir
        parked = self.base/'parked-owned-root'

        def replace_root(path, *args, **kwargs):
            result = real_mkdir(path, *args, **kwargs)
            if path == self.output.name and kwargs.get('dir_fd') is not None:
                self.output.rename(parked)
                real_mkdir(self.output)
                (self.output/'foreign-marker').write_bytes(b'keep')
            return result

        with patch.object(module.os, 'mkdir', side_effect=replace_root):
            with self.assertRaises(existing.PreparationError):
                self.prepare()
        self.assertEqual({p.name: p.read_bytes() for p in self.output.iterdir()},
                         {'foreign-marker': b'keep'})
        self.assertEqual(list(parked.iterdir()), [])

    def test_failure_cleanup_never_reopens_replaced_child(self):
        module = self.module()
        parked = self.base/'parked-owned-child'
        child = self.output/(self.pins[0]['run_id']+'-'+self.pins[0]['attempt'])

        def replace_child_before_failure(*args, **kwargs):
            child.rename(parked)
            child.mkdir()
            for name in existing.PROOF_NAMES:
                (child/name).write_bytes(b'foreign user file')
            raise PermissionError('injected publication failure')

        with patch.object(module.os, 'link', side_effect=replace_child_before_failure):
            with self.assertRaises(existing.PreparationError):
                self.prepare()
        self.assertTrue(child.is_dir(), 'cleanup removed the foreign replacement child')
        self.assertEqual({p.name: p.read_bytes() for p in child.iterdir()},
                         {name: b'foreign user file' for name in existing.PROOF_NAMES})

    def test_nonempty_child_replacement_rejects_before_writing(self):
        module = self.module()
        real_mkdir = os.mkdir
        name = self.pins[0]['run_id']+'-'+self.pins[0]['attempt']
        child, parked = self.output/name, self.base/'parked-empty-child'

        def replace_child(path, *args, **kwargs):
            result = real_mkdir(path, *args, **kwargs)
            if path == name and kwargs.get('dir_fd') is not None:
                child.rename(parked)
                real_mkdir(child)
                (child/'foreign-marker').write_bytes(b'keep')
            return result

        with patch.object(module.os, 'mkdir', side_effect=replace_child):
            with self.assertRaises(existing.PreparationError):
                self.prepare()
        self.assertEqual({p.name: p.read_bytes() for p in child.iterdir()},
                         {'foreign-marker': b'keep'})
        self.assertEqual(list(parked.iterdir()), [])

    def test_final_identity_checks_reject_root_and_child_replacements(self):
        module = self.module()
        real_link = os.link
        for replaced in ('root', 'child'):
            with self.subTest(replaced=replaced):
                self.output = self.base/('cohort-'+replaced)
                target = (self.output if replaced == 'root' else
                          self.output/(self.pins[0]['run_id']+'-'+self.pins[0]['attempt']))
                parked = self.base/('parked-'+replaced)

                def replace_before_link(*args, **kwargs):
                    target.rename(parked)
                    target.mkdir()
                    (target/'foreign-marker').write_bytes(b'keep')
                    return real_link(*args, **kwargs)

                with patch.object(module.os, 'link', side_effect=replace_before_link):
                    with self.assertRaises(existing.PreparationError):
                        self.prepare()
                self.assertEqual({p.name: p.read_bytes() for p in target.iterdir()},
                                 {'foreign-marker': b'keep'})
                self.assertFalse((self.output/'manifest.json').exists())
                self.assertEqual(list(parked.iterdir()), [])

    def test_unexpected_entries_reject_before_manifest_and_are_preserved(self):
        module = self.module()
        real_create = module._create_file
        for location in ('root', 'child'):
            with self.subTest(location=location):
                self.output = self.base/('cohort-unexpected-'+location)
                target = (self.output if location == 'root' else
                          self.output/(self.pins[0]['run_id']+'-'+self.pins[0]['attempt']))

                def insert_entry(directory_fd, name, raw, created):
                    real_create(directory_fd, name, raw, created)
                    if name == '.manifest.json.stage':
                        (target/'foreign-marker').write_bytes(b'keep')

                with patch.object(module, '_create_file', side_effect=insert_entry), \
                     patch.object(module.os, 'link') as publish:
                    with self.assertRaises(existing.PreparationError):
                        self.prepare()
                publish.assert_not_called()
                self.assertEqual({p.name: p.read_bytes() for p in target.iterdir()},
                                 {'foreign-marker': b'keep'})
                self.assertFalse((self.output/'manifest.json').exists())

    def test_cleanup_preserves_replaced_proof_stage_and_manifest_files(self):
        module = self.module()
        real_link = os.link
        for replaced in ('proof', 'stage', 'manifest'):
            with self.subTest(replaced=replaced):
                self.output = self.base/('cohort-file-'+replaced)
                target = (self.output/(self.pins[0]['run_id']+'-'+self.pins[0]['attempt'])/
                          existing.PROOF_NAMES[0] if replaced == 'proof' else
                          self.output/('.manifest.json.stage' if replaced == 'stage' else 'manifest.json'))

                def replace_file(*args, **kwargs):
                    if replaced == 'manifest':
                        real_link(*args, **kwargs)
                    target.unlink()
                    target.write_bytes(b'foreign user file')
                    if replaced != 'manifest':
                        raise PermissionError('injected publication failure')

                with patch.object(module.os, 'link', side_effect=replace_file):
                    with self.assertRaises(existing.PreparationError):
                        self.prepare()
                self.assertEqual(target.read_bytes(), b'foreign user file')

    def test_manifest_publication_waits_for_complete_files_and_never_overwrites(self):
        module = self.module()
        real_link = os.link
        for collision in (False, True):
            with self.subTest(collision=collision):
                self.output = self.base/('cohort-link-'+str(collision))
                manifest = self.output/'manifest.json'

                def publish(*args, **kwargs):
                    self.assertFalse(manifest.exists())
                    for pin in self.pins:
                        child = self.output/(pin['run_id']+'-'+pin['attempt'])
                        self.assertEqual({p.name: p.read_bytes() for p in child.iterdir()},
                                         self.raw[pin['run_id']])
                    staged = json.loads((self.output/'.manifest.json.stage').read_text())
                    self.assertEqual(len(staged['forecasts']), 2)
                    if collision:
                        manifest.write_bytes(b'foreign manifest')
                    return real_link(*args, **kwargs)

                with patch.object(module.os, 'link', side_effect=publish):
                    if collision:
                        with self.assertRaises(existing.PreparationError):
                            self.prepare()
                    else:
                        self.assertTrue(self.prepare()[0]['preparation_completed'])
                if collision:
                    self.assertEqual(manifest.read_bytes(), b'foreign manifest')
                    self.assertEqual(list(self.output.iterdir()), [manifest])

    def test_capture_context_is_strict_and_capture_files_are_regular(self):
        for field, values in {'capture_source_sha': ['F'*40, 'a'*39, True],
                              'capture_workflow_sha': ['F'*40, False],
                              'capture_run_id': ['0', '01', 1],
                              'capture_attempt': ['0', '01', True]}.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(existing.PreparationError):
                    self.prepare(**{field:value})
        path=self.capture/'openliga-capture.tar'; path.unlink()
        os.mkfifo(path)
        with self.assertRaises(existing.PreparationError):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_cli_success_and_failure_do_not_echo_sensitive_errors(self):
        module=self.module()
        argv=['--archives',str(self.archives),'--output-dir',str(self.output),
              '--capture-proof',str(self.capture),'--capture-source-sha','c'*40,
              '--capture-workflow-sha','d'*40,'--capture-run-id','40053042424','--capture-attempt','1']
        with patch.object(module,'FORECASTS',tuple(self.pins)), \
             patch.object(existing.subprocess,'run',side_effect=self.metadata), \
             patch('sys.stdout',new_callable=io.StringIO) as out:
            self.assertEqual(module.main(argv),0)
        self.assertEqual(json.loads(out.getvalue())['manifest'],str(self.output/'manifest.json'))
        for args in ([], argv):
            with patch('sys.stdout',new_callable=io.StringIO) as out, \
                 patch('sys.stderr',new_callable=io.StringIO) as err:
                self.assertEqual(module.main(args),1)
            self.assertFalse(json.loads(out.getvalue())['preparation_completed'])
            self.assertEqual(err.getvalue(),'')
            self.assertNotIn('SECRET',out.getvalue())


if __name__=='__main__':
    unittest.main()
