"""One verified historical StatsBomb open-data match — offline research only.

Pins exact two provider JSON files from one immutable public GitHub commit;
does not download/scrape data, does not store data in GitHub or CI, does not
train models, publish predictions, supply odds, or approve data licensing.
The provider README allows public football research with attribution, but
does not establish rights for commercial prediction/betting use.
"""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys

from ops.optional_kloppy_event_research import (
    SCHEMA, summarize_local_event_dataset,
)

UPSTREAM_REPO = "hudl/open-data"
UPSTREAM_COMMIT = "4b73468fc5b0f1950f9f66fada70ad3a4f9327cb"
MATCH_ID = "3788741"
EVENTS_SHA256 = "b9ddce6bee771bdb1f3564c9ac0552619257e412d0767939f1e7f1500ace3062"
LINEUPS_SHA256 = "5874bcd25f9c75b12ebcf14b1fa46507a349ac4de822ffe07f876d2edbe0cfca"
EVENTS_BYTES = 3208593
LINEUPS_BYTES = 19491
PROVIDER_README = (
    "https://github.com/hudl/open-data/blob/"
    + UPSTREAM_COMMIT + "/README.md"
)
# These are historical research claim timestamps, not an independently signed
# original capture, pre-match observation time, or a license authorization.
SOURCE_AVAILABLE_CLAIM_UTC = "2026-11-12T17:17:15Z"
RESEARCH_AS_OF_UTC = "2026-11-15T05:58:00Z"


def _read_fixed_file(path, expected_bytes, expected_sha256):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("SOURCE_MUST_BE_LOCAL_REGULAR_FILE")
    if path.stat().st_size != expected_bytes:
        raise ValueError("OFFICIAL_SAMPLE_SIZE_MISMATCH")
    raw = path.read_bytes()
    if len(raw) != expected_bytes or sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("OFFICIAL_SAMPLE_SHA256_MISMATCH")
    return raw


def summarize_verified_statsbomb_open_data(events_path, lineups_path):
    """Read the exact archived provider bytes and test real Kloppy contract.

    Only calls a local package loader *after* both digests match the
    immutable upstream files. BytesIO freezes the bytes between the hash
    preflight and parsing so a changed path cannot cause a TOCTOU swap.
    """
    events_bytes = _read_fixed_file(events_path, EVENTS_BYTES, EVENTS_SHA256)
    lineup_bytes = _read_fixed_file(lineups_path, LINEUPS_BYTES, LINEUPS_SHA256)

    # Runtime-only optional third-party import; never a default VNext CI dep.
    from kloppy import statsbomb
    dataset = statsbomb.load(
        event_data=BytesIO(events_bytes),
        lineup_data=BytesIO(lineup_bytes),
    )
    native_id = getattr(dataset.metadata, "game_id", None)
    if native_id not in (None, MATCH_ID):
        raise ValueError("MISMATCHED_NATIVE_MATCH_ID")
    if native_id is None:
        # Kloppy 3.19.1 has no game ID in provider-local event/lineup JSON.
        # metadata is mutable; setting the verified source ID *in place*
        # preserves the identity of each record.dataset. Passing this via
        # additional_metadata creates a shallow dataset wrapper and leaves
        # event.dataset pointing at the older parent. Do not use that path.
        dataset.metadata.game_id = MATCH_ID

    result = summarize_local_event_dataset(dataset, {
        "schema": SCHEMA,
        "source_namespace": "statsbomb_open_data_research",
        "source_event_id": MATCH_ID,
        "rights_reference_url": PROVIDER_README,
        "source_available_utc": SOURCE_AVAILABLE_CLAIM_UTC,
        "target_as_of_utc": RESEARCH_AS_OF_UTC,
    })
    if result["production_recommendations"] != "DISABLED":
        raise ValueError("UNSAFE_PROVIDER_PROMOTION")
    # Do not make rights claims from checksum matching or README language.
    result["source_commit"] = UPSTREAM_COMMIT
    result["provider_sample_sha256"] = {
        "events": EVENTS_SHA256, "lineups": LINEUPS_SHA256,
    }
    result["data_use_scope"] = "HISTORICAL_PUBLIC_RESEARCH_ONLY"
    result["commercial_data_rights_verified"] = False
    result["historical_sample_not_certified_prospective"] = True
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline StatsBomb open-data Kloppy research smoke")
    parser.add_argument("--events", required=True, help="Official local events JSON")
    parser.add_argument("--lineups", required=True, help="Official local lineups JSON")
    args = parser.parse_args(argv)
    try:
        result = summarize_verified_statsbomb_open_data(args.events, args.lineups)
    except (OSError, ValueError, ImportError) as exc:
        print("HOLD: " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
