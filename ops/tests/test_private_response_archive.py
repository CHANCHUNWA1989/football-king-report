"""Synthetic HTTP GitHub transport; never provider truth or real credentials."""
import base64
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import tempfile
import textwrap
import unittest
import warnings
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit
import zipfile

from ops.private_response_capture import CaptureSession, replay_records

CONTEXT={'source_sha':'a'*40,'run_id':'101','attempt':'1'}
TOKEN='synthetic-archive-token-never-real-123'
ENV={'PRIVATE_ARCHIVE_REPOSITORY':'SyntheticOwner/private-football',
     'PRIVATE_ARCHIVE_REPOSITORY_ID':'12345','PRIVATE_ARCHIVE_TOKEN':TOKEN}


def blob_sha(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()


class Response(io.BytesIO):
    def __init__(self,raw,url,status=200):
        super().__init__(raw);self.url=url;self.status=status
    def geturl(self):return self.url


class FakeGitHub:
    def __init__(self):
        self.calls=[];self.archive=None;self.commit='d'*40
        self.repo={'id':12345,'full_name':ENV['PRIVATE_ARCHIVE_REPOSITORY'],
                   'private':True,'visibility':'private','archived':False,
                   'disabled':False,'default_branch':'main'}
        self.metadata_reads=0;self.public_on_read=None;self.wrong_blob=False
        self.wrong_reachability=False;self.empty_branch=False;self.redirect=False
        self.fail_write=False

    def __call__(self,request,**kwargs):
        self.calls.append(request)
        self.assert_safe(request)
        method=request.get_method();path=urlsplit(request.full_url).path
        if self.redirect:
            return Response(b'{}','https://other.invalid/redirect',302)
        if path=='/repos/'+ENV['PRIVATE_ARCHIVE_REPOSITORY']:
            self.metadata_reads+=1
            data=dict(self.repo)
            if self.metadata_reads==self.public_on_read:
                data.update(private=False,visibility='public')
        elif '/git/ref/heads/' in path:
            if self.empty_branch:
                raise HTTPError(request.full_url,404,'SECRET '+TOKEN,{},io.BytesIO(TOKEN.encode()))
            data={'ref':'refs/heads/main','object':{'type':'commit','sha':'f'*40}}
        elif '/contents/' in path and method=='PUT':
            payload=json.loads(request.data)
            if self.fail_write or self.archive is not None:
                raise HTTPError(request.full_url,422,'SECRET '+TOKEN,{},io.BytesIO(TOKEN.encode()))
            assert set(payload)=={'message','content','branch'}
            assert payload['branch']=='main'
            self.archive=base64.b64decode(payload['content'],validate=True)
            data={'content':{'sha':blob_sha(self.archive)},'commit':{'sha':self.commit}}
            return Response(json.dumps(data).encode(),request.full_url,201)
        elif '/contents/' in path:
            assert request.full_url.endswith('?ref='+self.commit)
            data={'type':'file','path':path.split('/contents/',1)[1],
                  'sha':'0'*40 if self.wrong_reachability else blob_sha(self.archive),
                  'size':len(self.archive),'encoding':'none','content':''}
        elif '/git/blobs/' in path:
            raw=self.archive[:-1]+bytes([self.archive[-1]^1]) if self.wrong_blob else self.archive
            data={'sha':blob_sha(self.archive),'size':len(raw),'encoding':'base64',
                  'content':'\n'.join(textwrap.wrap(base64.b64encode(raw).decode(),60))+'\n'}
        else:
            raise AssertionError('unexpected synthetic endpoint')
        return Response(json.dumps(data).encode(),request.full_url)

    def assert_safe(self,request):
        assert request.full_url.startswith('https://api.github.com/repos/')
        assert TOKEN not in request.full_url
        assert request.get_header('Authorization')=='Bearer '+TOKEN


class PrivateResponseArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.source=self.base/'source';self.dest=self.base/'restored'
        self.raw=b' [ { "key" : "soccer_epl", "active" : true } ] \n'
        now=datetime(2026,10,28,8,tzinfo=timezone.utc)
        session=CaptureSession(self.source,**CONTEXT)
        session.record(self.raw,path='/sports/',quota={'used':359,'remaining':141,'last':0},
                       requested=now,completed=now+timedelta(seconds=1),secret='synthetic-provider-key')
        self.pin=session.seal()['manifest_sha256']
        self.api=FakeGitHub()

    def module(self):return importlib.import_module('ops.private_response_archive')
    def config(self):return self.module().configuration(ENV,required=True)
    def upload(self):
        return self.module().upload(self.source,**CONTEXT,expected_manifest_sha256=self.pin,
                                    config=self.config(),opener=self.api)
    def restore(self,report=None,**changes):
        report=report or self.upload()
        args=dict(CONTEXT,expected_manifest_sha256=self.pin,
                  expected_blob_sha=report['archive_blob_sha'],expected_commit_sha=report['archive_commit_sha'],
                  expected_archive_sha256=report['archive_sha256'],config=self.config(),opener=self.api)
        args.update(changes)
        return self.module().restore(self.dest,**args)

    def test_create_only_upload_and_separate_root_restore_keep_exact_bytes(self):
        report=self.upload();restored=self.restore(report)
        self.assertTrue(report['remote_roundtrip_completed']);self.assertTrue(restored['remote_roundtrip_completed'])
        self.assertEqual(restored['capture_count'],1)
        self.assertFalse(restored['raw_source_authenticated']);self.assertFalse(restored['durable_archive_verified'])
        self.assertEqual(restored['production_recommendations'],'DISABLED')
        self.assertEqual(replay_records(self.dest,**CONTEXT,expected_manifest_sha256=self.pin)[0]['raw'],self.raw)
        self.assertEqual({p.name:p.read_bytes() for p in self.source.iterdir()},
                         {p.name:p.read_bytes() for p in self.dest.iterdir()})
        self.assertEqual(self.dest.stat().st_mode&0o777,0o700)
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in self.dest.iterdir()))
        puts=[r for r in self.api.calls if r.get_method()=='PUT']
        self.assertEqual(len(puts),1);self.assertNotIn('sha',json.loads(puts[0].data))
        self.assertEqual(report['archive_blob_sha'],blob_sha(self.api.archive))
        self.assertNotIn(ENV['PRIVATE_ARCHIVE_REPOSITORY'],json.dumps(report))
        self.assertNotIn(TOKEN,json.dumps(report)+json.dumps(restored))

    def test_wrong_identity_public_internal_and_uninitialized_repo_never_write(self):
        for changes in ({'id':12346},{'id':True},{'private':False,'visibility':'public'},
                        {'visibility':'internal'},{'full_name':'Other/Private'},{'archived':True}):
            self.api=FakeGitHub();self.api.repo.update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.upload()
            self.assertFalse(any(r.get_method()=='PUT' for r in self.api.calls))
        self.api=FakeGitHub();self.api.empty_branch=True
        with self.assertRaises(ValueError):self.upload()
        self.assertFalse(any(r.get_method()=='PUT' for r in self.api.calls))

    def test_observed_privacy_change_rejected_before_write_and_after_readback(self):
        self.api.public_on_read=2
        with self.assertRaises(ValueError):self.upload()
        self.assertIsNone(self.api.archive)
        self.api=FakeGitHub();self.api.public_on_read=3
        with self.assertRaises(ValueError):self.upload()
        self.assertIsNotNone(self.api.archive)

    def test_existing_remote_path_is_not_retried_or_overwritten(self):
        self.upload();original=self.api.archive;before=len(self.api.calls)
        with self.assertRaisesRegex(ValueError,'^PRIVATE_ARCHIVE_HTTP_REJECTED$') as error:self.upload()
        self.assertNotIn(TOKEN,str(error.exception))
        self.assertEqual(self.api.archive,original)
        self.assertEqual(sum(r.get_method()=='PUT' for r in self.api.calls[before:]),1)

    def test_pin_tamper_unsafe_source_and_token_echo_reject_before_network(self):
        (self.source/'capture-000.body.json').write_bytes(self.raw+b' ')
        with self.assertRaises(ValueError):self.upload()
        self.assertEqual(self.api.calls,[])

    def test_archive_token_literal_json_escape_and_url_encoding_reject_before_network(self):
        encoded=''.join('%%%02x'%ord(c) for c in TOKEN)
        escaped=''.join('\\u%04x'%ord(c) for c in TOKEN)
        now=datetime(2026,10,28,8,tzinfo=timezone.utc)
        cases=(json.dumps([{'debug':TOKEN}]).encode(),
               ('[{"debug":"'+escaped+'"}]').encode(),
               json.dumps([{'debug':'https://example.invalid/?token='+encoded}]).encode())
        for index,raw in enumerate(cases):
            self.source=self.base/('token-source-'+str(index))
            session=CaptureSession(self.source,**CONTEXT)
            session.record(raw,path='/sports/',quota={'used':359,'remaining':141,'last':0},
                           requested=now,completed=now,secret='synthetic-provider-key')
            self.pin=session.seal()['manifest_sha256']
            with self.subTest(case=index),self.assertRaises(ValueError) as error:self.upload()
            self.assertNotIn(TOKEN,str(error.exception));self.assertEqual(self.api.calls,[])

    def test_seven_response_pack_is_deterministic_and_has_exact_fifteen_members(self):
        self.source=self.base/'seven-source'
        now=datetime(2026,10,28,8,tzinfo=timezone.utc)
        session=CaptureSession(self.source,**CONTEXT)
        for _ in range(7):
            session.record(self.raw,path='/sports/',quota={'used':359,'remaining':141,'last':0},
                           requested=now,completed=now,secret='synthetic-provider-key')
        self.pin=session.seal()['manifest_sha256']
        first=self.upload();raw=self.api.archive
        self.api=FakeGitHub();second=self.upload()
        self.assertEqual(first['archive_sha256'],second['archive_sha256'])
        self.assertEqual(raw,self.api.archive)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertEqual(len(archive.namelist()),15)
        self.assertEqual(self.restore(second)['capture_count'],7)

    def test_readback_wrong_blob_or_commit_reachability_rejects(self):
        for flag,code in (('wrong_blob','PRIVATE_ARCHIVE_BLOB_DIGEST_MISMATCH'),
                          ('wrong_reachability','PRIVATE_ARCHIVE_COMMIT_REACHABILITY_REJECTED')):
            self.api=FakeGitHub();setattr(self.api,flag,True)
            with self.subTest(flag=flag),self.assertRaisesRegex(ValueError,'^'+code+'$'):self.upload()

    def test_restore_bad_context_digest_and_existing_destination_reject(self):
        report=self.upload()
        for changes in ({'expected_archive_sha256':'0'*64},{'expected_blob_sha':'0'*40},
                        {'run_id':'102'},{'expected_manifest_sha256':'0'*64}):
            self.dest=self.base/('bad-'+str(len(list(self.base.iterdir()))))
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.restore(report,**changes)
        self.dest=self.source
        calls_before=len(self.api.calls)
        with self.assertRaises(ValueError):self.restore(report)
        self.assertEqual(len(self.api.calls),calls_before)
        self.assertEqual((self.source/'capture-000.body.json').read_bytes(),self.raw)

    def test_restore_symlink_parent_and_non_private_location_are_rejected_without_get(self):
        report=self.upload();real=self.base/'real';real.mkdir();alias=self.base/'alias';alias.symlink_to(real)
        self.dest=alias/'pack';before=len(self.api.calls)
        with self.assertRaises(ValueError):self.restore(report)
        self.assertEqual(len(self.api.calls),before);self.assertEqual(list(real.iterdir()),[])
        repo=self.base/'repository';repo.mkdir();(repo/'.git').mkdir()
        self.dest=repo/'pack'
        with self.assertRaises(ValueError):self.restore(report)
        self.assertEqual(len(self.api.calls),before)

    def test_zip_compression_traversal_duplicate_or_extra_entries_rejected(self):
        report=self.upload()
        with zipfile.ZipFile(io.BytesIO(self.api.archive)) as z:
            infos=copy.deepcopy(z.infolist())
            files={info.filename:z.read(info) for info in infos}
        def rebuild(kind=None):
            data=io.BytesIO()
            with warnings.catch_warnings():
                warnings.simplefilter('ignore',UserWarning)
                with zipfile.ZipFile(data,'w',compression=zipfile.ZIP_STORED,allowZip64=False) as z:
                    for original in infos:
                        info=copy.deepcopy(original)
                        if kind=='compression':info.compress_type=zipfile.ZIP_DEFLATED
                        z.writestr(info,files[original.filename])
                    if kind in ('traversal','duplicate','extra'):
                        info=copy.deepcopy(next(info for info in infos if info.filename=='manifest.json'))
                        info.filename={'traversal':'../outside','duplicate':'manifest.json','extra':'extra'}[kind]
                        z.writestr(info,files['manifest.json'])
            return data.getvalue()
        baseline=rebuild()
        self.assertEqual(baseline,self.api.archive)
        self.assertEqual(self.restore(report)['capture_count'],1)
        for kind in ('compression','traversal','duplicate','extra'):
            self.api.archive=rebuild(kind);self.dest=self.base/('badzip-'+kind)
            changed=dict(report,archive_blob_sha=blob_sha(self.api.archive),
                         archive_sha256=hashlib.sha256(self.api.archive).hexdigest())
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.restore(changed)
            self.assertFalse((self.base/'outside').exists())

    def test_redirect_response_never_uploads_or_exposes_error(self):
        self.api.redirect=True
        with self.assertRaises(ValueError) as error:self.upload()
        self.assertNotIn(TOKEN,str(error.exception));self.assertNotIn('SyntheticOwner',str(error.exception))
        self.assertEqual(len(self.api.calls),1)

    def test_redirect_handler_closes_original_response_before_any_follow(self):
        response=io.BytesIO(b'ignored secret response')
        with self.assertRaisesRegex(ValueError,'^PRIVATE_ARCHIVE_REDIRECT_REJECTED$'):
            self.module()._NoRedirect().redirect_request(None,response,302,'moved',{},'https://other.invalid/')
        self.assertTrue(response.closed)

    def test_malformed_configuration_never_produces_a_client_request(self):
        for changes in ({'PRIVATE_ARCHIVE_REPOSITORY':'owner/../bad'},
                        {'PRIVATE_ARCHIVE_REPOSITORY_ID':'001'},
                        {'PRIVATE_ARCHIVE_REPOSITORY_ID':'True'},
                        {'PRIVATE_ARCHIVE_TOKEN':TOKEN+'\nheader: injected'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.module().configuration(dict(ENV,**changes),required=True)
        for repository,identity,token in (('owner/../../bad',12345,TOKEN),
                                          (ENV['PRIVATE_ARCHIVE_REPOSITORY'],True,TOKEN),
                                          ('Owner/'+TOKEN,12345,TOKEN)):
            with self.assertRaises(ValueError):self.module().Configuration(repository,identity,token)
        self.assertEqual(self.api.calls,[])

    def test_token_echoed_as_branch_cannot_enter_any_request_url(self):
        self.api.repo['default_branch']=TOKEN
        with self.assertRaisesRegex(ValueError,'^PRIVATE_ARCHIVE_REQUEST_REJECTED$'):self.upload()
        self.assertEqual(len(self.api.calls),1)
        self.assertTrue(all(TOKEN not in request.full_url for request in self.api.calls))

    def test_config_absent_partial_and_cli_safe_output(self):
        module=self.module()
        argv=['upload','--private-dir',str(self.source),'--source-sha',CONTEXT['source_sha'],
              '--run-id','101','--attempt','1','--expected-manifest-sha256',self.pin]
        for env,expected in (({},0),({'PRIVATE_ARCHIVE_TOKEN':TOKEN},1)):
            with patch.dict(os.environ,env,clear=True),patch('sys.stdout',new_callable=io.StringIO) as out:
                self.assertEqual(module.main(argv),expected)
            self.assertNotIn(TOKEN,out.getvalue());self.assertNotIn(str(self.source),out.getvalue())
            if not env:self.assertEqual(json.loads(out.getvalue())['archive_status'],'NOT_CONFIGURED')
        output=self.base/'github-output'
        with patch.dict(os.environ,dict(ENV,GITHUB_OUTPUT=str(output)),clear=True), \
             patch.object(module,'default_opener',return_value=self.api), \
             patch('sys.stdout',new_callable=io.StringIO) as out:
            self.assertEqual(module.main(argv),0)
        lines=output.read_text().splitlines()
        self.assertEqual({line.split('=',1)[0] for line in lines},
                         {'private_archive_blob_sha','private_archive_commit_sha','private_archive_sha256'})
        self.assertNotIn(TOKEN,out.getvalue()+output.read_text())
        self.assertNotIn(ENV['PRIVATE_ARCHIVE_REPOSITORY'],out.getvalue()+output.read_text())


if __name__=='__main__':unittest.main()
