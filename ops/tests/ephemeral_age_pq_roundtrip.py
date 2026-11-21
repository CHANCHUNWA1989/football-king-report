"""Execute real age v1.3.2 PQ encryption/decryption on EPHEMERAL synthetic bytes.

Each run uses a brand new throwaway PQ identity generated inside a private
TemporaryDirectory; neither key, ciphertext, raw sources nor secret paths are
printed or uploaded. Only an aggregate verification status reaches CI logs.

The real 2026-11-08 sealed evidence cannot be decrypted by this new key.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

from ops import identity_ab_two_source_custody as custody
from ops import identity_ab_two_source_authorized_replay as authorized
from ops import private_response_relay as relay
from ops.tests.test_identity_ab_two_source_custody import (
    source_proof, COMMIT, RUN, ATTEMPT,
)


def _run(argv, *, stdout=subprocess.DEVNULL):
    response=subprocess.run(argv,stdin=subprocess.DEVNULL,
                            stdout=stdout,stderr=subprocess.DEVNULL,
                            check=False,timeout=35)
    if response.returncode:
        raise RuntimeError("PINNED_EPHEMERAL_PQ_CRYPTO_FAILURE")
    return response.stdout


def prove(age_binary, age_keygen):
    with tempfile.TemporaryDirectory(prefix="football-pq-ephemeral-") as folder:
        root=Path(folder)
        vault=root/"vault"
        vault.mkdir(mode=0o700)
        secret=vault/"ephemeral-identity.txt"
        _run([str(age_keygen),"-pq","-o",str(secret)])
        public=_run([str(age_keygen),"-y",str(secret)],
                    stdout=subprocess.PIPE).decode("ascii").strip()
        relay._recipient(public)
        recipient_file=root/"recipient.txt"
        fd=os.open(recipient_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as file:
            file.write((public+"\n").encode("ascii"))
        archive=root/"custody"
        src,meta,report=source_proof()
        custody.capture(archive,src,meta,report=report,
                        source_commit=COMMIT,run_id=RUN,attempt=ATTEMPT,
                        age_binary=age_binary,recipient_path=recipient_file)
        # This SYNTHETIC temp archive cannot match the fixed real 2026-11-08
        # index pin. We bypass ONLY that hardcoded real-archive pin and leave
        # native age decrypt, strict envelope, original SHA and JSON intact.
        import hashlib
        proof={
            "public_source_ciphertext_integrity_verified":True,
            "verified_public_files":5,
            "private_decryption_verified":False,
            "certified_scored_case_count":0,
            "original_source_raw_sha256":{
                provider:hashlib.sha256(raw).hexdigest()
                for provider,raw in src.items()
            },
        }
        original_index=authorized._git_blob((archive/"index.json").read_bytes())
        with patch.object(authorized,"verify_public",return_value=proof), \
             patch.object(authorized,"INDEX_GIT_BLOB_SHA1",original_index):
            result=authorized.replay(
                archive,identity_path=secret,age_binary=age_binary)
        if (result["sources_verified"]!=2
                or result["original_source_bytes_decrypted_and_replayed"] is not True
                or result["certified_scored_cases"]!=0
                or result["production_recommendations"]!="DISABLED"):
            raise RuntimeError("PINNED_EPHEMERAL_PQ_REPLAY_INCOMPLETE")
        for name,source_bytes in src.items():
            import hashlib
            if result["source_byte_proofs"][name]["source_raw_sha256"] != hashlib.sha256(
                    source_bytes).hexdigest():
                raise RuntimeError("PINNED_EPHEMERAL_PQ_SOURCE_SHA_MISMATCH")
        return {
            "status":"SYNTHETIC_ONLY_NATIVE_AGE_PQ_ROUNDTRIP_OK",
            "age_version":"v1.3.2",
            "ephemeral_only_keys_created":True,
            "synthetic_source_byte_replays":2,
            "real_historical_source_decryption_verified":False,
            "private_identity_disclosed_or_uploaded":False,
            "official_ft_authenticated":False,
            "certified_scored_cases":0,
            "production_recommendations":"DISABLED",
        }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--age-binary",type=Path,required=True)
    parser.add_argument("--keygen-binary",type=Path,required=True)
    a=parser.parse_args(argv)
    try:
        result=prove(a.age_binary,a.keygen_binary)
        print(json.dumps(result,sort_keys=True))
        return 0
    except Exception:
        # Never print subprocess stderr/stdout, private key, raw data or paths.
        print(json.dumps({
            "status":"HOLD","reason":"SYNTHETIC_NATIVE_PQ_ROUNDTRIP_FAILED",
            "real_historical_source_decryption_verified":False,
            "certified_scored_cases":0,
            "production_recommendations":"DISABLED",
        },sort_keys=True))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
