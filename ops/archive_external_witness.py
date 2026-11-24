"""Prepare exact public custody bytes and verify supplied external proofs.
No signing, submission to TSA, network write, permission change or release.
A trusted reviewer must independently provision the signer commit and TSA CA.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone

from ops.archive_custody_subject import build, canonical
from ops.history_blob_retention_preflight import _unique, _valid_sha

REPO = "CHANCHUNWA1989/football-king-report"
SIGNER = REPO + "/.github/workflows/archive-custody-witness.yml"
IDENTITY = "https://github.com/" + SIGNER + "@refs/heads/main"
EXPECTED_DIGEST = "250f37714db76dd78dbb05c275efcb99cbb71f5fb62949c5c4f405a7ddb462e7"
LIMIT = 4 * 1024 * 1024


def run(argv):
    env = dict(os.environ, LC_ALL="C", LANG="C")
    p = subprocess.run(argv, capture_output=True, timeout=60, check=False, env=env)
    if p.returncode or len(p.stdout) > LIMIT:
        raise ValueError("CRYPTOGRAPHIC_TOOL_REJECTED")
    return p.stdout


def read(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file() or not 0 < p.stat().st_size <= LIMIT:
        raise ValueError("UNSAFE_PROOF_FILE")
    return p.read_bytes()


def subject_bytes(path):
    raw = read(path)
    if hashlib.sha256(raw).hexdigest() != EXPECTED_DIGEST:
        raise ValueError("EXACT_SUBJECT_DIGEST_MISMATCH")
    doc = json.loads(raw, object_pairs_hook=_unique)
    if canonical(doc) != raw or doc.get("production_recommendations") != "DISABLED":
        raise ValueError("NONCANONICAL_SUBJECT")
    return raw


def parse_verified_sigstore(output, bundle, digest, signer_sha, now):
    result = json.loads(output, object_pairs_hook=_unique)
    if type(result) is not list or len(result) != 1:
        raise ValueError("AMBIGUOUS_SIGSTORE_RESULT")
    item = result[0]
    if item.get("attestation", {}).get("bundle") != bundle:
        raise ValueError("VERIFIED_BUNDLE_MISMATCH")
    v = item["verificationResult"]
    cert = v["signature"]["certificate"]
    expected = {"issuer": "https://token.actions.githubusercontent.com",
                "subjectAlternativeName": IDENTITY, "buildSignerURI": IDENTITY,
                "sourceRepositoryURI": "https://github.com/" + REPO,
                "sourceRepositoryRef": "refs/heads/main",
                "sourceRepositoryDigest": signer_sha, "buildSignerDigest": signer_sha,
                "runnerEnvironment": "github-hosted"}
    if any(cert.get(k) != value for k, value in expected.items()):
        raise ValueError("SIGNER_IDENTITY_MISMATCH")
    stmt = v["statement"]
    if (stmt.get("_type") != "https://in-toto.io/Statement/v1"
            or stmt.get("predicateType") != "https://slsa.dev/provenance/v1"
            or stmt.get("subject") != [{"name": "custody-subject.json", "digest": {"sha256": digest}}]):
        raise ValueError("SIGNED_SUBJECT_MISMATCH")
    stamps = [s for s in v["verifiedTimestamps"] if s.get("type") == "Tlog"
              and s.get("uri") == "https://rekor.sigstore.dev"]
    if len(stamps) != 1:
        raise ValueError("VERIFIED_REKOR_TIMESTAMP_MISSING")
    t = datetime.fromisoformat(stamps[0]["timestamp"].replace("Z", "+00:00"))
    if t.tzinfo is None or t > now:
        raise ValueError("INVALID_REKOR_TIME")
    return t.astimezone(timezone.utc).isoformat()


def verify_sigstore(subject, bundle_path, signer_sha):
    raw = subject_bytes(subject)
    bundle_raw = read(bundle_path)
    bundle = json.loads(bundle_raw, object_pairs_hook=_unique)
    if not _valid_sha(signer_sha):
        raise ValueError("INVALID_REVIEWED_SIGNER_SHA")
    if bundle.get("mediaType") != "application/vnd.dev.sigstore.bundle.v0.3+json":
        raise ValueError("UNSUPPORTED_BUNDLE")
    output = run(["gh", "attestation", "verify", str(subject), "--bundle", str(bundle_path),
                  "--repo", REPO, "--signer-workflow", SIGNER, "--source-ref", "refs/heads/main",
                  "--source-digest", signer_sha, "--signer-digest", signer_sha,
                  "--deny-self-hosted-runners", "--format", "json"])
    t = parse_verified_sigstore(output, bundle, hashlib.sha256(raw).hexdigest(), signer_sha,
                               datetime.now(timezone.utc))
    if read(subject) != raw or read(bundle_path) != bundle_raw:
        raise ValueError("PROOF_CHANGED_DURING_VERIFICATION")
    return t


def verify_tsa(subject, query, reply, ca, reviewed_ca_sha256):
    """Verify real RFC3161 signature/chain/imprint and request nonce.
    The caller's CA digest is not itself independent TSA policy approval.
    """
    raw, q, r, anchor = map(read, (subject, query, reply, ca))
    if hashlib.sha256(anchor).hexdigest() != reviewed_ca_sha256:
        raise ValueError("TSA_CA_PIN_MISMATCH")
    # Both checks are essential: original request nonce AND exact subject bytes.
    for flag, value in (("-queryfile", query), ("-data", subject)):
        run(["openssl", "ts", "-verify", "-in", str(reply), flag, str(value), "-CAfile", str(ca)])
    details = run(["openssl", "ts", "-reply", "-in", str(reply), "-text"]).decode("ascii")
    stamps = re.findall(r"^Time stamp:\s*(.+?)\s*GMT\s*$", details, re.M)
    if len(stamps) != 1:
        raise ValueError("INVALID_TSA_TIME")
    value = stamps[0]
    fmt = "%b %d %H:%M:%S.%f %Y" if "." in value else "%b %d %H:%M:%S %Y"
    stamp = datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
    if stamp > datetime.now(timezone.utc):
        raise ValueError("FUTURE_TSA_TIME")
    if tuple(map(read, (subject, query, reply, ca))) != (raw, q, r, anchor):
        raise ValueError("PROOF_CHANGED_DURING_VERIFICATION")
    return stamp.isoformat()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--repo", type=Path, required=True)
    prep.add_argument("--manifest", type=Path, required=True)
    prep.add_argument("--candidate", required=True)
    prep.add_argument("--out", type=Path, required=True)
    ver = sub.add_parser("verify")
    for name in ("subject", "bundle", "signer-sha", "query", "reply", "ca", "ca-sha256"):
        ver.add_argument("--" + name, required=True)
    a = p.parse_args()
    report = dict(status="HOLD_EXTERNAL_WITNESS_NOT_CONFIRMED", production_recommendations="DISABLED",
                  independent_archive_retention_verified=False, hosted_archive_write_authorized=False,
                  source_switch_authorized=False, external_signature_verified=False,
                  trusted_timestamp_verified=False)
    try:
        if a.command == "prepare":
            receipt = build(a.repo, json.loads(read(a.manifest), object_pairs_hook=_unique), a.candidate)
            raw = canonical(receipt["subject"])
            if hashlib.sha256(raw).hexdigest() != EXPECTED_DIGEST:
                raise ValueError("UNEXPECTED_CUSTODY_SUBJECT")
            a.out.mkdir(mode=0o700, parents=False, exist_ok=False)
            subject = a.out / "custody-subject.json"
            subject.write_bytes(raw)
            query = a.out / "custody.tsq"
            query.write_bytes(run(["openssl", "ts", "-query", "-data", str(subject), "-sha256", "-cert"]))
            report.update(status="HOLD_EXTERNAL_WITNESS_INPUTS_PREPARED", subject_sha256=EXPECTED_DIGEST)
        else:
            rekor = verify_sigstore(a.subject, a.bundle, a.signer_sha)
            tsa = verify_tsa(a.subject, a.query, a.reply, a.ca, a.ca_sha256)
            report.update(status="HOLD_CRYPTOGRAPHIC_WITNESS_CHECKS_PASSED",
                          sigstore_and_rekor_crypto_verified=True, rfc3161_crypto_verified=True,
                          rekor_utc=rekor, tsa_utc=tsa, subject_sha256=EXPECTED_DIGEST)
            # Independent policy/custody/identity review remains a separate gate.
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
        print(json.dumps(report, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
