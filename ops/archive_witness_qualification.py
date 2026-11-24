"""Custody provider qualification inventory. No applicant-supplied trust or release."""
import argparse
import json
from pathlib import Path
from ops.history_blob_retention_preflight import _git, _valid_sha, RetentionHold

SIGNER_PATH = ".github/workflows/archive-custody-witness.yml"
CANDIDATES = {
    "github_sigstore_public_good": "https://docs.github.com/en/actions/concepts/security/artifact-attestations",
    "digicert_rfc3161": "https://knowledge.digicert.com/general-information/rfc3161-compliant-time-stamp-authority-server",
    "freetsa_rfc3161": "https://www.freetsa.org/freetsa_cps.html",
}


def inspect(repo, sha):
    if not _valid_sha(sha) or _git(repo, "cat-file", "-t", sha, limit=64).strip() != b"commit":
        raise ValueError("INVALID_SIGNER_REPOSITORY_PIN")
    tree = _git(repo, "ls-tree", "-z", sha, "--", SIGNER_PATH, limit=4096)
    # Existence is not approval. No caller-provided boolean or CA hash grants trust.
    return dict(status="HOLD_WITNESS_PROVIDER_QUALIFICATION_INCOMPLETE", main_sha=sha,
                candidate_documentation=CANDIDATES, signer_workflow_present=bool(tree),
                signer_exact_head_independent_review_verified=False,
                sigstore_trust_root_reviewed=False, rekor_inclusion_verified=False,
                tsa_policy_oid_approved=False, tsa_ca_independently_pinned=False,
                tsa_revocation_policy_reviewed=False, tsa_external_response_verified=False,
                independent_retention_verified=False, hosted_archive_write_authorized=False,
                source_switch_authorized=False, production_recommendations="DISABLED")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--main-sha", required=True)
    a = p.parse_args()
    try:
        print(json.dumps(inspect(a.repo, a.main_sha), sort_keys=True))
    except (ValueError, OSError, RuntimeError):
        print(json.dumps(dict(status="HOLD_WITNESS_QUALIFICATION_UNVERIFIABLE", production_recommendations="DISABLED")))
        return 1
    return 0  # observation only


if __name__ == "__main__":
    raise SystemExit(main())
