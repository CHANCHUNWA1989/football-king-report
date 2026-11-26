"""CLI for independently pinned, research-only football walk-forward diagnostics.

Usage: python ops/run_pinned_walkforward.py --history history.json
       --sha256 <externally-verified-sha256> --model-version v1
"""
import argparse
import json
from pathlib import Path
from offline_admission_report import build_pinned_admission_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--capture-manifest", required=True)
    parser.add_argument("--capture-manifest-sha256", required=True)
    parser.add_argument("--source-receipt", required=True)
    parser.add_argument("--trusted-key-id", required=True)
    parser.add_argument("--trusted-key-registry", required=True)
    parser.add_argument("--trusted-key-registry-sha256", required=True)
    parser.add_argument("--timestamp-evidence", required=True)
    parser.add_argument("--timestamp-evidence-sha256", required=True)
    parser.add_argument("--timestamp-attestation", required=True)
    parser.add_argument("--timestamp-attestation-sha256", required=True)
    parser.add_argument("--rfc3161-token", required=True)
    parser.add_argument("--tsa-ca-bundle", required=True)
    parser.add_argument("--tsa-ca-bundle-sha256", required=True)
    parser.add_argument("--min-train", type=int, default=60)
    parser.add_argument("--test-size", type=int, default=30)
    parser.add_argument("--step-size", type=int, default=30)
    parser.add_argument("--embargo-hours", type=int, default=24)
    args = parser.parse_args(argv)
    try:
        source = Path(args.source_receipt)
        if source.stat().st_size > 100_000:
            raise ValueError("oversized receipt")
        with source.open("rb") as stream:
            raw = stream.read(100_001)
        if len(raw) > 100_000:
            raise ValueError("oversized receipt")
        receipt = json.loads(raw)
    except (OSError, ValueError, TypeError, RecursionError, UnicodeDecodeError):
        receipt = None
    report = build_pinned_admission_report(
        args.history, expected_sha256=args.sha256,
        expected_model_version=args.model_version,
        manifest_path=args.capture_manifest,
        expected_manifest_sha256=args.capture_manifest_sha256,
        min_train=args.min_train, test_size=args.test_size,
        step_size=args.step_size, embargo_hours=args.embargo_hours,
        source_receipt=receipt,
        trusted_key_id=args.trusted_key_id,
        trusted_registry_path=args.trusted_key_registry,
        trusted_registry_sha256=args.trusted_key_registry_sha256,
        timestamp_evidence_path=args.timestamp_evidence,
        timestamp_evidence_sha256=args.timestamp_evidence_sha256,
        timestamp_attestation_path=args.timestamp_attestation,
        timestamp_attestation_sha256=args.timestamp_attestation_sha256,
        rfc3161_token_path=args.rfc3161_token,
        tsa_ca_bundle_path=args.tsa_ca_bundle,
        tsa_ca_bundle_sha256=args.tsa_ca_bundle_sha256)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "RESEARCH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
