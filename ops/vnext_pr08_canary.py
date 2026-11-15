"""PR-08 synthetic-only Sigstore signer canary producer.

NOT a real forecast, official result, authorized provider feed, tradable quote,
or an eligible out-of-sample observation. No network IO or secret credentials.
The timestamp is merely the runner's local clock until external attestation.
"""
import argparse
import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from vnext_prospective_local_seal import read_forecast_seal, seal_forecast_pair

SYNTHETIC_PREFIX = "synthetic-pr08-canary-"
RIGHTS = "DERIVED_METADATA_ONLY_UNVERIFIED"


def _z(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_canary(root, run_id, attempt, *, now=None):
    """Generate one isolated, visibly synthetic local seal; never certify it."""
    if type(run_id) is not int or type(attempt) is not int or not 0 < run_id < 10**15 or not 0 < attempt < 1000:
        raise ValueError("INVALID_CANARY_RUN_IDENTITY")
    if now is None:
        now = datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ValueError("CANARY_REQUIRES_UTC")
    now = now.astimezone(timezone.utc)
    root = Path(root)
    if root.exists() or root.is_symlink():
        raise ValueError("CANARY_OUTPUT_MUST_BE_NEW")
    root.mkdir(mode=0o700)
    as_of = now - timedelta(seconds=30)
    kickoff = now + timedelta(hours=3)  # Fictional; NEVER a verified real kickoff.
    fixture_id = f"{SYNTHETIC_PREFIX}{run_id}-{attempt}"
    pair = {
        "fixture_id": fixture_id,
        "kickoff_utc": _z(kickoff),
        "as_of_utc": _z(as_of),
        "models": {
            key: {
                "model_id": "synthetic-canary-" + key,
                "forecast_utc": _z(as_of),
                "inputs_available_utc": _z(as_of - timedelta(seconds=30)),
                "input_sha256": _digest("SYNTHETIC INPUT " + key),
                "probabilities_1x2": [0.40, 0.30, 0.30] if key == "baseline" else [0.41, 0.30, 0.29],
                "calibrated": False,
                "production_recommendations": "DISABLED",
            }
            for key in ("baseline", "challenger")
        },
    }
    refs = [{
        "provider": "synthetic-pr08-provider",
        "source_event_id": "fictional-fixture",
        "source_group": "synthetic-not-an-independent-source",
        "source_updated_utc": _z(as_of - timedelta(seconds=15)),
        "received_utc": _z(as_of - timedelta(seconds=10)),
        "available_utc": _z(as_of - timedelta(seconds=5)),
        "raw_sha256": _digest("SYNTHETIC SOURCE; NO PROVIDER DATA"),
        "rights_scope": RIGHTS,
    }]
    seal = seal_forecast_pair(root, pair, refs, captured_utc=_z(now))
    read_forecast_seal(root, seal["file_name"], expected_sha256=seal["content_sha256"])
    return {
        "synthetic_test_only": True,
        "eligible_for_model_scoring": False,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
        "root": str(root.resolve()),
        "subject_path": str((root / seal["file_name"]).resolve()),
        "file_name": seal["file_name"],
        "sha256": seal["content_sha256"],
        "fixture_id": fixture_id,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--attempt", required=True, type=int)
    args = parser.parse_args()
    report = generate_canary(args.root, args.run_id, args.attempt)
    print("Created SYNTHETIC TEST ONLY seal; NO real prediction, rights, OOS or EV.")
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as stream:
            for key in ("root", "subject_path", "file_name", "sha256"):
                stream.write(f"{key}={report[key]}\n")


if __name__ == "__main__":
    main()
