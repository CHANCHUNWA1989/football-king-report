"""Synthetic-only replay pack tests. No real provider payloads or secrets."""
import copy
from datetime import datetime, timezone, timedelta
import hashlib
import io
import json
import sys
import tarfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from inplay_two_source_byte_packet import audit
from inplay_private_claim_replay import make_private_package, replay_private_package
from test_inplay_two_source_byte_packet import fixture, pair, source, raw, NOW


def make():
    return make_private_package(fixture(), pair(), now=NOW)


def forge_tar(entries):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode="w",format=tarfile.USTAR_FORMAT) as archive:
        for name,body,kind in entries:
            member=tarfile.TarInfo(name)
            member.mode=0o600; member.uid=member.gid=member.mtime=0
            if kind=="symlink":
                member.type=tarfile.SYMTYPE
                member.linkname="../secret"
            else:
                member.size=len(body)
            archive.addfile(member,io.BytesIO(body) if kind=="file" else None)
    return out.getvalue()


class InPlayPrivateClaimReplayTests(unittest.TestCase):
    def test_private_package_replay_preserves_input_byte_hashes(self):
        originals=pair()
        before=copy.deepcopy(originals)
        package=make_private_package(fixture(), originals, now=NOW)
        report=replay_private_package(package, now=NOW+timedelta(days=2))
        self.assertEqual(originals,before)
        self.assertEqual(report["status"],"RESEARCH_ONLY")
        self.assertTrue(report["exact_original_claim_bytes_replayed"])
        self.assertTrue(report["deterministic_private_container_rebuilt"])
        self.assertEqual(report["claimed_source_count"],2)
        self.assertFalse(report["raw_source_publisher_authenticated"])
        self.assertFalse(report["externally_attested"])
        self.assertFalse(report["durable_storage_verified"])
        self.assertFalse(report["eligible_for_model_input"])
        self.assertFalse(report["eligible_for_model_scoring"])
        self.assertFalse(report["positive_ev_verified"])
        self.assertEqual(report["certified_forward_samples"],0)
        self.assertEqual(report["production_recommendations"],"DISABLED")
        self.assertEqual(len(report["private_package_sha256_unattested"]),64)
        self.assertEqual(len(report["packet_sha256_unattested"]),64)
        self.assertNotIn("sofascore.com",str(report))
        self.assertEqual(report["source_byte_sha256_unattested"],
                         audit(fixture(),originals,now=NOW)["source_byte_sha256_unattested"])
        self.assertIsNone(report["recommendation"])

    def test_reversal_of_sources_produces_identical_bytes(self):
        claims=pair()
        a=make_private_package(fixture(),claims,now=NOW)
        b=make_private_package(fixture(),list(reversed(claims)),now=NOW)
        self.assertEqual(a,b)

    def test_raw_claims_are_physically_present_in_package(self):
        package=make()
        with tarfile.open(fileobj=io.BytesIO(package),mode="r:") as tar:
            names=tar.getnames()
            self.assertEqual(set(names),{"manifest.json","fotmob.claim.json","sofascore.claim.json"})
            self.assertEqual(tar.extractfile("fotmob.claim.json").read(),pair()[0])
            self.assertEqual(tar.extractfile("sofascore.claim.json").read(),pair()[1])

    def test_tampered_claim_byte_fails(self):
        original=make()
        with tarfile.open(fileobj=io.BytesIO(original),mode="r:") as tar:
            records=[(m.name,tar.extractfile(m).read(),"file") for m in tar.getmembers()]
        records[1]=(records[1][0],records[1][1].replace(b'"home_goals":1',b'"home_goals":2'),"file")
        self.assertEqual(replay_private_package(forge_tar(records),now=NOW)["status"],"HOLD")

    def test_tampered_manifest_or_claim_digest_fails(self):
        package=make()
        with tarfile.open(fileobj=io.BytesIO(package),mode="r:") as tar:
            records=[(m.name,tar.extractfile(m).read(),"file") for m in tar.getmembers()]
        envelope=json.loads(records[0][1])
        envelope["packet_sha256_unattested"]="0"*64
        records[0]=(records[0][0],json.dumps(envelope,sort_keys=True,separators=(",",":")).encode(),"file")
        self.assertEqual(replay_private_package(forge_tar(records),now=NOW)["status"],"HOLD")

    def test_directory_traversal_and_extra_file_rejected(self):
        original=make()
        with tarfile.open(fileobj=io.BytesIO(original),mode="r:") as tar:
            entries=[(m.name,tar.extractfile(m).read(),"file") for m in tar.getmembers()]
        for extra in ("../secret", "other.json"):
            self.assertEqual(replay_private_package(forge_tar(entries+[(extra,b"TOPSECRET","file")]),now=NOW)["status"],"HOLD")

    def test_repeated_manifest_file_and_symlink_rejected(self):
        original=make()
        with tarfile.open(fileobj=io.BytesIO(original),mode="r:") as tar:
            entries=[(m.name,tar.extractfile(m).read(),"file") for m in tar.getmembers()]
        self.assertEqual(replay_private_package(forge_tar(entries+[entries[0]]),now=NOW)["status"],"HOLD")
        entries[1]=(entries[1][0],b"","symlink")
        self.assertEqual(replay_private_package(forge_tar(entries),now=NOW)["status"],"HOLD")

    def test_appended_bytes_and_changed_tar_header_fail(self):
        raw_package=make()
        self.assertEqual(replay_private_package(raw_package+b"TRAILING_UNAUDITED",now=NOW)["status"],"HOLD")
        tampered=bytearray(raw_package)
        tampered[100]^=1
        self.assertEqual(replay_private_package(bytes(tampered),now=NOW)["status"],"HOLD")

    def test_error_no_raw_claim_content_or_provider_url_leak(self):
        evil=source("fotmob")
        evil["api_key"]="SECRET_DO_NOT_PRINT"
        with self.assertRaises(ValueError) as context:
            make_private_package(fixture(),[raw(evil),pair()[1]],now=NOW)
        self.assertNotIn("SECRET_DO_NOT_PRINT",str(context.exception))
        bad=b"SECRET_DO_NOT_PRINT"
        report=replay_private_package(bad,now=NOW)
        self.assertEqual(report["status"],"HOLD")
        self.assertNotIn("SECRET_DO_NOT_PRINT",str(report))

    def test_wrong_clock_and_future_issued_capture_is_not_replayable(self):
        package=make()
        result=replay_private_package(package,now=NOW-timedelta(seconds=1))
        self.assertEqual(result["status"],"HOLD")
        self.assertFalse(result["exact_original_claim_bytes_replayed"])

    def test_nonbytes_and_oversized_replay_rejected(self):
        for invalid in (None,{},b"",b"X"*131073):
            self.assertEqual(replay_private_package(invalid,now=NOW)["status"],"HOLD")

    def test_preexisting_source_disagreement_does_not_make_package(self):
        a,b=source("fotmob"),source("sofascore")
        b["home_goals"]=2
        with self.assertRaisesRegex(ValueError,"SOURCE_CLAIMS_NOT_ADMISSIBLE"):
            make_private_package(fixture(),[raw(a),raw(b)],now=NOW)


if __name__=="__main__":
    unittest.main()
