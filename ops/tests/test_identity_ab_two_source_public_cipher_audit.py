"""Actual pinned 2026-11-08 dual-source ciphertexts: replay, tamper, spoof tests."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ops import identity_ab_two_source_public_cipher_audit as audit


ORIGINAL=(Path(__file__).resolve().parents[2]
          /"evidence/identity_ab_ft_sources/v1/42446535384-1")


class PinnedSourceCipherAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/audit.RUN_DIRECTORY
        shutil.copytree(ORIGINAL,self.root)

    def test_complete_real_source_archive_checks_every_byte(self):
        result=audit.verify(self.root)
        self.assertTrue(result["public_source_ciphertext_integrity_verified"])
        self.assertEqual(result["verified_public_files"],5)
        self.assertEqual(result["sealed_ciphertext_chunks"],2)
        self.assertEqual(result["sealed_receipts"],2)
        self.assertEqual(result["original_source_counts"],2)
        self.assertFalse(result["private_decryption_verified"])
        self.assertFalse(result["upstream_independence_authenticated"])
        self.assertEqual(result["independently_verified_regulation_ft"],0)
        self.assertEqual(result["certified_scored_case_count"],0)
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_one_bit_ciphertext_mutation_fails(self):
        path=self.root/"OpenLigaDB.age.part000"
        original=path.read_bytes()
        path.write_bytes(original[:-1]+bytes([original[-1]^1]))
        with self.assertRaisesRegex(audit.SourceArchiveError,
                                    "SOURCE_CIPHER_BYTES_CHANGED"):
            audit.verify(self.root)

    def test_original_receipt_mutation_fails_against_index(self):
        path=self.root/"OpenFootball.receipt.json"
        path.write_bytes(path.read_bytes()+b" ")
        with self.assertRaisesRegex(audit.SourceArchiveError,
                                    "SOURCE_RECEIPT_BYTES_CHANGED"):
            audit.verify(self.root)

    def test_index_rewrite_fails_original_git_blob_pin(self):
        p=self.root/"index.json"
        p.write_bytes(p.read_bytes()+b" ")
        with self.assertRaisesRegex(audit.SourceArchiveError,
                                    "ORIGINAL_SOURCE_CUSTODY_INDEX_CHANGED"):
            audit.verify(self.root)

    def test_missing_ciphertext_piece_fails_incomplete_denominator(self):
        (self.root/"OpenFootball.age.part000").unlink()
        with self.assertRaisesRegex(audit.SourceArchiveError,
                                    "SOURCE_CUSTODY_EXTRA_OR_MISSING_FILE"):
            audit.verify(self.root)

    def test_unexpected_plaintext_file_cannot_hide_in_public_custody(self):
        (self.root/"OpenFootball.json").write_text('{"score":[2,1]}')
        with self.assertRaisesRegex(audit.SourceArchiveError,
                                    "SOURCE_CUSTODY_EXTRA_OR_MISSING_FILE"):
            audit.verify(self.root)

    def test_symlink_refused_even_at_original_content_sha(self):
        original=self.root/"OpenFootball.age.part000"
        data=original.read_bytes()
        p=self.root.parent/"real-file"
        p.write_bytes(data)
        original.unlink()
        original.symlink_to(p)
        # Exact file names remain present; open(O_NOFOLLOW) must reject.
        with self.assertRaises(audit.ForwardArchiveAuditError):
            audit.verify(self.root)

    def test_forged_verification_flag_rejected_even_with_rewritten_sha(self):
        receipt_path=self.root/"OpenLigaDB.receipt.json"
        receipt=json.loads(receipt_path.read_text())
        receipt["regulation_ft_authenticated"]=True
        receipt_bytes=(json.dumps(receipt,sort_keys=True,
                                  separators=(",",":"))+"\n").encode()
        receipt_path.write_bytes(receipt_bytes)
        index_path=self.root/"index.json"
        index=json.loads(index_path.read_text())
        digest=hashlib.sha256(receipt_bytes).hexdigest()
        index["file_sha256"][receipt_path.name]=digest
        index["sources"]["OpenLigaDB"]["receipt_sha256"]=digest
        index_bytes=(json.dumps(index,sort_keys=True,separators=(",",":"))+"\n").encode()
        index_path.write_bytes(index_bytes)
        fake_pin=audit._git_blob(index_bytes)
        with patch.object(audit,"INDEX_GIT_BLOB_SHA1",fake_pin):
            with self.assertRaisesRegex(audit.SourceArchiveError,
                                        "CIPHER_RECEIPT_SEMANTICS_INVALID"):
                audit.verify(self.root)

    def test_swapped_custody_run_folder_is_rejected(self):
        wrong=self.root.parent/"replacement-run"
        self.root.rename(wrong)
        with self.assertRaisesRegex(audit.SourceArchiveError,
                                    "INVALID_SOURCE_CUSTODY_FOLDER"):
            audit.verify(wrong)


if __name__=="__main__":
    unittest.main()
