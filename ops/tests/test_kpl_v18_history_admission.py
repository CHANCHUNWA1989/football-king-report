"""KPL V18 only synthetic records, ephemeral test keys, no licensed KPL rows."""
import base64
import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ops.tests.test_kpl_v17_elo_replay import BASE, rows, iso
from research.kpl_v11_forecast_archive import archive_forecast, _digest
from research.kpl_v14_signed_anchor import (
    build_unsigned_anchor_payload, canonical_signed_message)
from research.kpl_v17_elo_replay import replay_elo_shadow
from research.kpl_v18_history_admission import audit_history_intake, SOURCE_FIELDS


def ts_add(value, *, minutes=0, seconds=0):
    return iso(datetime.fromisoformat(value.replace("Z","+00:00"))
               + timedelta(minutes=minutes,seconds=seconds))


class TestKPLV18Admission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temps = tempfile.TemporaryDirectory(prefix="kpl18-synthetic-")
        d = Path(cls.temps.name)
        key, pub = d/"simkey.pem", d/"simkeypub.pem"
        subprocess.run(["openssl","genpkey","-algorithm","Ed25519",
                        "-out",str(key)],check=True,capture_output=True)
        subprocess.run(["openssl","pkey","-in",str(key),"-pubout",
                        "-out",str(pub)],check=True,capture_output=True)
        cls.private = key
        pem=pub.read_text()
        der=subprocess.run(["openssl","pkey","-pubin","-inform","PEM",
                            "-outform","DER"],input=pem.encode(),capture_output=True,
                           check=True).stdout
        cls.trust={"synthetic-test-only-key":{
            "public_key_pem":pem,"spki_sha256":hashlib.sha256(der).hexdigest()}}
        cls.history=rows()
        cls.packets=[]
        for row in cls.history:
            original={key:row[key] for key in SOURCE_FIELDS}
            raw=json.dumps(original,sort_keys=True,separators=(",",":"))
            row["source_record_sha256"]=hashlib.sha256(raw.encode()).hexdigest()
            cls.packets.append({
                "series_id":row["series_id"],"game_number":row["game_number"],
                "source_id":row["source_id"],
                "source_url":"https://fixture.example.test/result/"
                             +row["series_id"]+"/"+str(row["game_number"]),
                "published_at":ts_add(row["result_observed_at"],seconds=-10),
                "captured_at":ts_add(row["result_observed_at"],minutes=1),
                "raw_record_json":raw})
        cls.frozen=iso(BASE-timedelta(days=1))
        cls.universe=[f"synthetic-bo-{i}" for i in range(4)]
        cls.claim={
            "provider_id":"simulated-data-provider","source_hostname":"fixture.example.test",
            "license_reference":"synthetic-unverified-contract-ref",
            "grant_document_sha256":"f"*64,
            "granted_use":["RESEARCH_BACKTEST"],
            "grant_expires_at":iso(BASE+timedelta(days=100)),
            "grant_observed_at":iso(BASE-timedelta(days=2))}
        cls.archive=d/"synthetic-forecasts.jsonl"
        computed=replay_elo_shadow(
            cls.history,model_frozen_at=cls.frozen,
            registered_series_ids=cls.universe,universe_registered_at=cls.frozen,
            train_fraction=0.5,min_test_series=1,min_test_maps=4,repetitions=200)
        fullp={(x["series_id"],x["game_number"]):x["probability_a"]
               for x in computed["all_forecasts"]}
        for row in cls.history:
            p=fullp[(row["series_id"],row["game_number"])]
            forecast={
                "prediction_id":f"{row['series_id']}-{row['game_number']}",
                "series_id":row["series_id"],"game_number":row["game_number"],
                "team_ids":[row["team_a"],row["team_b"]],
                "predicted_team_id":row["team_a"],"probability":p,
                "model_version":"synthetic-frozen-elo-v1",
                "phase":"PRE_GAME",
                "info_cutoff_at":ts_add(row["forecast_at"],seconds=-20),
                "forecast_at":row["forecast_at"],"game_start_at":row["game_start_at"],
                "status":"RESEARCH_ONLY",
                "evidence":[{
                    "source_id":"simulated-pre-game-data",
                    "kind":"team_form","subject_game":0,
                    "published_at":ts_add(row["forecast_at"],minutes=-3),
                    "captured_at":ts_add(row["forecast_at"],minutes=-2)}]}
            archive_forecast(cls.archive,forecast)
        cls.envelopes=[]
        for i,row in enumerate(cls.history,1):
            payload=build_unsigned_anchor_payload(
                cls.archive,i,witnessed_at=ts_add(row["forecast_at"],minutes=1),
                nonce=f"synthetic-v18-nonce-{i:04d}-fixed")
            msg=d/"message.bin"
            sig=d/"signature.bin"
            msg.write_bytes(canonical_signed_message(payload))
            subprocess.run(["openssl","pkeyutl","-sign","-rawin",
                            "-inkey",str(cls.private),"-in",str(msg),
                            "-out",str(sig)],check=True,capture_output=True)
            cls.envelopes.append({
                "payload":payload,"key_id":"synthetic-test-only-key",
                "signature_b64":base64.b64encode(sig.read_bytes()).decode()})

    @classmethod
    def tearDownClass(cls):
        cls.temps.cleanup()

    def check(self, *, history=None, packets=None, archive=None,
              envelopes=None, trust=None, claim=None, **kw):
        params={
            "model_frozen_at":self.frozen,
            "expected_model_version":"synthetic-frozen-elo-v1",
            "registered_series_ids":self.universe,
            "universe_registered_at":self.frozen,
            "train_fraction":0.5,"min_test_series":1,"min_test_maps":4}
        params.update(kw)
        return audit_history_intake(
            history if history is not None else self.history,
            packets if packets is not None else self.packets,
            archive if archive is not None else self.archive,
            envelopes if envelopes is not None else self.envelopes,
            trust if trust is not None else self.trust,
            claim if claim is not None else self.claim, **params)

    def test_complete_synthetic_pack_never_becomes_real_kpl_accuracy(self):
        r=self.check()
        self.assertTrue(r["technical_preflight_passed"],r)
        self.assertTrue(r["source_packet_integrity_passed"])
        self.assertTrue(r["forecast_archive_linkage_passed"])
        self.assertTrue(r["pinned_signed_receipt_coverage_passed"])
        self.assertTrue(r["archived_elo_probabilities_match_prequential_replay"])
        self.assertEqual(r["map_count"],16)
        self.assertEqual(r["status"],"HOLD")
        self.assertFalse(r["licence_independently_verified"])
        self.assertFalse(r["independent_pregame_existence_verified"])
        self.assertFalse(r["real_kpl_accuracy_verified"])
        self.assertFalse(r["positive_ev_verified"])
        self.assertFalse(r["eligible_for_real_kpl_performance_claims"])

    def test_replay_metrics_only_labelled_synthetic(self):
        r=self.check()
        self.assertEqual(r["synthetic_diagnostic_metrics_only"]["test_maps"],8)
        self.assertEqual(r["source_class"],"SYNTHETIC")

    def test_license_claim_completeness_not_real_permission(self):
        claim=copy.deepcopy(self.claim)
        claim["license_reference"]="some-alleged-official-licence"
        r=self.check(claim=claim)
        self.assertTrue(r["rights_documentary_claim_fields_complete"])
        self.assertFalse(r["licence_independently_verified"])
        self.assertEqual(r["status"],"HOLD")

    def test_unavailable_documentary_claim_fails_technical(self):
        claim=copy.deepcopy(self.claim)
        claim.pop("grant_document_sha256")
        r=self.check(claim=claim)
        self.assertIn("NO_COMPLETE_PRE_FORECAST_RIGHTS_DOCUMENTARY_CLAIM",r["reasons"])
        self.assertFalse(r["technical_preflight_passed"])

    def test_unverified_public_cannot_claim_real_metrics(self):
        h=copy.deepcopy(self.history)
        for row in h:
            row["source_class"]="LICENSED_OFFLINE_CLAIM"
        r=self.check(history=h)
        self.assertTrue(r["technical_preflight_passed"],r)
        self.assertIsNone(r["synthetic_diagnostic_metrics_only"])
        self.assertFalse(r["real_kpl_accuracy_verified"])

    def test_bad_raw_source_hash_fails(self):
        packets=copy.deepcopy(self.packets)
        packets[0]["raw_record_json"]+=' '
        r=self.check(packets=packets)
        self.assertIn("SOURCE_BYTES_HASH_MISMATCH",r["reasons"])

    def test_mismatched_source_result_even_with_new_hash_fails(self):
        packets=copy.deepcopy(self.packets)
        history=copy.deepcopy(self.history)
        decoded=json.loads(packets[0]["raw_record_json"])
        decoded["winner_team_id"]="team-B"
        raw=json.dumps(decoded,sort_keys=True,separators=(",",":"))
        packets[0]["raw_record_json"]=raw
        history[0]["source_record_sha256"]=hashlib.sha256(raw.encode()).hexdigest()
        r=self.check(history=history,packets=packets)
        self.assertIn("SOURCE_MATCH_GAME_RESULT_MISMATCH",r["reasons"])

    def test_publisher_time_after_result_first_seen_rejected(self):
        packets=copy.deepcopy(self.packets)
        packets[0]["published_at"]=ts_add(
            self.history[0]["result_observed_at"],minutes=2)
        r=self.check(packets=packets)
        self.assertIn("SOURCE_POST_EVENT_TIME_MISMATCH",r["reasons"])

    def test_fake_similar_official_domain_fails(self):
        packets=copy.deepcopy(self.packets)
        packets[0]["source_url"]="https://fixture.example.test.evil.org/data"
        r=self.check(packets=packets)
        self.assertIn("SOURCE_ID_OR_HOST_MISMATCH",r["reasons"])

    def test_malformed_packet_identity_fails_closed(self):
        packets=copy.deepcopy(self.packets)
        packets[0]["series_id"]=[]
        r=self.check(packets=packets)
        self.assertIn("INVALID_PACKET_IDENTITY_TYPE",r["reasons"])

    def test_duplicate_packet_fails(self):
        packets=copy.deepcopy(self.packets)
        packets[-1]=copy.deepcopy(packets[0])
        r=self.check(packets=packets)
        self.assertIn("DUPLICATE_OR_UNKNOWN_SOURCE_GAME",r["reasons"])

    def test_missing_complete_series_fails(self):
        h=[x for x in self.history if x["series_id"]!="synthetic-bo-3"]
        p=[x for x in self.packets if x["series_id"]!="synthetic-bo-3"]
        r=self.check(history=h,packets=p)
        self.assertIn("UNREGISTERED_OR_CHANGED_SERIES_UNIVERSE",r["reasons"])

    def test_unregistered_before_forecast_rejected(self):
        r=self.check(universe_registered_at=iso(BASE+timedelta(days=1)))
        self.assertIn("UNREGISTERED_OR_CHANGED_SERIES_UNIVERSE",r["reasons"])

    def test_missing_local_archive_fails(self):
        r=self.check(archive=Path(self.temps.name)/"absent.jsonl")
        self.assertIn("MISSING_OR_MISMATCHED_PRE_GAME_FORECAST_ARCHIVE",r["reasons"])

    def test_missing_signed_receipts_fails(self):
        r=self.check(envelopes=[])
        self.assertIn("INCOMPLETE_OR_INVALID_PINNED_SIGNED_RECEIPTS",r["reasons"])

    def test_tampered_signature_fails(self):
        envelopes=copy.deepcopy(self.envelopes)
        envelopes[0]["signature_b64"]=base64.b64encode(bytes(64)).decode()
        r=self.check(envelopes=envelopes)
        self.assertFalse(r["pinned_signed_receipt_coverage_passed"])

    def test_untrusted_keyring_fails(self):
        r=self.check(trust={})
        self.assertFalse(r["pinned_signed_receipt_coverage_passed"])
        self.assertEqual(r["status"],"HOLD")

    def test_different_frozen_model_version_fails(self):
        r=self.check(expected_model_version="renamed-after-the-game")
        self.assertIn("MISSING_OR_MISMATCHED_PRE_GAME_FORECAST_ARCHIVE",r["reasons"])

    def test_expired_rights_mid_history_rejected(self):
        claim=copy.deepcopy(self.claim)
        claim["grant_expires_at"]=iso(BASE+timedelta(days=2))
        r=self.check(claim=claim)
        self.assertIn("NO_COMPLETE_PRE_FORECAST_RIGHTS_DOCUMENTARY_CLAIM",r["reasons"])
        self.assertFalse(r["technical_preflight_passed"])

    def test_rights_cover_latest_forecast_boundary(self):
        claim=copy.deepcopy(self.claim)
        claim["grant_expires_at"]=max(row["forecast_at"] for row in self.history)
        r=self.check(claim=claim)
        self.assertTrue(r["rights_documentary_claim_fields_complete"])

    def test_resigned_training_probability_forgery_rejected(self):
        # Adversarial test: attacker rewrites all local hash entries AND
        # re-signs every receipt with a synthetic test key. A V18 check
        # covering test maps only previously missed this altered train map.
        with tempfile.TemporaryDirectory() as d:
            d=Path(d)
            path=d/"rewritten-and-resigned.jsonl"
            entries=[json.loads(line) for line in self.archive.read_text().splitlines()]
            entries[0]["forecast"]["probability"]=0.99
            previous="0"*64
            for entry in entries:
                entry["previous_hash"]=previous
                entry["entry_hash"]=_digest(previous,entry["forecast"])
                previous=entry["entry_hash"]
            path.write_text("".join(
                json.dumps(e,sort_keys=True,separators=(",",":"))+"\n"
                for e in entries))
            resigned=[]
            msg=d/"message.bin"
            sig=d/"signature.bin"
            for i,row in enumerate(self.history,1):
                payload=build_unsigned_anchor_payload(
                    path,i,witnessed_at=ts_add(row["forecast_at"],minutes=1),
                    nonce=f"synthetic-v19-nonce-{i:04d}-fixed")
                msg.write_bytes(canonical_signed_message(payload))
                subprocess.run(["openssl","pkeyutl","-sign","-rawin",
                                "-inkey",str(self.private),"-in",str(msg),
                                "-out",str(sig)],check=True,capture_output=True)
                resigned.append({
                    "payload":payload,"key_id":"synthetic-test-only-key",
                    "signature_b64":base64.b64encode(sig.read_bytes()).decode()})
            r=self.check(archive=path,envelopes=resigned)
            self.assertFalse(r["technical_preflight_passed"])
            self.assertIn("SEALED_FORECAST_DISAGREES_WITH_ELO_REPLAY",r["reasons"])

    def test_pre_game_prob_rewritten_with_valid_local_hash_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"mutated_archive.jsonl"
            entries=[json.loads(x) for x in self.archive.read_text().splitlines()]
            entries[-1]["forecast"]["probability"]=0.99
            previous="0"*64
            for entry in entries:
                entry["previous_hash"]=previous
                entry["entry_hash"]=_digest(previous,entry["forecast"])
                previous=entry["entry_hash"]
            path.write_text("".join(
                json.dumps(e,sort_keys=True,separators=(",",":"))+"\n"
                for e in entries))
            r=self.check(archive=path)
            self.assertIn("SEALED_FORECAST_DISAGREES_WITH_ELO_REPLAY",r["reasons"])
            self.assertFalse(r["archived_elo_probabilities_match_prequential_replay"])
            self.assertFalse(r["pinned_signed_receipt_coverage_passed"])


if __name__=="__main__":
    unittest.main()
