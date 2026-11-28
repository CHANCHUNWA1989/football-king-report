"""Bind a signed checkpoint to a local research snapshot; never authorize resume.
Expected digest, sequence, clock and key pin must come from a trusted caller.
This module does not authenticate that caller or prove external latestness.
"""
from signed_checkpoint import verify
from recovery_gate import review
from persistent_poll_policy import valid_time


def review_signed(path, doc, signature, public_key, *, pinned_key_sha256,
                  expected_checkpoint_sha256, expected_domain, expected_sequence,
                  expected_clock):
    if type(expected_sequence) is not int or not 0 <= expected_sequence < 2**63 or not valid_time(expected_clock):
        raise ValueError('invalid expected checkpoint state')
    signed = verify(doc, signature, public_key, pinned_key_sha256=pinned_key_sha256,
                    expected_checkpoint_sha256=expected_checkpoint_sha256,
                    expected_domain=expected_domain)
    if doc['sequence'] != expected_sequence:
        raise ValueError('checkpoint sequence mismatch')
    local = review(path, doc['database_sha256'], expected_sequence, expected_clock)
    return {'schema':'signed-recovery-review-v1', 'signature_valid':True,
            'snapshot_checkpoint_match':True, 'checkpoint_sha256':signed['checkpoint_sha256'],
            'key_sha256':signed['key_sha256'], 'active_leases':local['active_leases'],
            'halted_scopes':local['halted_scopes'], 'external_latestness_verified':False,
            'external_anchor_authenticated':False, 'rollback_protection':False,
            'resume_allowed':False, 'automatic_restore':False, 'status':'HOLD',
            'model_input_allowed':False, 'live_trading':'DISABLED',
            'production_recommendations':'DISABLED'}


if __name__ == '__main__':
    import subprocess
    import unittest
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from atomic_poll_cache import AtomicPollCache
    from db_backup import backup, digest
    from signed_checkpoint import canonical, sha

    class Tests(unittest.TestCase):
        def setUp(self):
            tmp = TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            self.root = Path(tmp.name)
            self.path = self.root/'state.db'
            self.store = AtomicPollCache.initialize(self.path, ['a'])
            self.key = self.root/'key.pem'
            subprocess.run(['openssl','genpkey','-algorithm','ED25519','-out',str(self.key)],check=True,capture_output=True,timeout=5)
            self.pub = subprocess.check_output(['openssl','pkey','-in',str(self.key),'-pubout','-outform','DER'],timeout=5)

        def checkpoint(self, seq):
            doc = dict(schema='research-checkpoint-v1',domain='football',database_sha256=digest(self.path),sequence=seq)
            msg = self.root/'message'
            msg.write_bytes(canonical(doc))
            sig = subprocess.check_output(['openssl','pkeyutl','-sign','-inkey',str(self.key),'-rawin','-in',str(msg)],timeout=5)
            return doc, sig

        def check(self, doc, sig, seq=0, clock=0, path=None, **overrides):
            args = dict(pinned_key_sha256=sha(self.pub),expected_checkpoint_sha256=sha(canonical(doc)),expected_domain='football',expected_sequence=seq,expected_clock=clock)
            args.update(overrides)
            return review_signed(self.path if path is None else path,doc,sig,self.pub,**args)

        def test_match_never_resumes(self):
            d,s = self.checkpoint(0)
            result = self.check(d,s)
            self.assertTrue(result['snapshot_checkpoint_match'])
            self.assertTrue(result['signature_valid'])
            for key in ('external_latestness_verified','external_anchor_authenticated','rollback_protection','resume_allowed','automatic_restore','model_input_allowed'):
                self.assertIs(result[key],False)
            self.assertEqual(result['status'],'HOLD')
            self.assertEqual(result['live_trading'],'DISABLED')
            self.assertEqual(digest(self.path),d['database_sha256'])

        def test_signed_old_snapshot_rejected_by_new_sequence(self):
            d,s = self.checkpoint(0)
            self.store.reserve('a',100)
            with self.assertRaises(ValueError): self.check(d,s,1,100)

        def test_changed_database_rejected_even_with_valid_signature(self):
            d,s = self.checkpoint(0)
            self.store.reserve('a',100)
            with self.assertRaises(ValueError): self.check(d,s)

        def test_wrong_clock_rejected(self):
            d,s = self.checkpoint(0)
            with self.assertRaises(ValueError): self.check(d,s,0,1)

        def test_active_lease_preserved(self):
            self.store.reserve('a',100)
            d,s = self.checkpoint(1)
            self.assertEqual(self.check(d,s,1,100)['active_leases'],1)
            self.assertIsNone(self.store.reserve('a',100000))

        def test_tampered_or_wrong_domain_signature(self):
            d,s = self.checkpoint(0)
            with self.assertRaises(ValueError): self.check(d,bytes(64))
            with self.assertRaises(ValueError): self.check(d,s,expected_domain='quant')

        def test_replayed_caller_checkpoint_never_certifies_latestness(self):
            old = self.root/'old.db'
            backup(self.path,old)
            # Sign the exact archived bytes; SQLite backup need not be byte-identical.
            live = self.path
            self.path = old
            d,s = self.checkpoint(0)
            self.path = live
            self.store.reserve('a',100)
            result = self.check(d,s,path=old)
            self.assertFalse(result['rollback_protection'])
            self.assertFalse(result['resume_allowed'])

    unittest.main(verbosity=2)
