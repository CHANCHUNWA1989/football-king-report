"""Real local RFC3161 crypto roundtrip and adversarial diagnostic fixtures."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from ops.archive_external_witness import run, verify_tsa, parse_verified_sigstore, IDENTITY, REPO
from ops.german_schedule_gap import diagnose


class WitnessTests(unittest.TestCase):
    def test_real_local_tsa_signature_nonce_and_tamper(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            root, key, cert, tsa_key, csr, ext, conf, serial, subject, query, reply = [
                p / n for n in ("root.pem","root.key","tsa.pem","tsa.key","tsa.csr","ext","tsa.cnf","serial","subject","query","reply")]
            run(["openssl","req","-x509","-newkey","rsa:2048","-nodes","-days","2","-subj","/CN=LOCAL TEST ROOT",
                 "-keyout",str(key),"-out",str(root),"-addext","basicConstraints=critical,CA:TRUE",
                 "-addext","keyUsage=critical,keyCertSign,cRLSign"])
            run(["openssl","req","-new","-newkey","rsa:2048","-nodes","-subj","/CN=LOCAL TEST TSA",
                 "-keyout",str(tsa_key),"-out",str(csr)])
            ext.write_text("basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=critical,timeStamping\n")
            run(["openssl","x509","-req","-in",str(csr),"-CA",str(root),"-CAkey",str(key),
                 "-CAcreateserial","-out",str(cert),"-days","1","-extfile",str(ext)])
            serial.write_text("01\n")
            conf.write_text("[tsa]\ndefault_tsa=tsa_config1\n[tsa_config1]\nserial="+str(serial)+
                "\ncrypto_device=builtin\nsigner_cert="+str(cert)+"\ncerts="+str(root)+
                "\nsigner_key="+str(tsa_key)+"\nsigner_digest=sha256\ndefault_policy=1.2.3.4.1\n"+
                "digests=sha256\naccuracy=secs:1\nordering=no\ntsa_name=yes\ness_cert_id_chain=no\n")
            subject.write_bytes(b"LOCAL SYNTHETIC TEST ONLY")
            query.write_bytes(run(["openssl","ts","-query","-data",str(subject),"-sha256","-cert"]))
            run(["openssl","ts","-reply","-config",str(conf),"-queryfile",str(query),"-out",str(reply)])
            pin = hashlib.sha256(root.read_bytes()).hexdigest()
            self.assertTrue(verify_tsa(subject, query, reply, root, pin))
            with self.assertRaises(ValueError):
                verify_tsa(subject, query, reply, root, "0"*64)
            query.write_bytes(run(["openssl","ts","-query","-data",str(subject),"-sha256","-cert"]))
            with self.assertRaises(ValueError):
                verify_tsa(subject, query, reply, root, pin)
            subject.write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                verify_tsa(subject, query, reply, root, pin)

    def test_sigstore_parser_rejects_missing_rekor_and_wrong_identity(self):
        sha, digest, bundle = "a"*40, "b"*64, {"fixture": True}
        cert = dict(issuer="https://token.actions.githubusercontent.com", subjectAlternativeName=IDENTITY,
                    buildSignerURI=IDENTITY, sourceRepositoryURI="https://github.com/"+REPO,
                    sourceRepositoryRef="refs/heads/main", sourceRepositoryDigest=sha,
                    buildSignerDigest=sha, runnerEnvironment="github-hosted")
        v = dict(signature={"certificate":cert}, statement={"_type":"https://in-toto.io/Statement/v1",
            "predicateType":"https://slsa.dev/provenance/v1","subject":[{"name":"custody-subject.json","digest":{"sha256":digest}}]},
            verifiedTimestamps=[{"type":"Tlog","uri":"https://rekor.sigstore.dev","timestamp":"2026-11-24T00:00:00Z"}])
        now = datetime(2026,11,24,12,tzinfo=timezone.utc)
        def check():
            return parse_verified_sigstore(json.dumps([{"attestation":{"bundle":bundle},"verificationResult":v}]),bundle,digest,sha,now)
        self.assertTrue(check())
        v["verifiedTimestamps"] = []
        with self.assertRaises(ValueError):
            check()
        v["verifiedTimestamps"] = [{"type":"Tlog","uri":"https://rekor.sigstore.dev","timestamp":"2026-11-24T00:00:00Z"}]
        cert["sourceRepositoryRef"] = "refs/heads/fake"
        with self.assertRaises(ValueError):
            check()


class ScheduleTests(unittest.TestCase):
    def test_real_observed_time_shape_and_no_false_provider_blame(self):
        d = {"schema":"football-king-openligadb-hourly-v1","collected_utc":"2026-11-24T02:20:13Z","production_recommendations":"DISABLED"}
        r = dict(id=45311544639,path=".github/workflows/football-king-german-live.yml",head_branch="main",
                 created_at="2026-11-24T02:19:41Z",status="completed",conclusion="success")
        now = datetime(2026,11,24,12,32,tzinfo=timezone.utc)
        x = diagnose(d,r,now)
        self.assertEqual(x["status"],"HOLD_NO_RECENT_RUN_IN_OBSERVED_INVENTORY")
        self.assertFalse(x["provider_failure_proven"])
        self.assertFalse(x["fallback_allowed"])
        r["created_at"]="2026-11-24T12:00:00Z"
        self.assertEqual(diagnose(d,r,now)["status"],"HOLD_RECENT_RUN_BUT_STALE_PUBLISHED_POINTER")
        r["conclusion"]="failure"
        self.assertEqual(diagnose(d,r,now)["status"],"HOLD_LATEST_RUN_FAILED")


if __name__ == "__main__":
    unittest.main()
