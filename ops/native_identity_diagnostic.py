"""Audit existing normalized gateway projections, without identity admission."""
import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

try:
    from .fixture_source_evidence import verify_for_artifact, digest, utc
except ImportError:
    from fixture_source_evidence import verify_for_artifact, digest, utc


def text_field(value):
    return isinstance(value, str) and bool(value) and value == value.strip()


def audit(doc):
    verify_for_artifact(doc)
    output = []
    for b in doc["batches"]:
        league = b["requested_league"]
        keys = Counter()
        ids = Counter(r["event_id"] for r in b["rows"] if text_field(r["event_id"]))
        candidates = []
        counts = Counter()
        for r in b["rows"]:
            if not all(text_field(r[k]) for k in ("date", "home", "away")) or r["home"] == r["away"]:
                counts["invalid_date_or_teams"] += 1
                continue
            try:
                if date.fromisoformat(r["date"]).isoformat() != r["date"]:
                    raise ValueError("NONCANONICAL_DATE")
            except ValueError:
                counts["invalid_date_or_teams"] += 1
                continue
            # Exact names only; no fuzzy match, guessed native ID or inferred league.
            key = (b["source"], b["source_url"], league, b["season"],
                   r["date"], r["home"], r["away"])
            keys[key] += 1
            candidates.append((key, r))
        fingerprints = []
        for key, r in candidates:
            if keys[key] != 1:
                counts["ambiguous_exact_fixture_rows"] += 1
                continue
            counts["unique_exact_context_rows"] += 1
            # A diagnostic fingerprint is intentionally not an event identifier.
            fingerprints.append(digest(["football-king-context-fingerprint-v1", *key]))
            native = r["event_id"]
            if not text_field(native):
                counts["missing_event_id"] += 1
            elif ids[native] != 1:
                counts["duplicate_event_id_rows"] += 1
            elif (league == "bundesliga" and b["source"] == "OpenLigaDB"
                  and b["source_url"].startswith("https://api.openligadb.de/getmatchdata/bl1/")
                  and re.fullmatch(r"openligadb:[1-9][0-9]*", native)):
                counts["unique_reported_openligadb_id"] += 1
            else:
                counts["other_unverified_event_id"] += 1
            try:
                utc(r["kickoff_utc"])
                counts["timezone_aware_kickoff_rows"] += 1
            except (ValueError, TypeError, OverflowError):
                counts["missing_or_invalid_kickoff_rows"] += 1
            counts["explicit_row_league"] += int(r["league"] == league)
        output.append({"requested_league": league, "row_count": len(b["rows"]),
                       "gateway_reported_league": b.get("gateway_reported_league"),
                       "source_context_complete": b.get("source_context_complete") is True,
                       "counts": dict(sorted(counts.items())),
                       "context_fingerprint_set_sha256": digest(sorted(fingerprints))})
    return {"schema": "football-king-native-identity-diagnostic-v1",
            "input_batches_sha256": doc["batches_sha256"], "batches": output,
            "source_identity_authenticated": False,
            "native_identity_authenticated": False,
            "missing_gateway_fixtures_proven": False,
            "admitted_new_fixtures": 0, "status": "HOLD",
            "production_recommendations": "DISABLED"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    with Path(args.input).open("rb") as f:
        raw = f.read(8_000_001)
    if not 0 < len(raw) <= 8_000_000:
        raise ValueError("INPUT_SIZE")
    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError("DUPLICATE_JSON_KEY")
            out[k] = v
        return out
    result = audit(json.loads(raw, object_pairs_hook=unique))
    result["input_file_sha256"] = hashlib.sha256(raw).hexdigest()
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
