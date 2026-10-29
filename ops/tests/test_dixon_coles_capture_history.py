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
        endpoint=argv[-1].split('?',1)[0].split('/')
        jobs=endpoint[-1]=='jobs'
        run,attempt=(endpoint[-4],endpoint[-2]) if jobs else (endpoint[-3],endpoint[-1])
        value={'id':int(run),'run_attempt':int(attempt),'workflow_id':383990991,
               'head_branch':'main','path':'.github/workflows/four-model-shadow-daily.yml',
               'event':'schedule','status':'completed','conclusion':'success',
               'head_sha':format(int(run),'040x')}
        for key in ('repository','head_repository'):
            value[key]={'id':existing.REPOSITORY_ID,'full_name':existing.REPOSITORY}
        if jobs:
            names=('shadow-daily','attest_openliga_capture','verify_openliga_capture',
                   'archive_openliga_capture')
            value={'total_count':4,'jobs':[
                {'id':index+1,'run_id':int(run),'run_attempt':int(attempt),
                 'head_sha':value['head_sha'],'head_branch':'main',
                 'run_url':'https://api.github.com/repos/'+existing.REPOSITORY+'/actions/runs/'+run,
                 'name':name,'status':'completed','conclusion':'success'}
                for index,name in enumerate(names)]}
        return subprocess.CompletedProcess(argv,0,json.dumps(value).encode(),b'')

    def changed_metadata(self, change, *, jobs):
        def changed(argv, **kwargs):
            result=self.metadata(argv,**kwargs)
            if ('/jobs?' in argv[-1]) == jobs:
                value=json.loads(result.stdout)
                change(value)
                return subprocess.CompletedProcess(argv,0,json.dumps(value).encode(),b'')
            return result
        return changed

    def reject_metadata(self, response, reason=None):
        with patch.object(self.module().subprocess,'run',side_effect=response):
            with self.assertRaisesRegex(existing.PreparationError,reason or '.'):
                self.module().collect(self.root,current_proof=self.current,**self.cutoff)

    def collect(self, **changes):
        with patch.object(self.module().subprocess,'run',side_effect=self.metadata) as api:
            result=self.module().collect(self.root,current_proof=self.current,
                                         **dict(self.cutoff,**changes))
        return result,api

    def test_all_history_retained_in_run_order_without_decoding_tar_as_json(self):
        result,api=self.collect()
        self.assertEqual([r['reference']['run_id'] for r in result],['40258192078','40437105506'])
        self.assertEqual(api.call_count,4)
        expected=[]
        for run in ('40258192078','40437105506'):
            endpoint='repos/'+existing.REPOSITORY+'/actions/runs/'+run+'/attempts/1'
            expected.extend((endpoint,endpoint+'/jobs?per_page=100&page=1'))
        self.assertEqual([call.args[0] for call in api.call_args_list],
                         [['gh','api',endpoint] for endpoint in expected])
        for call in api.call_args_list:
            self.assertEqual(call.kwargs,{'capture_output':True,'timeout':30,'check':False})
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
        self.assertEqual(api.call_count,4)

    def test_current_archived_copy_omitted_only_after_byte_match(self):
        current=self.archive(self.cutoff['run_id'],'1','2026/10/28')
        result,api=self.collect()
        self.assertEqual(len(result),2)
        self.assertEqual(api.call_count,4)
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
                   {'head_branch':'other'},{'status':'in_progress'},{'conclusion':'cancelled'},
                   {'conclusion':'timed_out'},{'conclusion':'neutral'},{'conclusion':None},
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

    def test_failed_parent_with_successful_producers_retains_every_capture(self):
        def response(argv,**kwargs):
            cp=self.metadata(argv,**kwargs); value=json.loads(cp.stdout)
            if '/jobs?' in argv[-1]:
                child=dict(value['jobs'][0],id=5,name='controlled-case-intake',conclusion='failure')
                value['jobs'].append(child);value['total_count']=5
            else:
                value['conclusion']='failure'
            return subprocess.CompletedProcess(argv,0,json.dumps(value).encode(),b'')
        with patch.object(self.module().subprocess,'run',side_effect=response) as api:
            result=self.module().collect(self.root,current_proof=self.current,**self.cutoff)
        self.assertEqual(api.call_count,4)
        self.assertEqual([r['reference']['run_id'] for r in result],['40258192078','40437105506'])
        self.assertTrue(all(row['files']==self.files for row in result))

    def test_successful_parent_still_requires_each_successful_producer(self):
        for index in range(4):
            for change in ({'status':'queued'},{'status':'in_progress'},
                           {'conclusion':'failure'},{'conclusion':'cancelled'},
                           {'conclusion':'timed_out'},{'conclusion':'skipped'},
                           {'conclusion':None},{'status':None}):
                def mutate(value):value['jobs'][index].update(change)
                with self.subTest(producer=index,change=change):
                    self.reject_metadata(self.changed_metadata(mutate,jobs=True),
                                         'UNSUCCESSFUL_CAPTURE_PRODUCER_JOB')

    def test_failed_parent_cannot_hide_a_failed_producer(self):
        for index in range(4):
            def response(argv,**kwargs):
                cp=self.metadata(argv,**kwargs);value=json.loads(cp.stdout)
                if '/jobs?' in argv[-1]:value['jobs'][index]['conclusion']='failure'
                else:value['conclusion']='failure'
                return subprocess.CompletedProcess(argv,0,json.dumps(value).encode(),b'')
            with self.subTest(producer=index):
                self.reject_metadata(response,'UNSUCCESSFUL_CAPTURE_PRODUCER_JOB')

    def test_missing_duplicate_or_renamed_producer_rejects_complete_history(self):
        for index in range(4):
            for action in ('missing','duplicate','renamed'):
                def mutate(value):
                    if action=='missing':value['jobs'].pop(index)
                    elif action=='duplicate':
                        value['jobs'].append(dict(value['jobs'][index],id=10))
                    else:value['jobs'][index]['name']+='-other'
                    value['total_count']=len(value['jobs'])
                with self.subTest(producer=index,action=action):
                    self.reject_metadata(self.changed_metadata(mutate,jobs=True),
                                         'AMBIGUOUS_OR_MISSING_CAPTURE_PRODUCER_JOBS')

    def test_job_identity_context_and_types_reject(self):
        changes=({'id':True},{'id':0},{'id':-1},{'id':'1'},
                 {'run_id':True},{'run_id':1},{'run_id':'40258192078'},
                 {'run_attempt':True},{'run_attempt':2},{'run_attempt':'1'},
                 {'head_sha':'0'*40},{'head_sha':None},{'head_branch':'other'},
                 {'run_url':'https://api.github.com/repos/other/repo/actions/runs/40258192078'},
                 {'run_url':'https://api.github.com/repos/'+existing.REPOSITORY+'/actions/runs/1'},
                 {'name':None},{'name':[]})
        for change in changes:
            def mutate(value):value['jobs'][0].update(change)
            with self.subTest(change=change):
                self.reject_metadata(self.changed_metadata(mutate,jobs=True))
        def duplicate(value):value['jobs'][1]['id']=value['jobs'][0]['id']
        self.reject_metadata(self.changed_metadata(duplicate,jobs=True),'DUPLICATE_CAPTURE_JOB_ID')

    def test_all_job_rows_are_bound_even_when_unrelated(self):
        def mutate(value):
            value['jobs'].append(dict(value['jobs'][0],id=5,name='unrelated',run_attempt=2))
            value['total_count']=5
        self.reject_metadata(self.changed_metadata(mutate,jobs=True),'CAPTURE_JOB_CONTEXT_MISMATCH')

    def test_job_list_count_shape_and_completeness_reject(self):
        changes=({'total_count':True},{'total_count':0},{'total_count':-1},
                 {'total_count':3},{'total_count':5},{'total_count':101},
                 {'total_count':'4'},{'jobs':None},{'jobs':{}},{'jobs':[]},
                 {'jobs':[None]*4})
        for change in changes:
            with self.subTest(change=change):
                self.reject_metadata(self.changed_metadata(lambda value:value.update(change),jobs=True))
        def truncated(value):
            value['jobs']=[dict(value['jobs'][0],id=i+1) for i in range(100)]
            value['total_count']=101
        self.reject_metadata(self.changed_metadata(truncated,jobs=True),'INVALID_CAPTURE_JOB_LIST')

    def test_complete_job_limit_with_unrelated_failures_is_accepted(self):
        def mutate(value):
            template=value['jobs'][0]
            value['jobs'].extend(dict(template,id=i,name='unrelated-'+str(i),conclusion='failure')
                                 for i in range(5,101))
            value['total_count']=100
        with patch.object(self.module().subprocess,'run',
                          side_effect=self.changed_metadata(mutate,jobs=True)) as api:
            result=self.module().collect(self.root,current_proof=self.current,**self.cutoff)
        self.assertEqual(len(result),2)
        self.assertEqual(api.call_count,4)

    def test_missing_parent_and_job_status_fields_reject(self):
        for jobs,fields in ((False,('status','conclusion')),
                           (True,('id','run_id','run_attempt','head_sha','head_branch','run_url',
                                  'name','status','conclusion'))):
            for field in fields:
                def mutate(value):
                    target=value['jobs'][0] if jobs else value
                    target.pop(field)
                with self.subTest(jobs=jobs,field=field):
                    self.reject_metadata(self.changed_metadata(mutate,jobs=jobs))

    def test_jobs_api_error_timeout_invalid_or_oversized_response_rejects(self):
        replies=(subprocess.CompletedProcess([],1,b'',b'SECRET'),
                 subprocess.CompletedProcess([],0,b'not JSON',b'SECRET'),
                 subprocess.CompletedProcess([],0,b'[]',b'SECRET'),
                 subprocess.CompletedProcess([],0,b'{"total_count":4,"total_count":4,"jobs":[]}',b'SECRET'),
                 subprocess.CompletedProcess([],0,b'',b'SECRET'),
                 subprocess.CompletedProcess([],0,'text instead of bytes',b'SECRET'),
                 subprocess.CompletedProcess([],0,b'x'*(existing.MAX_API_BYTES+1),b'SECRET'),
                 subprocess.TimeoutExpired(['gh','SECRET'],30,stderr=b'SECRET'),
                 OSError('SECRET'))
        for reply in replies:
            def response(argv,**kwargs):
                if '/jobs?' in argv[-1]:
                    if isinstance(reply,BaseException):raise reply
                    return reply
                return self.metadata(argv,**kwargs)
            with self.subTest(reply=type(reply).__name__), \
                 patch.object(self.module().subprocess,'run',side_effect=response):
                with self.assertRaises(existing.PreparationError) as error:
                    self.module().collect(self.root,current_proof=self.current,**self.cutoff)
                self.assertNotIn('SECRET',str(error.exception))

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
