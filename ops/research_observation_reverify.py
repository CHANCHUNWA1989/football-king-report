"""Independent deterministic replay of a research-run observation artifact.

Checks downloaded files against expected GitHub run identifiers *provided by the
caller*. The report alone cannot authenticate GitHub metadata, source truth,
chat-message times, executable betting prices, or prospective model skill.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from research_run_observation import MAX_INPUT_BYTES, _pairs, _utc, build

SOURCE_FILE = "research_selections.json"
MANIFEST_FILE = "observation.json"
MAX_MANIFEST_BYTES = 1_000_000


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _read(folder, name, limit):
    p = folder / name
    _require(p.is_file() and not p.is_symlink(), "UNSAFE_ARTIFACT_FILE")
    with p.open("rb") as stream:
        raw = stream.read(limit + 1)
    _require(0 < len(raw) <= limit, "INVALID_ARTIFACT_FILE_SIZE")
    return raw


def verify(folder, *, run_id, attempt, sha):
    """Recompute all observational fields from raw bytes and captured clock."""
    folder = Path(folder)
    _require(folder.is_dir() and not folder.is_symlink(),
             "UNSAFE_ARTIFACT_DIRECTORY")
    _require({p.name for p in folder.iterdir()} ==
             {SOURCE_FILE, MANIFEST_FILE}, "INVALID_ARTIFACT_FILE_INVENTORY")
    raw = _read(folder, SOURCE_FILE, MAX_INPUT_BYTES)
    manifest_raw = _read(folder, MANIFEST_FILE, MAX_MANIFEST_BYTES)
    try:
        manifest = json.loads(manifest_raw, object_pairs_hook=_pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(
                                  ValueError("NONFINITE_JSON_NUMBER")))
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("INVALID_ARTIFACT_MANIFEST") from None
    _require(type(manifest) is dict, "INVALID_ARTIFACT_MANIFEST")
    _require(manifest.get("run_id") == run_id
             and manifest.get("run_attempt") == attempt
             and manifest.get("workflow_source_commit_sha") == sha,
             "GITHUB_RUN_CONTEXT_MISMATCH")
    _require(manifest.get("research_selections_sha256") ==
             hashlib.sha256(raw).hexdigest(), "RAW_RESEARCH_DIGEST_MISMATCH")
    observed = _utc(manifest.get("observed_utc_runner_clock"))
    replayed = build(raw, run_id=run_id, attempt=attempt, sha=sha, now=observed)
    _require(manifest == replayed, "OBSERVATION_REPLAY_MISMATCH")
    _require(manifest["production_recommendations"] == "DISABLED"
             and manifest["certified_forward_samples"] == 0
             and manifest["can_enter_formal_settlement_ledger"] is False
             and manifest["independent_publication_timestamp_verified"] is False,
             "UNSAFE_RESEARCH_OBSERVATION")
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--attempt", required=True)
    p.add_argument("--sha", required=True)
    args = p.parse_args()
    data = verify(args.dir, run_id=args.run_id,
                  attempt=args.attempt, sha=args.sha)
    print(json.dumps({"status": data["status"],
                      "observed_count": data["observed_count"],
                      "reverified_sha256": data["research_selections_sha256"],
                      "certified_forward_samples": 0,
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
