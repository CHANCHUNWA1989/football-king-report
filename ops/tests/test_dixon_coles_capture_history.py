"""Result-blind archive restoration; mocked API is not cryptographic evidence."""
import copy
import gzip
import importlib
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


class CaptureHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base/'archives'
        self.root.mkdir()
        self.current = self.base/'current'
        self.current.mkdir()
        self.files = {'openliga-capture.tar': b'tar bytes are deliberately not JSON',
                      'capture.sigstore.json': b'{}'}
        for name, raw in self.files.items():
            (self.current/name).write_bytes(raw)
        self.baseline = self.archive('40258192078', '1', '2026/10/26')
        self.later = self.archive('40437105506', '1', '2026/10/27')
        self.cutoff = {'run_id':'40637105506', 'attempt':'1'}

    def archive(self, run, attempt, day, files=None):
        folder = self.root/day/(run+'-'+attempt)
        folder.mkdir(parents=True)
        for name, raw in (files or self.files).items():
            (folder/(name+'.gz')).write_bytes(gzip.compress(raw, mtime=0))
        return folder

    def module(self):
        return importlib.import_module('dixon_coles_capture_history')

    def metadata(self, argv, **kwargs):
        run, attempt = argv[-1].split('/')[-3::2]
        value={'id':int(run),'run_attempt':int(attempt),'workflow_id':383990991,
               'head_branch':'main','path':'.github/workflows/four-model-shadow-daily.yml',
               'event':'schedule','status':'completed','conclusion':'success',
               'head_sha':format(int(run),'040x')}
        for key in ('repository','head_repository'):
            value[key]={'id':existing.REPOSITORY_ID,'full_name':existing.REPOSITORY}
        return subprocess.CompletedProcess(argv,0,json.dumps(value).encode(),b'')

    def collect(self, **changes):
        with patch.object(self.module().subprocess,'run',side_effect=self.metadata) as api:
            result=self.module().collect(self.root,current_proof=self.current,
                                         **dict(self.cutoff,**changes))
        return result,api

    def test_all_history_retained_in_run_order_without_decoding_tar_as_json(self):
        result,api=self.collect()
        self.assertEqual([r['reference']['run_id'] for r in result],['40258192078','40437105506'])
        self.assertEqual(api.call_count,2)
        for row in result:
            self.assertEqual(set(row),{'name','files','reference','archive_ref'})
            self.assertEqual(row['files'],self.files)
            ref=row['reference']
            self.assertEqual(set(ref),{'source_sha','workflow_sha','run_id','attempt'})
            self.assertEqual(ref['source_sha'],ref['workflow_sha'])

    def test_newer_and_older_archives_excluded_by_run_not_result(self):
        self.archive('40153166007','1','2026/10/25',{'bad':b'ignored content'})
        self.archive('40637105507','1','2026/10/28',{'bad':b'ignored content'})
        result,api=self.collect()
        self.assertEqual(len(result),2)
        self.assertEqual(api.call_count,2)

    def test_current_archived_copy_omitted_only_after_byte_match(self):
        current=self.archive(self.cutoff['run_id'],'1','2026/10/28')
        result,api=self.collect()
        self.assertEqual(len(result),2)
        self.assertEqual(api.call_count,2)
        (current/'openliga-capture.tar.gz').write_bytes(gzip.compress(b'changed'))
        with self.assertRaisesRegex(existing.PreparationError,'CURRENT_CAPTURE_ARCHIVE_MISMATCH'):
            self.collect()

    def test_earlier_attempt_of_current_run_is_retained(self):
        self.archive(self.cutoff['run_id'],'1','2026/10/28')
        result,api=self.collect(attempt='2')
        self.assertEqual([r['reference']['attempt'] for r in result],['1','1','1'])
        self.assertEqual(len(result),3)

    def test_mandatory_baseline_cannot_disappear(self):
        for p in self.baseline.iterdir():p.unlink()
        self.baseline.rmdir()
        with self.assertRaisesRegex(existing.PreparationError,'CAPTURE_HISTORY_BASELINE_MISSING'):
            self.collect()

    def test_duplicate_run_attempt_in_two_days_is_ambiguous(self):
        self.archive('40258192078','1','2026/10/27')
        with self.assertRaisesRegex(existing.PreparationError,'AMBIGUOUS_CAPTURE_ARCHIVE'):
            self.collect()

    def test_limits_checked_before_reading_any_capture_or_metadata(self):
        module=self.module()
        with patch.object(module,'MAX_HISTORY_CAPTURES',1), \
             patch.object(module,'_read_gzip',side_effect=AssertionError('read before selection limit')), \
             patch.object(module.subprocess,'run',side_effect=AssertionError('API before limit')):
            with self.assertRaisesRegex(existing.PreparationError,'CAPTURE_HISTORY_COUNT_LIMIT'):
                module.collect(self.root,current_proof=self.current,**self.cutoff)

    def test_bad_gzip_and_decompression_overflow_reject_entire_history(self):
        path=self.later/'openliga-capture.tar.gz'
        path.write_bytes(b'not gzip')
        with self.assertRaisesRegex(existing.PreparationError,'INVALID_CAPTURE_GZIP'):
            self.collect()
        path.write_bytes(gzip.compress(b'x'*101))
        with patch.dict(self.module().FILE_LIMITS,{'openliga-capture.tar':100}):
            with self.assertRaisesRegex(existing.PreparationError,'DECODED_CAPTURE_SIZE_LIMIT'):
                self.collect()

    def test_missing_extra_and_non_json_bundle_reject(self):
        missing=self.later/'capture.sigstore.json.gz'
        missing.unlink()
        with self.assertRaises(existing.PreparationError):self.collect()
        missing.write_bytes(gzip.compress(b'{}'))
        (self.later/'audit.json').write_bytes(b'{}')
        with self.assertRaisesRegex(existing.PreparationError,'CAPTURE_ARCHIVE_FILE_ALLOWLIST'):
            self.collect()
        (self.later/'audit.json').unlink()
        missing.write_bytes(gzip.compress(b'{broken'))
        with self.assertRaises(existing.PreparationError):self.collect()

    def test_symlink_hardlink_fifo_and_ancestor_alias_rejected(self):
        path=self.later/'openliga-capture.tar.gz'
        original=path.read_bytes()
        outside=self.base/'outside'
        outside.write_bytes(original)
        for kind in ('symlink','hardlink','fifo'):
            path.unlink()
            if kind=='symlink':path.symlink_to(outside)
            elif kind=='hardlink':os.link(outside,path)
            else:os.mkfifo(path)
            with self.subTest(kind=kind),self.assertRaises(existing.PreparationError):self.collect()
        path.unlink();path.write_bytes(original)
        alias=self.base/'alias';alias.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(existing.PreparationError):
            self.module().collect(alias,current_proof=self.current,**self.cutoff)

    def test_invalid_run_path_future_day_and_invalid_cutoff_reject(self):
        invalid=self.root/'2026/10/28/not-a-run';invalid.mkdir(parents=True)
        with self.assertRaises(existing.PreparationError):self.collect()
        invalid.rmdir()
        future=self.root/'9999/01/01/99999999999-1';future.mkdir(parents=True)
        with self.assertRaises(existing.PreparationError):self.collect()
        for cutoff in ({'run_id':'1'},{'attempt':True},{'run_id':'../40258192078'}):
            with self.subTest(cutoff=cutoff),self.assertRaises(existing.PreparationError):self.collect(**cutoff)

    def test_metadata_wrong_identity_context_event_status_and_shape_reject(self):
        mutations=[{'workflow_id':1},{'event':'pull_request'},{'path':existing.WORKFLOW_PATH},
                   {'head_branch':'other'},{'status':'in_progress'},{'conclusion':'failure'},
                   {'head_sha':'bad'},{'id':True},{'run_attempt':2},
                   {'repository':{'id':1,'full_name':existing.REPOSITORY}},
                   {'head_repository':{'id':existing.REPOSITORY_ID,'full_name':'other/repo'}}]
        real=self.metadata
        for changes in mutations:
            def wrong(argv,**kwargs):
                cp=real(argv,**kwargs); value=json.loads(cp.stdout);value.update(changes)
                return subprocess.CompletedProcess(argv,0,json.dumps(value).encode(),b'')
            with self.subTest(changes=changes),patch.object(self.module().subprocess,'run',side_effect=wrong):
                with self.assertRaises(existing.PreparationError):
                    self.module().collect(self.root,current_proof=self.current,**self.cutoff)

    def test_failed_api_never_exposes_stderr_or_skips_history(self):
        with patch.object(self.module().subprocess,'run',return_value=subprocess.CompletedProcess([],1,b'',b'SECRET')):
            with self.assertRaisesRegex(existing.PreparationError,'CAPTURE_RUN_METADATA_API_REJECTED') as error:
                self.module().collect(self.root,current_proof=self.current,**self.cutoff)
        self.assertNotIn('SECRET',str(error.exception))

    def test_existing_files_and_original_bytes_remain_unchanged(self):
        before={p:p.read_bytes() for p in self.root.rglob('*.gz')}
        self.collect()
        self.assertEqual(before,{p:p.read_bytes() for p in before})
        self.assertEqual({p.name:p.read_bytes() for p in self.current.iterdir()},self.files)


if __name__=='__main__':unittest.main()
