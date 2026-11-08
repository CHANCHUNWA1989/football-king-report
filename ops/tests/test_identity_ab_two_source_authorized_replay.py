"""Authorized replay: synthetic PQ decrypt stub only, never actual private keys.

Positive tests exercise the REAL custody pack format and the real strict zlib/
manifest validation; the crypto subprocess is replaced with a deterministic
synthetic mapping. CI MUST NOT be reported as having decrypted actual historical
ciphertexts (the original age private identity is not available in CI).
"""
import copy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

from ops import identity_ab_two_source_authorized_replay as replay
from ops import identity_ab_two_source_custody as custody
from ops.tests.test_identity_ab_two_source_custody import (
    source_proof, COMMIT, RUN, ATTEMPT,
)


class AuthorizedOwnerOfflineReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.directory=self.root/"pq-source-archive"
        self.private=self.root/"secret-vault"
        self.private.mkdir(mode=0o700)
        self.secret_file=self.private/"age-identity.txt"
        self.fake_secret=("AGE-SECRET-KEY-PQ-1"+"A"*120+"\n").encode("ascii")
        fd=os.open(self.secret_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as f:
            f.write(self.fake_secret)
        self.age_bin=self.root/"mock-age"
        self.sources,self.receipts,self.report=source_proof()
        self.recipient=(Path(__file__).resolve().parents[2]
                       /"sources/policies/private_original_recipient_v1.txt")
        self.mapping={}
        def encrypt(pack,args,bin_path,*,maximum):
            self.assertEqual(args[:2],["--encrypt","-r"])
            opaque=b"MOCK-ENCRYPTED-ONLY:" + hashlib.sha256(pack).digest()*3
            self.mapping[opaque]=pack
            return opaque
        with patch.object(custody.relay,"_crypto",side_effect=encrypt):
            custody.capture(self.directory,self.sources,self.receipts,
                            report=self.report,source_commit=COMMIT,
                            run_id=RUN,attempt=ATTEMPT,
                            age_binary=self.age_bin,recipient_path=self.recipient)
        synthetic_index=(self.directory/"index.json").read_bytes()
        self.index_pin=patch.object(
            replay,"INDEX_GIT_BLOB_SHA1",replay._git_blob(synthetic_index))
        self.index_pin.start()
        self.addCleanup(self.index_pin.stop)
        self.gate=patch.object(replay,"verify_public",return_value={
            "public_source_ciphertext_integrity_verified":True,
            "verified_public_files":5,
            "private_decryption_verified":False,
            "certified_scored_case_count":0,
            "original_source_raw_sha256":{
                provider:hashlib.sha256(raw).hexdigest()
                for provider,raw in self.sources.items()
            },
        })
        self.gate.start()
        self.addCleanup(self.gate.stop)

    def mock_decrypt(self, cipher,args,age,*,identity,maximum):
        self.assertEqual(args,["--decrypt"])
        self.assertEqual(identity,self.fake_secret)
        self.assertEqual(age,self.age_bin)
        return self.mapping[cipher]

    def test_real_custody_format_decrypt_replay_both_original_raw_bytes(self):
        with patch.object(replay,"crypto",side_effect=self.mock_decrypt):
            output=replay.replay(self.directory,identity_path=self.secret_file,
                                 age_binary=self.age_bin)
        self.assertTrue(output["original_source_bytes_decrypted_and_replayed"])
        self.assertTrue(output["public_ciphertext_integrity_verified"])
        self.assertEqual(output["sources_verified"],2)
        for provider,raw in self.sources.items():
            self.assertEqual(output["source_byte_proofs"][provider]["source_raw_sha256"],
                             hashlib.sha256(raw).hexdigest())
            self.assertEqual(output["source_byte_proofs"][provider]["source_raw_bytes"],
                             len(raw))
        self.assertFalse(output["private_identity_disclosed_or_uploaded"])
        self.assertFalse(output["source_publisher_authenticated"])
        self.assertFalse(output["upstream_independence_authenticated"])
        self.assertFalse(output["actual_kickoff_authenticated"])
        self.assertEqual(output["independently_verified_regulation_ft"],0)
        self.assertEqual(output["certified_scored_cases"],0)
        self.assertFalse(output["positive_ev_verified"])
        self.assertEqual(output["production_recommendations"],"DISABLED")
        self.assertNotIn("raw",json.dumps(output).lower().split("source_byte_proofs")[0])

    def test_public_tamper_check_must_happen_before_secret_read(self):
        with patch.object(replay,"verify_public",side_effect=replay.SourceArchiveError(
            "ORIGINAL_SOURCE_CUSTODY_INDEX_CHANGED")):
            with patch.object(replay,"_secret",side_effect=AssertionError(
                "private identity must not be read")):
                with self.assertRaises(replay.SourceArchiveError):
                    replay.replay(self.directory,identity_path=self.secret_file,
                                  age_binary=self.age_bin)

    def test_secure_identity_file_only_0600_private_directory(self):
        self.secret_file.chmod(0o644)
        with self.assertRaises(replay.AuthorizedReplayError):
            replay.replay(self.directory,identity_path=self.secret_file,
                          age_binary=self.age_bin)
        self.secret_file.chmod(0o600)
        self.private.chmod(0o755)
        with self.assertRaises(replay.AuthorizedReplayError):
            replay.replay(self.directory,identity_path=self.secret_file,
                          age_binary=self.age_bin)

    def test_wrong_identity_format_cannot_run_decryption(self):
        self.secret_file.write_text("example-fake-key\n")
        with patch.object(replay,"crypto",side_effect=AssertionError(
            "should never invoke cipher")):
            with self.assertRaisesRegex(replay.AuthorizedReplayError,
                                        "PRIVATE_AGE_IDENTITY_INVALID"):
                replay.replay(self.directory,identity_path=self.secret_file,
                              age_binary=self.age_bin)

    def test_wrong_age_identity_cannot_produce_partial_success(self):
        def fails(*args,**kwargs):
            raise replay.RelayError("PRIVATE_RELAY_CRYPTO_REJECTED")
        with patch.object(replay,"crypto",side_effect=fails):
            with self.assertRaisesRegex(replay.AuthorizedReplayError,
                                        "PQ_AGE_DECRYPTION_FAILED"):
                replay.replay(self.directory,identity_path=self.secret_file,
                              age_binary=self.age_bin)

    def test_second_provider_failure_rejects_entire_two_source_claim(self):
        def fails_second(cipher,args,age,*,identity,maximum):
            if cipher==self._cipher_for("OpenFootball"):
                raise replay.RelayError("PRIVATE_RELAY_CRYPTO_REJECTED")
            return self.mock_decrypt(cipher,args,age,identity=identity,maximum=maximum)
        with patch.object(replay,"crypto",side_effect=fails_second):
            with self.assertRaisesRegex(replay.AuthorizedReplayError,
                                        "PQ_AGE_DECRYPTION_FAILED"):
                replay.replay(self.directory,identity_path=self.secret_file,
                              age_binary=self.age_bin)

    def _cipher_for(self,provider):
        ix=json.loads((self.directory/"index.json").read_text())
        return b"".join((self.directory/name).read_bytes()
                        for name in ix["sources"][provider]["parts"])

    def test_index_swapped_after_initial_audit_is_rejected_before_key_use(self):
        def swap(_directory):
            path=self.directory/"index.json"
            path.write_bytes(path.read_bytes()+b" ")
            return {
                "public_source_ciphertext_integrity_verified":True,
                "verified_public_files":5,
                "private_decryption_verified":False,
                "certified_scored_case_count":0,
                "original_source_raw_sha256":{
                    key:hashlib.sha256(value).hexdigest()
                    for key,value in self.sources.items(),
                },
            }
        with patch.object(replay,"verify_public",side_effect=swap):
            with patch.object(replay,"_secret",side_effect=AssertionError(
                    "must reject changed index before loading key")):
                with self.assertRaisesRegex(replay.AuthorizedReplayError,
                                            "CUSTODY_INDEX_CHANGED_AFTER_PUBLIC_CHECK"):
                    replay.replay(self.directory,identity_path=self.secret_file,
                                  age_binary=self.age_bin)

    def test_receipt_swapped_after_public_audit_rejected_before_decrypt(self):
        def mutate(_identity_path):
            receipt_path=self.directory/"OpenLigaDB.receipt.json"
            receipt_path.write_bytes(receipt_path.read_bytes()+b" ")
            return self.fake_secret
        with patch.object(replay,"_secret",side_effect=mutate):
            with patch.object(replay,"crypto",side_effect=AssertionError(
                    "decrypt must not run on changed receipt")):
                with self.assertRaisesRegex(replay.AuthorizedReplayError,
                                            "SOURCE_RECEIPT_CHANGED_AFTER_PUBLIC_CHECK"):
                    replay.replay(self.directory,identity_path=self.secret_file,
                                  age_binary=self.age_bin)

    def test_ciphertext_swapped_after_public_audit_rejected_before_decrypt(self):
        def mutate(_identity_path):
            path=self.directory/"OpenLigaDB.age.part000"
            raw=path.read_bytes()
            path.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
            return self.fake_secret
        with patch.object(replay,"_secret",side_effect=mutate):
            with patch.object(replay,"crypto",side_effect=AssertionError(
                    "decrypt must not run on changed ciphertext")):
                with self.assertRaisesRegex(replay.AuthorizedReplayError,
                                            "CIPHER_CHUNK_CHANGED_AFTER_PUBLIC_CHECK"):
                    replay.replay(self.directory,identity_path=self.secret_file,
                                  age_binary=self.age_bin)

    def test_source_bytes_corruption_inside_decrypted_pack_is_rejected(self):
        packed,header=custody._pack(
            self.sources["OpenFootball"],self.receipts["OpenFootball"],
            "OpenFootball")
        receipt=json.loads((self.directory/"OpenFootball.receipt.json").read_text())
        corrupt=packed[:-1]+bytes([packed[-1]^1])
        receipt["compressed_original_pack_sha256"]=hashlib.sha256(corrupt).hexdigest()
        receipt["compressed_original_pack_bytes"]=len(corrupt)
        with self.assertRaises(replay.AuthorizedReplayError):
            replay._unpack_authenticated(corrupt,provider="OpenFootball",
                                         receipt=receipt)

    def test_forged_authority_inside_decrypted_manifest_cannot_pass(self):
        packed,header=custody._pack(
            self.sources["OpenLigaDB"],self.receipts["OpenLigaDB"],
            "OpenLigaDB")
        receipt=json.loads((self.directory/"OpenLigaDB.receipt.json").read_text())
        header["regulation_ft_authenticated"]=True
        blob=(json.dumps(header,sort_keys=True,separators=(",",":"))+"\n").encode()
        offset=len(custody.MAGIC)
        pack=custody.MAGIC+len(blob).to_bytes(4,"big")+blob+packed[
            offset+4+int.from_bytes(packed[offset:offset+4],"big"):]
        receipt["compressed_original_pack_sha256"]=hashlib.sha256(pack).hexdigest()
        receipt["compressed_original_pack_bytes"]=len(pack)
        with self.assertRaisesRegex(replay.AuthorizedReplayError,
                                    "DECRYPTED_SOURCE_HEADER_CONTRADICTION"):
            replay._unpack_authenticated(pack,provider="OpenLigaDB",
                                         receipt=receipt)

    def test_decompression_bomb_fails_bounded_output(self):
        packed,header=custody._pack(
            self.sources["OpenFootball"],self.receipts["OpenFootball"],
            "OpenFootball")
        receipt=json.loads((self.directory/"OpenFootball.receipt.json").read_text())
        n=len(custody.MAGIC)
        start=n+4+int.from_bytes(packed[n:n+4],"big")
        bomb=packed[:start]+zlib.compress(b"A"*(3_000_050),9)
        receipt["compressed_original_pack_sha256"]=hashlib.sha256(bomb).hexdigest()
        receipt["compressed_original_pack_bytes"]=len(bomb)
        with self.assertRaisesRegex(replay.AuthorizedReplayError,
                                    "DECRYPTED_SOURCE_DECOMPRESSION_UNSAFE"):
            replay._unpack_authenticated(bomb,provider="OpenFootball",
                                         receipt=receipt)

    def test_trailing_compressed_garbage_fails(self):
        packed,_=custody._pack(self.sources["OpenFootball"],
                               self.receipts["OpenFootball"],"OpenFootball")
        receipt=json.loads((self.directory/"OpenFootball.receipt.json").read_text())
        changed=packed+b"extra"
        receipt["compressed_original_pack_sha256"]=hashlib.sha256(changed).hexdigest()
        receipt["compressed_original_pack_bytes"]=len(changed)
        with self.assertRaisesRegex(replay.AuthorizedReplayError,
                                    "DECRYPTED_SOURCE_DECOMPRESSION_UNSAFE"):
            replay._unpack_authenticated(changed,provider="OpenFootball",
                                         receipt=receipt)

    def test_noncanonical_manifest_fails_even_if_rewrapped(self):
        packed,header=custody._pack(
            self.sources["OpenFootball"],self.receipts["OpenFootball"],
            "OpenFootball")
        receipt=json.loads((self.directory/"OpenFootball.receipt.json").read_text())
        n=len(custody.MAGIC)
        size=int.from_bytes(packed[n:n+4],"big")
        blob=json.dumps(header,indent=2).encode()
        changed=packed[:n]+len(blob).to_bytes(4,"big")+blob+packed[n+4+size:]
        receipt["compressed_original_pack_sha256"]=hashlib.sha256(changed).hexdigest()
        receipt["compressed_original_pack_bytes"]=len(changed)
        with self.assertRaisesRegex(replay.AuthorizedReplayError,
                                    "DECRYPTED_ENVELOPE_HEADER_NOT_CANONICAL"):
            replay._unpack_authenticated(changed,provider="OpenFootball",
                                         receipt=receipt)


if __name__=="__main__":
    unittest.main()
