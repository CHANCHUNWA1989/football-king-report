"""All-synthetic source custody tests; never use or expose a true age key."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

from ops import identity_ab_two_source_custody as custody
from ops import identity_ab_two_provider_result_review as dual
from ops import private_response_relay as relay
from ops.shadow_raw_source_collector import source_urls
from ops.tests.test_identity_ab_two_provider_result_review import (
    ROOT, observation, second, encoded, clock,
)

NOW=datetime.fromisoformat(clock(after=4))
COMMIT="a"*40
RUN="42445456132"
ATTEMPT="1"


def source_proof():
    source={
        "OpenLigaDB":json.dumps([observation(finished=True)],sort_keys=True).encode(),
        "OpenFootball":encoded([second()]),
    }
    urls=source_urls(2026)
    receipts={
        provider:{
            "url":urls[provider],"final_url":urls[provider],
            "status":200,"media":"application/json",
            "received_utc":(NOW-timedelta(seconds=8)).isoformat(),
        }
        for provider in source
    }
    report=dual.compare(ROOT,source["OpenLigaDB"],source["OpenFootball"],
                        observed_utc=NOW.isoformat(),transport_verified=True)
    return source,receipts,report


def crypto_stub(pack, args, executable, *, maximum):
    if args[:2] != ["--encrypt","-r"] or len(pack) < 20:
        raise AssertionError("Expected authentic age encrypt semantics")
    # Synthetic opaque stand-in; no plaintext is embedded in outputs.
    return hashlib.sha256(pack).digest() * 1550


class TwoSourceCustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.folder=self.root/"new-source-proof"
        self.source,self.receipt,self.report=source_proof()
        self.recipient=Path(__file__).resolve().parents[2]/(
            "sources/policies/private_original_recipient_v1.txt")

    def run_capture(self, *, source=None, receipts=None, report=None):
        with patch.object(custody.relay,"_crypto",side_effect=crypto_stub):
            return custody.capture(
                self.folder, self.source if source is None else source,
                self.receipt if receipts is None else receipts,
                report=self.report if report is None else report,
                source_commit=COMMIT,run_id=RUN,attempt=ATTEMPT,
                age_binary=self.root/"mock-age",recipient_path=self.recipient)

    def test_encrypted_chunks_only_and_receipts_without_score_body(self):
        result=self.run_capture()
        self.assertTrue(result["source_originals_encrypted"])
        self.assertFalse(result["source_ciphertexts_remotely_preserved"])
        index=json.loads((self.folder/"index.json").read_text())
        self.assertEqual(index["source_count"],2)
        self.assertEqual(result["ciphertext_parts"],4)
        self.assertEqual(result["local_file_count"],7)
        self.assertEqual(len(index["file_sha256"]),6)
        for provider in custody.TWO_SOURCES:
            proof=json.loads((self.folder/(provider+".receipt.json")).read_text())
            self.assertEqual(proof["source_raw_sha256"],
                             hashlib.sha256(self.source[provider]).hexdigest())
            self.assertEqual(proof["certified_case_count"],0)
            self.assertFalse(proof["upstream_independence_authenticated"])
            part_names=index["sources"][provider]["parts"]
            self.assertEqual(len(part_names),2)
            whole=b"".join((self.folder/p).read_bytes() for p in part_names)
            self.assertEqual(hashlib.sha256(whole).hexdigest(),
                             proof["encrypted_ciphertext_sha256"])
            for name in part_names:
                body=(self.folder/name).read_bytes()
                self.assertLessEqual(len(body),custody.MAX_PART_BYTES)
                self.assertNotIn(b"matchID",body)
                self.assertEqual(hashlib.sha256(body).hexdigest(),
                                 index["file_sha256"][name])
        self.assertEqual(self.folder.stat().st_mode&0o777,0o700)
        self.assertEqual((self.folder/"index.json").stat().st_mode&0o777,0o600)

    def test_pack_carries_exact_original_bytes_for_future_private_decryption(self):
        for provider in custody.TWO_SOURCES:
            pack,meta=custody._pack(self.source[provider],self.receipt[provider],provider)
            self.assertTrue(pack.startswith(custody.MAGIC))
            offset=len(custody.MAGIC)
            count=int.from_bytes(pack[offset:offset+4],"big")
            header=json.loads(pack[offset+4:offset+4+count])
            raw=zlib.decompress(pack[offset+4+count:])
            self.assertEqual(raw,self.source[provider])
            self.assertEqual(meta,header)
            self.assertEqual(header["raw_sha256"],hashlib.sha256(raw).hexdigest())
            self.assertFalse(header["source_publisher_authenticated"])

    def test_duplicate_archive_directory_never_overwritten(self):
        self.run_capture()
        orig=(self.folder/"index.json").read_bytes()
        with self.assertRaisesRegex(custody.CustodyError,
                                    "UNSAFE_SOURCE_CUSTODY_DESTINATION"):
            self.run_capture()
        self.assertEqual((self.folder/"index.json").read_bytes(),orig)

    def test_wrong_http_url_or_status_rejected_before_any_file(self):
        for edits in (
            {"final_url":"https://evil.invalid/redirect"},
            {"status":301},
            {"media":"text/html"},
            {"url":"https://api.other.invalid"},
        ):
            p={key:dict(value) for key,value in self.receipt.items()}
            p["OpenFootball"].update(edits)
            with self.subTest(edits=edits):
                with self.assertRaisesRegex(custody.CustodyError,
                                            "UNTRUSTED_HTTP_SOURCE_RECEIPT"):
                    self.run_capture(receipts=p)
                self.assertFalse(self.folder.exists())

    def test_changed_source_raw_after_comparison_rejected(self):
        src=dict(self.source)
        src["OpenFootball"]=src["OpenFootball"]+b" "
        with self.assertRaisesRegex(custody.CustodyError,
                                    "SOURCE_CHANGED_AFTER_RESULT_COMPARISON"):
            self.run_capture(source=src)
        self.assertFalse(self.folder.exists())

    def test_future_or_ancient_http_receipt_time_rejected(self):
        for shift in (timedelta(seconds=20),timedelta(hours=-1)):
            receipt={p:dict(value) for p,value in self.receipt.items()}
            receipt["OpenLigaDB"]["received_utc"]=(NOW+shift).isoformat()
            with self.subTest(shift=shift):
                with self.assertRaisesRegex(custody.CustodyError,
                                            "SOURCE_OBSERVATION_TIMESTAMP_CONFLICT"):
                    self.run_capture(receipts=receipt)
                self.assertFalse(self.folder.exists())

    def test_no_private_key_and_no_forged_trusted_outcome_allowed(self):
        for name,value in (("certified_scored_cases",1),
                           ("upstream_independence_authenticated",True),
                           ("production_recommendations","ENABLED")):
            forged=dict(self.report)
            forged[name]=value
            with self.subTest(name=name):
                with self.assertRaisesRegex(custody.CustodyError,
                                            "UNTRUSTED_TWO_SOURCE_REVIEW"):
                    self.run_capture(report=forged)
                self.assertFalse(self.folder.exists())

    def test_failed_encryption_cannot_write_partial_public_files(self):
        def broken(*args,**kwargs):
            raise relay.RelayError("PRIVATE_RELAY_CRYPTO_REJECTED")
        with patch.object(custody.relay,"_crypto",side_effect=broken):
            with self.assertRaisesRegex(custody.CustodyError,
                                        "PINNED_PQ_ENCRYPTION_FAILED"):
                custody.capture(self.folder,self.source,self.receipt,
                    report=self.report,source_commit=COMMIT,
                    run_id=RUN,attempt=ATTEMPT,age_binary=self.root/"mock-age",
                    recipient_path=self.recipient)
        self.assertFalse(self.folder.exists())

    def test_missing_source_rejected_without_output(self):
        src=dict(self.source)
        src.pop("OpenFootball")
        with self.assertRaisesRegex(custody.CustodyError,
                                    "INCOMPLETE_TWO_SOURCE_CUSTODY"):
            self.run_capture(source=src)
        self.assertFalse(self.folder.exists())


if __name__=="__main__":
    unittest.main()
