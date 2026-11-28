"""Replay only exact pinned archive bytes; no outcome or identity authentication."""
import argparse
import json
from collections import Counter
from pathlib import Path

from ops.forward_evidence_pipeline import audit_batches, MAX_BATCHES
from ops.forward_forecast_binding import FIELDS
from ops.readonly_artifact_verify import verify_artifact


def replay(specs):
    if not isinstance(specs, list) or not 1 <= len(specs) <= MAX_BATCHES:
        raise ValueError("INVALID_PINNED_BATCH_COUNT")
    batches, manifests, seen = [], [], set()
    for path, sha, run, attempt in specs:
        if (run, attempt) in seen:
            raise ValueError("DUPLICATE_PINNED_RUN")
        seen.add((run, attempt))
        doc, manifest, raw = verify_artifact(path, sha, run, attempt,
                                             include_shadow_bytes=True)
        # Do not infer actual kickoff, results, publisher identity or witnesses.
        claims = [{"identity": {k: row.get(k) for k in FIELDS}, "evidence": {}}
                  for row in doc["predictions"]]
        batches.append({"raw": raw, "expected_sha256": manifest["shadow_sha256"],
                        "claims": claims})
        manifests.append(manifest)
    audit = audit_batches(batches)
    if audit["bound_observation_count"] != audit["candidate_count"]:
        raise ValueError("PINNED_ARCHIVE_BINDING_INCOMPLETE")
    if (audit["status"] != "HOLD" or audit["production_recommendations"] != "DISABLED"
            or audit["authenticated_samples"] != 0 or audit["formal_metrics"] is not None):
        raise ValueError("UNSAFE_REPLAY_OUTPUT")
    reasons = Counter(reason for batch in audit["reports"] for row in batch["rows"]
                      for reason in row["reasons"])
    if reasons["INDEPENDENT_VERIFICATION_REQUIRED"] != audit["candidate_count"]:
        raise ValueError("MISSING_INDEPENDENT_VERIFICATION_GATE")
    return {**audit, "schema": "football-king-pinned-binding-replay-v1",
            "verified_archives": manifests, "rejection_reason_counts": dict(reasons),
            "actual_result_evidence_supplied": False, "new_provider_calls": 0}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--artifact", nargs=4, action="append", required=True,
                   metavar=("ZIP", "SHA256", "RUN", "ATTEMPT"))
    p.add_argument("--output", required=True)
    args = p.parse_args()
    result = replay(args.artifact)
    Path(args.output).write_text(json.dumps(result, sort_keys=True, indent=2)+"\n",
                                 encoding="utf-8")


if __name__ == "__main__":
    main()
