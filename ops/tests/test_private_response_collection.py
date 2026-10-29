"""Reuse each original HTTP response; synthetic opener is never source proof."""
from datetime import datetime, timedelta, timezone
import importlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ops import odds_market as market
from ops import all_market_private_feed as feed

NOW=datetime(2026,10,28,8,tzinfo=timezone.utc)
KEY='synthetic-secret-only-never-real-key'
CONTEXT={'source_sha':'a'*40,'run_id':'40620390216','attempt':'1'}
PARAMS={'regions':'eu','markets':'h2h','oddsFormat':'decimal','dateFormat':'iso'}


class Response:
    status=200
    def __init__(self,raw,url,quota=None):
        self.raw,self.url=raw,url
        self.headers=quota or {'x-requests-used':'2','x-requests-remaining':'498','x-requests-last':'1'}
        self.reads=0
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,limit):self.reads+=1;return self.raw[:limit]
    def geturl(self):return self.url


class Spy:
    def __init__(self):self.records=[]
    def check_request(self,path,params):
        if params and 'apiKey' in params:raise ValueError('SECRET in rejected input')
    def record(self,raw,**kwargs):self.records.append((raw,kwargs))


class PrivateResponseCollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)

    def session(self):
        module=importlib.import_module('ops.private_response_capture')
        return module.CaptureSession(self.base/'private',**CONTEXT)

    def event(self):
        return {'id':'fixture-test','sport_key':'soccer_epl','home_team':'Home','away_team':'Away',
                'commence_time':(NOW+timedelta(hours=2)).isoformat(),
                'bookmakers':[{'key':'book-test','markets':[{'key':'h2h',
                    'last_update':(NOW-timedelta(minutes=1)).isoformat(),
                    'outcomes':[{'name':'Home','price':2.1},{'name':'Draw','price':3.3},
                                {'name':'Away','price':3.4}]}]}]}

    def clock(self):
        values=iter([NOW,NOW+timedelta(seconds=1),NOW+timedelta(seconds=90),
                     NOW+timedelta(seconds=91)])
        class Clock:
            @staticmethod
            def now(tz):return next(values)
        return Clock

    def collector_patches(self, opener):
        actual=market.retrieve
        def retrieve(path,key,**kwargs):
            kwargs['opener']=opener
            return actual(path,key,**kwargs)
        return patch.object(market,'retrieve',side_effect=retrieve),patch.object(feed,'retrieve',side_effect=retrieve)

    def test_retrieve_taps_exact_bytes_once_and_preserves_existing_return(self):
        raw=b' [ { "original" : 1 } ] \n';sink=Spy();responses=[]
        def opener(request,**kwargs):
            response=Response(raw,request.full_url);responses.append(response);return response
        with patch.object(market,'datetime',self.clock()):
            parsed,quota=market.retrieve('/sports/',KEY,opener=opener,capture=sink)
        self.assertEqual(parsed,[{'original':1}]);self.assertEqual(quota['remaining'],498)
        self.assertEqual(len(responses),1);self.assertEqual(responses[0].reads,1)
        self.assertEqual(sink.records[0][0],raw)
        self.assertEqual(sink.records[0][1]['requested'],NOW)
        self.assertEqual(sink.records[0][1]['completed'],NOW+timedelta(seconds=1))

    def test_capture_preflight_rejects_key_override_before_get(self):
        with patch.object(market,'urlopen') as network:
            with self.assertRaisesRegex(market.APIProblem,'PRIVATE_RESPONSE_CAPTURE_REJECTED'):
                market.retrieve('/sports/',KEY,opener=network,params={'apiKey':'other'},capture=Spy())
        network.assert_not_called()

    def test_redirect_never_records_or_reads_response_body(self):
        response=Response(b'[]','https://other.invalid/secret')
        sink=Spy()
        with self.assertRaisesRegex(market.APIProblem,'PRIVATE_RESPONSE_CAPTURE_REJECTED'):
            market.retrieve('/sports/',KEY,opener=lambda *a,**k:response,capture=sink)
        self.assertEqual(response.reads,0);self.assertEqual(sink.records,[])

    def test_sink_error_is_public_safe_without_retry(self):
        sink=Spy()
        def fail(*args,**kwargs):raise ValueError('SECRET '+KEY)
        sink.record=fail
        with self.assertRaisesRegex(market.APIProblem,'PRIVATE_RESPONSE_CAPTURE_REJECTED') as error:
            market.retrieve('/sports/',KEY,opener=lambda req,**kw:Response(b'[]',req.full_url),capture=sink)
        self.assertNotIn(KEY,str(error.exception));self.assertNotIn('SECRET',str(error.exception))
        with patch.object(feed,'verify',return_value={'quota':{'used':2,'remaining':498},
                'supported':{'epl':True,'championship':True},'active':{'epl':True,'championship':True}}), \
             patch.object(feed,'retrieve',side_effect=market.APIProblem('PRIVATE_RESPONSE_CAPTURE_REJECTED')) as getter:
            result=feed.collect(KEY,capture=sink)
        self.assertEqual(getter.call_count,1);self.assertEqual(result['collector_status'],'PROVIDER_ERROR')

    def test_offline_clock_cannot_be_presented_as_live_capture(self):
        with patch.object(feed,'verify') as getter:
            with self.assertRaisesRegex(ValueError,'OFFLINE_CLOCK_CANNOT_CAPTURE_RESPONSE'):
                feed.collect(KEY,now=NOW,capture=Spy())
        getter.assert_not_called()

    def test_raw_catalog_and_odds_rebuild_the_exact_original_quote_rows(self):
        session=self.session();bodies=[];responses=[]
        def opener(request,**kwargs):
            value=([{'key':'soccer_epl','active':True}] if '/sports/?' in request.full_url
                   else [self.event()])
            raw=(json.dumps(value,indent=1)+'  \n').encode();bodies.append(raw)
            response=Response(raw,request.full_url);responses.append(response);return response
        one,two=self.collector_patches(opener)
        with one,two,patch.object(market,'datetime',self.clock()):result=feed.collect(KEY,capture=session)
        sealed=session.seal()
        self.assertEqual(len(responses),2);self.assertTrue(all(r.reads==1 for r in responses))
        self.assertEqual(len(result['quotes']),3)
        self.assertTrue(all(q['captured_utc']==(NOW+timedelta(seconds=91)).isoformat() for q in result['quotes']))
        module=importlib.import_module('ops.private_response_capture')
        records=module.replay_records(self.base/'private',**CONTEXT,
                                     expected_manifest_sha256=sealed['manifest_sha256'])
        self.assertEqual([r['raw'] for r in records],bodies)
        with patch.object(market,'retrieve',side_effect=AssertionError('replay fetched a provider')):
            replay=feed.replay_private_quotes(self.base/'private',result,**CONTEXT,
                                              expected_manifest_sha256=sealed['manifest_sha256'])
        self.assertTrue(replay['replay_completed']);self.assertEqual(replay['odds_response_count'],1)
        self.assertEqual(replay['replayed_quote_count'],3);self.assertEqual(replay['certified_case_count'],0)
        for field,value in (('decimal_odds',result['quotes'][0]['decimal_odds']+.01),
                            ('line',False),('line',0.0),('decimal_odds',float('nan'))):
            changed=json.loads(json.dumps(result));changed['quotes'][0][field]=value
            with self.subTest(field=field,value=value), \
                 self.assertRaisesRegex(ValueError,'PRIVATE_CAPTURE_QUOTE_REPLAY_MISMATCH'):
                feed.replay_private_quotes(self.base/'private',changed,**CONTEXT,
                                           expected_manifest_sha256=sealed['manifest_sha256'])

    def test_quota_guard_replays_catalog_only_with_no_extra_odds_get(self):
        session=self.session();calls=[]
        def opener(request,**kwargs):
            calls.append(request.full_url)
            return Response(b'[{"key":"soccer_epl","active":true}]',request.full_url,
                            {'x-requests-used':'359','x-requests-remaining':'141','x-requests-last':'0'})
        one,two=self.collector_patches(opener)
        with one,two,patch.object(market,'datetime',self.clock()):result=feed.collect(KEY,capture=session)
        sealed=session.seal()
        replay=feed.replay_private_quotes(self.base/'private',result,**CONTEXT,
                                          expected_manifest_sha256=sealed['manifest_sha256'])
        self.assertEqual(len(calls),1);self.assertEqual(result['collector_status'],'QUOTA_GUARD')
        self.assertEqual(replay['odds_response_count'],0);self.assertEqual(replay['replayed_quote_count'],0)

    def test_sealed_bytes_are_readable_by_a_separate_process_with_no_network(self):
        session=self.session()
        raw=b'[ { "key" : "soccer_epl", "active" : true } ]  \n'
        session.record(raw,path='/sports/',params=None,quota={'used':359,'remaining':141,'last':0},
                       requested=NOW,completed=NOW+timedelta(seconds=1),secret=KEY)
        sealed=session.seal()
        argv=[sys.executable,'-B','-m','ops.private_response_capture','--private-dir',str(self.base/'private'),
              '--source-sha',CONTEXT['source_sha'],'--run-id',CONTEXT['run_id'],'--attempt','1',
              '--expected-manifest-sha256',sealed['manifest_sha256']]
        process=subprocess.run(argv,cwd=Path(__file__).resolve().parents[2],capture_output=True,timeout=10)
        self.assertEqual(process.returncode,0,process.stderr.decode())
        report=json.loads(process.stdout)
        self.assertTrue(report['replay_completed']);self.assertTrue(report['manifest_digest_pinned'])
        self.assertEqual(report['capture_count'],1)
        self.assertNotIn(KEY.encode(),process.stdout+process.stderr)
        module=importlib.import_module('ops.private_response_capture')
        records=module.replay_records(self.base/'private',**CONTEXT,
                                     expected_manifest_sha256=sealed['manifest_sha256'])
        self.assertEqual(records[0]['raw'],raw)

    def test_main_publishes_only_a_manifest_pin_not_raw_payload_to_outputs(self):
        module=importlib.import_module('ops.private_response_capture')
        outputs=self.base/'github-output';cwd=Path.cwd();os.chdir(self.base)
        self.addCleanup(os.chdir,cwd)
        def opener(request,**kwargs):return Response(b'[]',request.full_url)
        one,two=self.collector_patches(opener)
        env={'THE_ODDS_API_KEY':KEY,'PRIVATE_RESPONSE_CAPTURE_DIR':str(self.base/'private'),
             'GITHUB_SHA':CONTEXT['source_sha'],'GITHUB_RUN_ID':CONTEXT['run_id'],
             'GITHUB_RUN_ATTEMPT':'1','GITHUB_OUTPUT':str(outputs)}
        with patch.dict(os.environ,env),one,two,patch.object(market,'datetime',self.clock()), \
             patch('sys.stdout',new_callable=io.StringIO) as stdout:
            feed.main()
        text=outputs.read_text();self.assertRegex(text,r'^private_capture_manifest_sha256=[0-9a-f]{64}\n$')
        self.assertNotIn(KEY,text+stdout.getvalue())
        report=module.replay(self.base/'private',**CONTEXT,
            expected_manifest_sha256=text.strip().split('=',1)[1])
        self.assertEqual(report['capture_count'],1)

    def test_live_workflow_keeps_raw_pack_out_of_public_uploads(self):
        root=Path(__file__).resolve().parents[2]
        text=(root/'.github/workflows/private-all-market-research.yml').read_text()
        job=text.split('  collect:\n',1)[1].split('\n  archive_redacted_coverage:',1)[0]
        setting='PRIVATE_RESPONSE_CAPTURE_DIR: ${{ runner.temp }}/football-private-responses'
        self.assertNotIn('runner.temp',job.split('    steps:',1)[0])
        self.assertEqual(job.count(setting),2)
        steps=re.split(r'^      - ',job,flags=re.M)
        for marker in ('id: collect_private','name: Replay original response bytes privately'):
            step=next(s for s in steps if marker in s)
            self.assertIn('        env:\n',step)
            self.assertIn('          '+setting,step)
        uploads=[s for s in steps if 'uses: actions/upload-artifact@' in s]
        self.assertEqual(len(uploads),3)
        block=re.search(r'          path: \|\n((?:            .+\n)+)',uploads[0])
        self.assertIsNotNone(block)
        self.assertEqual({line.strip() for line in block.group(1).splitlines()},
                         {'output/private_all_market_public_summary.json','output/recommendation_readiness.json'})
        self.assertNotIn('actions/cache@',job)
        self.assertIn('--expected-manifest-sha256 "$PRIVATE_CAPTURE_MANIFEST_SHA"',job)
        self.assertIn("replay_private_quotes(Path(os.environ['PRIVATE_RESPONSE_CAPTURE_DIR']), feed,",job)

    def test_main_closes_session_when_sealing_fails_without_leaking_error(self):
        cwd=Path.cwd();os.chdir(self.base);self.addCleanup(os.chdir,cwd)
        fake=Spy();fake.seal=lambda:(_ for _ in ()).throw(ValueError('SECRET '+KEY))
        fake.close=lambda:setattr(fake,'closed',True)
        env={'THE_ODDS_API_KEY':KEY,'PRIVATE_RESPONSE_CAPTURE_DIR':str(self.base/'private'),
             'GITHUB_SHA':CONTEXT['source_sha'],'GITHUB_RUN_ID':CONTEXT['run_id'],
             'GITHUB_RUN_ATTEMPT':'1'}
        with patch.dict(os.environ,env),patch('ops.private_response_capture.CaptureSession',return_value=fake), \
             patch.object(feed,'collect',return_value={'quotes':[]}), \
             patch('sys.stdout',new_callable=io.StringIO) as stdout:
            feed.main()
        self.assertTrue(fake.closed)
        report=json.loads(Path('output/private_all_market_quotes.json').read_text())
        self.assertEqual(report['collector_status'],'PROVIDER_ERROR')
        self.assertEqual(report['collector_reason'],'PRIVATE_CAPTURE_FINALIZATION_FAILED')
        self.assertNotIn(KEY,json.dumps(report)+stdout.getvalue())


if __name__=='__main__':unittest.main()
