"""Private synthetic bytes only; successful replay never certifies a provider."""
import copy
from datetime import datetime, timedelta, timezone
import importlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class PrivateResponseCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.root=self.base/'private-pack'
        self.context={'source_sha':'a'*40,'run_id':'101','attempt':'1'}
        self.start=datetime(2026,10,28,1,tzinfo=timezone.utc)
        self.options={'path':'/sports/','params':None,
                      'quota':{'used':10,'remaining':490,'last':0},
                      'requested':self.start,'completed':self.start+timedelta(seconds=1),
                      'secret':'SECRET_NOT_FOR_STORAGE_123'}
        self.raw=b'[ {"key":"soccer_epl", "active": true} ]\n'

    def module(self):
        return importlib.import_module('ops.private_response_capture')

    def session(self):
        s=self.module().CaptureSession(self.root,**self.context)
        self.addCleanup(s.close)
        return s

    def make_pack(self):
        s=self.session();receipt=s.record(self.raw,**self.options);summary=s.seal()
        return receipt,summary

    def test_original_whitespace_bytes_roundtrip_and_private_modes(self):
        s=self.session();self.assertIsNone(s.last_receipt)
        receipt=s.record(self.raw,**self.options)
        self.assertEqual(s.last_receipt,receipt)
        changed=copy.deepcopy(s.last_receipt);changed['quota']['used']=999
        self.assertNotEqual(s.last_receipt,changed)
        self.assertEqual((self.root/receipt['raw_file']).read_bytes(),self.raw)
        summary=s.seal()
        restored=self.module().replay_records(self.root,**self.context,
                            expected_manifest_sha256=summary['manifest_sha256'])
        self.assertEqual(restored,[{'receipt':receipt,'raw':self.raw}])
        report=self.module().replay(self.root,**self.context,
                            expected_manifest_sha256=summary['manifest_sha256'])
        self.assertEqual(report['capture_count'],1)
        self.assertTrue(report['pack_sealed']);self.assertTrue(report['replay_completed'])
        self.assertTrue(report['manifest_digest_pinned'])
        self.assertFalse(report['raw_source_authenticated'])
        self.assertFalse(report['durable_archive_verified'])
        self.assertEqual(report['production_recommendations'],'DISABLED')
        self.assertEqual(self.root.stat().st_mode&0o777,0o700)
        for p in self.root.iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)

    def test_request_whitelist_preflight_and_record_recheck(self):
        s=self.session()
        valid={'regions':'eu','markets':'h2h','oddsFormat':'decimal','dateFormat':'iso'}
        s.check_request('/sports/',None)
        detached=s.check_request('/sports/soccer_epl/odds/',valid)
        self.assertEqual(detached,valid);self.assertIsNot(detached,valid)
        cases=[('/sports/?apiKey=x',None),('/sports/unknown/odds/',valid),
               ('https://api.the-odds-api.com/v4/sports/',None),
               ('/sports/',{'markets':'h2h'}),('/sports/soccer_epl/odds/',None),
               ('/sports/soccer_epl/odds/',dict(valid,markets='spreads')),
               ('/sports/soccer_epl/odds/',dict(valid,apiKey='SECRET'))]
        for path,params in cases:
            with self.subTest(path=path,params=params),self.assertRaises(ValueError):
                s.check_request(path,params)
            with self.assertRaises(ValueError):
                s.record(self.raw,**dict(self.options,path=path,params=params))
        self.assertEqual(list(self.root.iterdir()),[])

    def test_secret_rejected_in_raw_and_decoded_keys_or_values(self):
        s=self.session();secret=self.options['secret']
        escaped=''.join('\\u%04x'%ord(c) for c in secret)
        for raw in (json.dumps([secret]).encode(),('["'+escaped+'"]').encode(),
                    ('[{"'+escaped+'":0}]').encode()):
            with self.assertRaises(ValueError) as error:s.record(raw,**self.options)
            self.assertNotIn(secret,str(error.exception))
            self.assertEqual(list(self.root.iterdir()),[])
        # A misconfigured context cannot put the supplied secret in a receipt.
        with self.assertRaises(ValueError):
            s.record(self.raw,**dict(self.options,secret=self.context['source_sha']))
        self.assertEqual(list(self.root.iterdir()),[])

    def test_percent_encoded_secret_keys_and_values_reject_before_writes(self):
        s=self.session();secret=self.options['secret']
        encoded=''.join('%%%02X'%ord(c) for c in secret)
        partial=secret[:8]+''.join('%%%02x'%ord(c) for c in secret[8:])
        twice=encoded.replace('%','%25')
        for text in (encoded, partial, twice):
            for item in ({'debug':'https://example.invalid/?apiKey='+text},{text:0}):
                raw=json.dumps([item]).encode()
                with self.subTest(encoding=text,item_kind=next(iter(item))), \
                     self.assertRaisesRegex(ValueError,'^CAPTURE_CONTAINS_SECRET$') as error:
                    s.record(raw,**self.options)
                self.assertNotIn(secret,str(error.exception))
                self.assertEqual(list(self.root.iterdir()),[])

    def test_benign_percent_encoded_body_keeps_original_bytes(self):
        s=self.session()
        raw=b'[ {"debug":"https://example.invalid/?name=Home%20Team&v=%2520"} ]\n'
        receipt=s.record(raw,**self.options);summary=s.seal()
        records=self.module().replay_records(self.root,**self.context,
                             expected_manifest_sha256=summary['manifest_sha256'])
        self.assertEqual(records,[{'receipt':receipt,'raw':raw}])
        self.assertEqual((self.root/receipt['raw_file']).read_bytes(),raw)

    def test_invalid_json_sizes_quota_and_clocks_reject_without_writes(self):
        s=self.session()
        for raw in (b'',b'{broken',b'[{"x":1,"x":2}]',b'[NaN]',b'[1e9999]',b'{}'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):s.record(raw,**self.options)
        for changes in ({'quota':{'used':True,'remaining':1,'last':0}},
                        {'quota':dict(self.options['quota'],other=1)},
                        {'requested':self.start.replace(tzinfo=None)},
                        {'completed':self.start-timedelta(seconds=1)},
                        {'secret':''}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                s.record(self.raw,**dict(self.options,**changes))
        with patch.object(self.module(),'MAX_BODY_BYTES',2):
            with self.assertRaises(ValueError):s.record(self.raw,**self.options)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_existing_directory_repository_ancestor_and_symlink_reject(self):
        self.root.mkdir();marker=self.root/'keep';marker.write_bytes(b'original')
        with self.assertRaises(ValueError):self.session()
        self.assertEqual(marker.read_bytes(),b'original')
        self.root=self.base/'repo'/'nested'/'pack';self.root.parent.mkdir(parents=True)
        (self.base/'repo'/'.git').write_text('gitdir: elsewhere')
        with self.assertRaises(ValueError):self.session()
        real=self.base/'real';real.mkdir();alias=self.base/'alias';alias.symlink_to(real)
        self.root=alias/'pack'
        with self.assertRaises(ValueError):self.session()

    def test_seven_capture_limit_prevents_eighth_request(self):
        s=self.session()
        for _ in range(7):s.record(self.raw,**self.options)
        with self.assertRaises(ValueError):s.check_request('/sports/',None)
        with self.assertRaises(ValueError):s.record(self.raw,**self.options)
        self.assertEqual(s.seal()['capture_count'],7)

    def test_context_pin_missing_extra_and_tamper_reject(self):
        receipt,summary=self.make_pack();m=self.module()
        for changes in ({'run_id':'102'},{'attempt':'2'},{'source_sha':'b'*40}):
            with self.assertRaises(ValueError):m.replay(self.root,**dict(self.context,**changes))
        with self.assertRaises(ValueError):m.replay(self.root,**self.context,expected_manifest_sha256='0'*64)
        self.assertFalse(m.replay(self.root,**self.context)['manifest_digest_pinned'])
        path=self.root/receipt['raw_file'];original=path.read_bytes();path.write_bytes(original+b' ')
        with self.assertRaises(ValueError):m.replay(self.root,**self.context)
        path.write_bytes(original);extra=self.root/'extra';extra.write_bytes(b'x')
        with self.assertRaises(ValueError):m.replay(self.root,**self.context)
        extra.unlink();path.unlink()
        with self.assertRaises(ValueError):m.replay(self.root,**self.context)

    def test_replay_rejects_symlink_hardlink_fifo_and_permissions(self):
        receipt,_=self.make_pack();path=self.root/receipt['raw_file'];raw=path.read_bytes()
        outside=self.base/'outside';outside.write_bytes(raw)
        for kind in ('symlink','hardlink','fifo'):
            path.unlink()
            if kind=='symlink':path.symlink_to(outside)
            elif kind=='hardlink':os.link(outside,path)
            else:os.mkfifo(path)
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                self.module().replay(self.root,**self.context)
        path.unlink();path.write_bytes(raw);path.chmod(0o644)
        with self.assertRaises(ValueError):self.module().replay(self.root,**self.context)
        self.assertEqual(outside.read_bytes(),raw)

    def test_foreign_files_and_replaced_root_are_preserved(self):
        s=self.session();foreign=self.root/'foreign';foreign.write_bytes(b'keep')
        with self.assertRaises(ValueError):s.record(self.raw,**self.options)
        self.assertEqual(foreign.read_bytes(),b'keep')
        foreign.unlink();parked=self.base/'parked';self.root.rename(parked);self.root.mkdir()
        marker=self.root/'marker';marker.write_bytes(b'foreign root')
        with self.assertRaises(ValueError):s.seal()
        self.assertEqual(marker.read_bytes(),b'foreign root')
        self.assertEqual(list(parked.iterdir()),[])

    def test_empty_seal_and_closed_session_never_claim_truth_or_durability(self):
        s=self.session();report=s.seal()
        self.assertEqual(report['capture_count'],0)
        self.assertFalse(report['raw_source_authenticated']);self.assertFalse(report['durable_archive_verified'])
        for function in (s.seal,lambda:s.record(self.raw,**self.options)):
            with self.assertRaises(ValueError):function()
        s.close()

    def test_recorded_file_change_blocks_seal_and_closes_session(self):
        s=self.session();receipt=s.record(self.raw,**self.options)
        (self.root/receipt['raw_file']).write_bytes(self.raw+b' ')
        with self.assertRaises(ValueError):s.seal()
        self.assertFalse((self.root/'manifest.json').exists())
        with self.assertRaisesRegex(ValueError,'SESSION_CLOSED'):s.check_request('/sports/',None)

    def test_substitution_after_first_replay_read_is_rejected(self):
        receipt,_=self.make_pack();module=self.module();original=module._read
        changed=False
        def replace(descriptor,name,limit):
            nonlocal changed
            raw=original(descriptor,name,limit)
            if name.endswith('.receipt.json') and not changed:
                changed=True
                (self.root/receipt['raw_file']).write_bytes(self.raw+b' ')
            return raw
        with patch.object(module,'_read',side_effect=replace),self.assertRaises(ValueError):
            module.replay(self.root,**self.context)

    def test_new_directory_entry_during_replay_is_rejected_and_preserved(self):
        self.make_pack();module=self.module();original=module._read
        calls=0
        def insert(descriptor,name,limit):
            nonlocal calls
            raw=original(descriptor,name,limit)
            if name.endswith('.body.json'):
                calls+=1
                if calls==2:(self.root/'foreign').write_bytes(b'keep')
            return raw
        with patch.object(module,'_read',side_effect=insert),self.assertRaises(ValueError):
            module.replay(self.root,**self.context)
        self.assertEqual((self.root/'foreign').read_bytes(),b'keep')

    def test_cli_only_emits_safe_counts_and_fixed_error_codes(self):
        _,summary=self.make_pack();module=self.module()
        args=['--private-dir',str(self.root),'--source-sha',self.context['source_sha'],
              '--run-id','101','--attempt','1','--expected-manifest-sha256',summary['manifest_sha256']]
        with patch('sys.stdout',new_callable=io.StringIO) as out:
            self.assertEqual(module.main(args),0)
        result=json.loads(out.getvalue());self.assertEqual(result['capture_count'],1)
        self.assertNotIn('soccer_epl',out.getvalue());self.assertNotIn(str(self.root),out.getvalue())
        for argv in ([],args+['--SECRET']):
            with patch('sys.stdout',new_callable=io.StringIO) as out,patch('sys.stderr',new_callable=io.StringIO) as err:
                self.assertEqual(module.main(argv),1)
            self.assertNotIn('SECRET',out.getvalue());self.assertEqual(err.getvalue(),'')


if __name__=='__main__':unittest.main()
