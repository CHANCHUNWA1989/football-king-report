"""Preserve untrusted public provenance bytes; this is not a signature verifier.

JSON shapes and the exact file allowlist prevent accidental archival of other
runner files. Neither a bundle nor a verification report authenticates itself.
No prediction, result, qualification flag, or original byte is changed here.
"""
import argparse
import gzip
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path


FILES = (
    "shadow.json", "paired.json", "slate.json", "research.sigstore.json",
    "shadow.verification.json", "paired.verification.json", "slate.verification.json",
    "negative_checks.json", "tampered.rejection.log", "wrong-source.rejection.log",
)
MAX_FILE_BYTES = 8_000_000


def _reject_nonfinite(value):
    raise ValueError("NONFINITE_JSON_VALUE")


def _read_proof(proof):
    if proof.is_symlink() or not proof.is_dir():
        raise ValueError("INVALID_PROOF_DIRECTORY")
    if {p.name for p in proof.iterdir()} != set(FILES):
        raise ValueError("PROVENANCE_FILE_ALLOWLIST_MISMATCH")
    payloads = {}
    for name in FILES:
        path = proof / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("INVALID_PROVENANCE_FILE")
        with path.open("rb") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if not raw or len(raw) > MAX_FILE_BYTES:
            raise ValueError("INVALID_PROVENANCE_FILE_SIZE")
        text = raw.decode("utf-8")
        if name.endswith(".json"):
            value = json.loads(text, parse_constant=_reject_nonfinite)
            if name.endswith(".verification.json"):
                if not isinstance(value, list) or not value or not all(
                        isinstance(item, dict) for item in value):
                    raise ValueError("INVALID_VERIFICATION_REPORT_SHAPE")
            elif not isinstance(value, dict):
                raise ValueError("INVALID_PROVENANCE_JSON_SHAPE")
            if name == "negative_checks.json" and (
                    set(value) != {"tampered_subject_rejected", "wrong_source_digest_rejected"}
                    or any(v is not True for v in value.values())):
                raise ValueError("INVALID_NEGATIVE_CHECK_REPORT_SHAPE")
        elif "\0" in text:
            raise ValueError("INVALID_PROVENANCE_LOG")
        payloads[name] = raw
    return payloads


def _check_existing(target, payloads):
    if {p.name for p in target.iterdir()} != {name + ".gz" for name in FILES}:
        raise ValueError("INCOMPLETE_OR_UNEXPECTED_PROVENANCE_ARCHIVE")
    for name, raw in payloads.items():
        path = target / (name + ".gz")
        if path.is_symlink() or not path.is_file():
            raise ValueError("INVALID_EXISTING_PROVENANCE_FILE")
        try:
            with gzip.open(path, "rb") as stream:
                existing = stream.read(MAX_FILE_BYTES + 1)
        except (OSError, EOFError) as exc:
            raise ValueError("INVALID_EXISTING_PROVENANCE_GZIP") from exc
        if existing != raw:
            raise ValueError("IMMUTABLE_PROVENANCE_ARCHIVE_COLLISION")


def prepare(proof, destination, run_id, attempt, *, day=None):
    """Return created relative paths after an atomic, immutable ten-file batch.

    A complete identical batch is a no-op. Existing incomplete batches or any
    conflicting bytes are rejected without repair or overwrite of old evidence.
    """
    if any(not re.fullmatch(r"[0-9]{1,20}", str(value)) for value in (run_id, attempt)):
        raise ValueError("INVALID_PROVENANCE_RUN_ID")
    if day is None:
        day = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    if not isinstance(day, str) or not re.fullmatch(r"[0-9]{4}/[0-9]{2}/[0-9]{2}", day):
        raise ValueError("INVALID_PROVENANCE_DAY")
    datetime.strptime(day, "%Y/%m/%d")  # Reject impossible calendar dates too.
    payloads = _read_proof(Path(proof))
    destination = Path(destination)
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("INVALID_PROVENANCE_DESTINATION")
    relative = Path("forecast_provenance") / day / (str(run_id) + "-" + str(attempt))
    target = destination / relative
    current = destination
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or (current.exists() and not current.is_dir()):
            raise ValueError("INVALID_PROVENANCE_ARCHIVE_PARENT")
    if target.exists():
        _check_existing(target, payloads)
        return []
    # No mkdir or write happens before every source and target is preflighted.
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".provenance-stage-", dir=target.parent) as stage:
        for name, raw in payloads.items():
            (Path(stage) / (name + ".gz")).write_bytes(gzip.compress(raw, mtime=0))
        os.rename(stage, target)  # Publish all ten files together on this filesystem.
    return [(relative / (name + ".gz")).as_posix() for name in FILES]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--day")
    args = parser.parse_args()
    print(json.dumps({"created": prepare(args.proof, args.destination, args.run_id,
                                         args.attempt, day=args.day)}))


if __name__ == "__main__":
    main()
