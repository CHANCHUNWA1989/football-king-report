"""Fixed synthetic prospective A/B archive: no results, immutable bytes, completeness."""
import copy
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from ops import identity_ab_forward_seal as seal
from ops.identity_ab_openliga_probe import probe
from ops.tests.test_identity_ab_openliga_probe import source,encoded,NOW

SHA="a"*40
RUN="42443562562"
ATTEMPT="1"


def report():
    return probe(year=2026,observed_utc=NOW.isoformat(),raw=encoded(source()),
                 source_commit=SHA)


def seal_records(p=None,now=None):
    return seal.records(p if p is not None else report(),
                        received_utc=now or NOW.isoformat(),
                        source_commit=SHA,run_id=RUN,attempt=ATTEMPT)


class ForwardSealTests(unittest.TestCase):
    def test_real_model_synthetic_ledger_contains_each_future_probability(self):
        pack=report()
        files=seal_records(pack)
        self.assertEqual(len(files),1)
        self.assertEqual(list(files),["100075.json"])
        doc=json.loads(files["100075.json"])
        self.assertEqual(doc["provider_native_event_id"],"100075")
        self.assertEqual(doc["research_coverage"],"PAIRED")
        self.assertEqual(doc["source_response_sha256"],pack["raw_source_sha256"])
        self.assertEqual(doc["normalized_model_input_sha256"],
                         pack["ab"]["input_canonical_sha256"])
        self.assertEqual(doc["candidate_source_commit"],SHA)
        self.assertEqual(doc["github_run_id"],RUN)
        self.assertEqual(doc["github_run_attempt"],ATTEMPT)
        self.assertEqual(len(doc["legacy_1x2"]),3)
        self.assertEqual(len(doc["candidate_1x2"]),3)
        self.assertEqual(doc["production_recommendations"],"DISABLED")
        self.assertFalse(doc["regulation_time_result_verified"])
        self.assertFalse(doc["model_accuracy_improved_proven"])
        self.assertFalse(doc["positive_ev_verified"])
        self.assertNotIn("score_ft",doc)
        self.assertNotIn("outcome",doc)
        self.assertGreater(doc["forecast_horizon_at_capture_minutes"],60)

    def test_complete_archive_proves_index_exact_bytes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/"new-archive"
            index=seal.create_local_archive(target,report(),
                received_utc=NOW.isoformat(),source_commit=SHA,run_id=RUN,attempt=ATTEMPT)
            self.assertEqual(index["record_count"],1)
            self.assertEqual(set(p.name for p in target.iterdir()),
                             {"100075.json","index.json"})
            data=(target/"100075.json").read_bytes()
            self.assertEqual(index["record_sha256"]["100075.json"],
                             hashlib.sha256(data).hexdigest())
            self.assertEqual(json.loads((target/"index.json").read_text()),index)
            self.assertEqual(target.stat().st_mode&0o777,0o700)
            self.assertEqual((target/"100075.json").stat().st_mode&0o777,0o600)
            with self.assertRaisesRegex(seal.SealError,"UNSAFE_ARCHIVE_OUTPUT"):
                seal.create_local_archive(target,report(),
                    received_utc=NOW.isoformat(),source_commit=SHA,run_id=RUN,attempt=ATTEMPT)
            self.assertEqual((target/"100075.json").read_bytes(),data)

    def test_replay_is_deterministic_and_no_result_in_artifact(self):
        a=seal_records()
        b=seal_records()
        self.assertEqual(a,b)
        self.assertNotIn(b"score_ft",list(a.values())[0])
        self.assertNotIn(b"historical_outcome",list(a.values())[0])
        doc=json.loads(list(a.values())[0])
        self.assertFalse(doc["market_odds_verified"])
        self.assertNotIn("decimal_odds",doc)
        self.assertNotIn("executable_price",doc)

    def test_kickoff_within_one_hour_cannot_be_sealed(self):
        fake=copy.deepcopy(report())
        fake["ab"]["paired"][0]["kickoff_utc"]=(NOW+timedelta(minutes=30)).isoformat()
        with self.assertRaisesRegex(seal.SealError,"NOT_GENUINELY_PREKICKOFF"):
            seal_records(fake)

    def test_neither_mismatched_source_sha_nor_source_commit_accepted(self):
        for edit in ("raw_source_sha256","candidate_source_commit"):
            fake=copy.deepcopy(report())
            if edit=="raw_source_sha256":
                fake["raw_source_sha256"]="not-a-sha"
            else:
                fake["ab"][edit]="b"*40
            with self.subTest(edit=edit):
                with self.assertRaises(seal.SealError):
                    seal_records(fake)

    def test_never_archive_fake_certification_or_betting(self):
        for field,value in (
            ("positive_ev_verified",True),
            ("certified_case_count",1),
            ("production_recommendations","ENABLED"),
            ("provider_capture_authenticated",True),
        ):
            fake=copy.deepcopy(report())
            fake[field]=value
            with self.subTest(field=field):
                with self.assertRaisesRegex(seal.SealError,"UNTRUSTED_PROSPECTIVE_REPORT"):
                    seal_records(fake)

    def test_unpaired_matches_preserve_denominator_without_inventing_probability(self):
        fake=copy.deepcopy(report())
        case=fake["ab"]["paired"].pop()
        fake["ab"]["candidate_only"].append({
            "event_id":case["event_id"],"kickoff_utc":case["kickoff_utc"]
        })
        fake["ab"]["counts"]["paired"]-=1
        fake["ab"]["counts"]["legacy"]-=1
        fake["ab"]["counts"]["candidate_only"]+=1
        result=seal_records(fake)
        doc=json.loads(result["100075.json"])
        self.assertIsNone(doc["legacy_1x2"])
        self.assertIsNone(doc["candidate_1x2"])
        self.assertEqual(doc["research_coverage"],"CANDIDATE_ONLY")

    def test_duplicate_same_fixture_in_a_b_groups_fails_closed(self):
        fake=copy.deepcopy(report())
        case=fake["ab"]["paired"][0]
        fake["ab"]["candidate_only"].append({
            "event_id":case["event_id"],"kickoff_utc":case["kickoff_utc"]
        })
        fake["ab"]["counts"]["candidate"]+=1
        fake["ab"]["counts"]["candidate_only"]+=1
        with self.assertRaisesRegex(seal.SealError,"DUPLICATE_ARCHIVED_EVENT"):
            seal_records(fake)

    def test_invalid_run_provenance_rejected(self):
        for run_id,attempt in (("0","1"),("123","0"),("abc","1"),
                               ("123","-1")):
            with self.subTest(run_id=run_id,attempt=attempt):
                with self.assertRaises(seal.SealError):
                    seal.records(report(),received_utc=NOW.isoformat(),
                                 source_commit=SHA,run_id=run_id,attempt=attempt)

    def test_bad_forecast_probabilities_fail_before_any_file_is_written(self):
        fake=copy.deepcopy(report())
        fake["ab"]["paired"][0]["candidate_1x2"]=[.91,.91,-.82]
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"out"
            with self.assertRaisesRegex(seal.SealError,"INVALID_FORECAST_PROBABILITIES"):
                seal.create_local_archive(path,fake,received_utc=NOW.isoformat(),
                                          source_commit=SHA,run_id=RUN,attempt=ATTEMPT)
            self.assertFalse(path.exists())


if __name__=="__main__":
    unittest.main()
