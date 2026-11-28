"""Offline Ed25519 checkpoint verifier. Never authorizes resume or establishes latestness."""
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

PREFIX = bytes.fromhex('302a300506032b6570032100')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(doc):
    if type(doc) is not dict or set(doc) != {'schema', 'domain', 'database_sha256', 'sequence'}:
        raise ValueError('invalid checkpoint schema')
    if doc['schema'] != 'research-checkpoint-v1' or doc['domain'] not in ('football', 'quant'):
        raise ValueError('invalid checkpoint identity')
    if type(doc['database_sha256']) is not str or not re.fullmatch('[a-f0-9]{64}', doc['database_sha256']):
        raise ValueError('invalid database hash')
    if type(doc['sequence']) is not int or not 0 <= doc['sequence'] < 2**63:
        raise ValueError('invalid sequence')
    return json.dumps(doc, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def verify(doc, signature, public_key, *, pinned_key_sha256, expected_checkpoint_sha256, expected_domain):
    raw = canonical(doc)
    if type(public_key) is not bytes or len(public_key) != 44 or not public_key.startswith(PREFIX) or sha(public_key) != pinned_key_sha256:
        raise ValueError('untrusted key')
    if type(signature) is not bytes or len(signature) != 64:
        raise ValueError('invalid signature')
    if doc['domain'] != expected_domain or sha(raw) != expected_checkpoint_sha256:
        raise ValueError('unexpected checkpoint')
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for name, data in [('key.der', public_key), ('message', raw), ('signature', signature)]:
            (root / name).write_bytes(data)
        result = subprocess.run(['openssl', 'pkeyutl', '-verify', '-pubin', '-keyform', 'DER', '-inkey', str(root/'key.der'), '-rawin', '-in', str(root/'message'), '-sigfile', str(root/'signature')], capture_output=True, timeout=5)
        if result.returncode != 0:
            raise ValueError('signature verification failed')
    return {'signature_valid':True, 'checkpoint_sha256':sha(raw), 'key_sha256':sha(public_key), 'external_latestness_verified':False, 'rollback_protection':False, 'resume_allowed':False, 'automatic_restore':False, 'status':'HOLD', 'model_input_allowed':False, 'live_trading':'DISABLED', 'production_recommendations':'DISABLED'}


if __name__ == '__main__':
    import unittest
    class Tests(unittest.TestCase):
        def setUp(self):
            folder = tempfile.TemporaryDirectory()
            self.addCleanup(folder.cleanup)
            self.root = Path(folder.name)
            self.key = self.root/'key.pem'
            subprocess.run(['openssl','genpkey','-algorithm','ED25519','-out',str(self.key)],check=True,capture_output=True,timeout=5)
            self.pub = subprocess.check_output(['openssl','pkey','-in',str(self.key),'-pubout','-outform','DER'],timeout=5)
            self.doc = dict(schema='research-checkpoint-v1',domain='football',database_sha256='a'*64,sequence=7)
            self.sig = self.sign(self.doc)
        def sign(self, doc):
            p=self.root/'message';p.write_bytes(canonical(doc))
            return subprocess.check_output(['openssl','pkeyutl','-sign','-inkey',str(self.key),'-rawin','-in',str(p)],timeout=5)
        def check(self, doc=None, sig=None, **kw):
            args=dict(pinned_key_sha256=sha(self.pub),expected_checkpoint_sha256=sha(canonical(self.doc)),expected_domain='football');args.update(kw)
            return verify(self.doc if doc is None else doc,self.sig if sig is None else sig,self.pub,**args)
        def test_valid_never_resumes(self):
            result=self.check()
            self.assertTrue(result['signature_valid'])
            for k in ('resume_allowed','rollback_protection','external_latestness_verified','automatic_restore','model_input_allowed'): self.assertIs(result[k],False)
        def test_tamper(self):
            doc=dict(self.doc,sequence=8)
            with self.assertRaises(ValueError): self.check(doc,expected_checkpoint_sha256=sha(canonical(doc)))
        def test_wrong_signature(self):
            with self.assertRaises(ValueError): self.check(sig=bytes(64))
        def test_wrong_key_pin(self):
            with self.assertRaises(ValueError): self.check(pinned_key_sha256='0'*64)
        def test_cross_domain(self):
            with self.assertRaises(ValueError): self.check(expected_domain='quant')
        def test_old_valid_signature(self):
            old=dict(self.doc,sequence=6)
            with self.assertRaises(ValueError): self.check(old,self.sign(old))
            # If caller supplies an old expected digest, valid old signatures still verify.
            self.assertFalse(self.check(old,self.sign(old),expected_checkpoint_sha256=sha(canonical(old)))['rollback_protection'])
        def test_schema(self):
            for doc in (dict(self.doc,sequence=True),dict(self.doc,extra=1),dict(self.doc,database_sha256='bad')):
                with self.assertRaises(ValueError): canonical(doc)
    unittest.main(verbosity=2)
