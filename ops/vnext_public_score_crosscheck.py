"""Offline check of transcribed public 2026 Bundesliga score pages.

This only checks *researcher supplied* transcriptions against pinned known
URLs and score. No HTTP, no publisher signature, no trustworthy capture time.
ALWAYS HOLD/DISABLED: not a verified independent result or OOS sample.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = "football-king-vnext-public-score-crosscheck-v1"
FIXTURE = "OpenLigaDB:83156"
KICKOFF = "2026-08-28T18:30:00Z"
DIGEST = "420aca223bdc71d3a5f88a0af8d76c54406567a296934a40bab313800b3e0e2d"
SCORE = {"home": 5, "away": 1}
PAGES = {
    "bundesliga": "https://www.bundesliga.com/en/bundesliga/matchday/2026-2027/1/fc-bayern-muenchen-vs-vfb-stuttgart/liveticker",
    "fc-bayern": "https://fcbayern.com/en/news/matchreports/2026/08/match-report-bundesliga-fc-bayern-v-vfb-stuttgart-280826",
    "vfb-stuttgart": "https://www.vfb.de/en/vfb/latest/news/professionals/2627/1-fc-bayern-muenchen----vfb-stuttgart-/",
}
FIELDS = {
    "schema", "research_only", "fixture_id", "kickoff_utc", "score_90m",
    "openligadb_observed_sha256_unattested", "review_date_utc_unattested",
    "source_original_bytes_archived", "publisher_signed_capture",
    "upstream_independence_audited", "future_model_scoring_authorized",
    "source_pages",
}
MAX_BYTES = 16384


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("DUPLICATE_MANIFEST_KEY")
        out[key] = value
    return out


def _nonfinite(value):
    raise ValueError("NONFINITE_MANIFEST_NUMBER")

def _exact_integer_score_shape(value):
    """Do not accept JSON true/false or floats as 90-minute goal counts.

    Python considers True == 1 and 5.0 == 5. Equality with a pinned score
    alone is therefore not sufficient to establish a typed result schema.
    """
    return (
        type(value) is dict
        and set(value) == {"home", "away"}
        and type(value["home"]) is int
        and type(value["away"]) is int
    )


def _hold(reason, **extra):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "public_page_transcription_consistent": False,
        "sources_upstream_independence_authenticated": False,
        "source_original_bytes_archived_and_verified": False,
        "publisher_identity_independently_authenticated": False,
        "capture_timestamp_independently_attested": False,
        "result_truth_independently_authenticated": False,
        "prematch_forecast_witness_verified": False,
        "eligible_for_model_scoring": False,
        "certified_prospective_samples": 0,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED", **extra,
    }


def audit_manifest_bytes(raw):
    """Offline structural consistency only, never independent web verification."""
    try:
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
            raise ValueError("INVALID_PUBLIC_CROSSCHECK_MANIFEST_SIZE")
        obj = json.loads(raw, object_pairs_hook=_unique,
                         parse_constant=_nonfinite)
        if type(obj) is not dict or set(obj) != FIELDS:
            raise ValueError("UNEXPECTED_PUBLIC_CROSSCHECK_SCHEMA")
        if not _exact_integer_score_shape(obj["score_90m"]):
            raise ValueError("INVALID_EXACT_SCORE_TYPES")
        if (obj["schema"] != SCHEMA or obj["research_only"] is not True
                or obj["fixture_id"] != FIXTURE or obj["kickoff_utc"] != KICKOFF
                or obj["score_90m"] != SCORE
                or obj["openligadb_observed_sha256_unattested"] != DIGEST
                or obj["review_date_utc_unattested"] != "2026-11-15"):
            raise ValueError("PUBLIC_CROSSCHECK_FIXTURE_OR_DIGEST_CONFLICT")
        for flag in ("source_original_bytes_archived", "publisher_signed_capture",
                     "upstream_independence_audited", "future_model_scoring_authorized"):
            if obj[flag] is not False:
                raise ValueError("SELF_CERTIFICATION_NOT_ALLOWED")
        pages = obj["source_pages"]
        if type(pages) is not list or len(pages) != len(PAGES):
            raise ValueError("PUBLIC_CROSSCHECK_SOURCE_COUNT_INVALID")
        seen = set()
        for page in pages:
            if type(page) is not dict or set(page) != {
                "publisher", "url", "score_90m", "fixture_date", "home", "away"
            }:
                raise ValueError("INVALID_PAGE_TRANSCRIPTION")
            provider = page["publisher"]
            if (type(provider) is not str or provider not in PAGES
                    or provider in seen):
                raise ValueError("DUPLICATE_OR_UNKNOWN_PUBLIC_PUBLISHER")
            seen.add(provider)
            url = page["url"]
            if (type(url) is not str or url != PAGES[provider]
                    or urlsplit(url).scheme != "https"
                    or urlsplit(url).username is not None
                    or urlsplit(url).password is not None):
                raise ValueError("UNPINNED_PUBLIC_SOURCE_URL")
            if not _exact_integer_score_shape(page["score_90m"]):
                raise ValueError("INVALID_EXACT_SCORE_TYPES")
            if (page["score_90m"] != SCORE
                    or page["fixture_date"] != "2026-08-28"
                    or page["home"] != "FC Bayern München"
                    or page["away"] != "VfB Stuttgart"):
                raise ValueError("PUBLIC_PAGE_FIXTURE_OR_SCORE_DISAGREEMENT")
        if seen != set(PAGES):
            raise ValueError("PUBLIC_CROSSCHECK_SOURCE_SET_INVALID")
        return _hold(
            "PUBLIC_PAGE_SCORE_TRANSCRIPTIONS_AGREE_BUT_UNATTESTED",
            public_page_transcription_consistent=True,
            source_page_count=len(pages),
            fixture_id=FIXTURE, transcribed_score_90m=dict(SCORE),
        )
    except (ValueError, TypeError, KeyError, OverflowError, UnicodeError) as exc:
        reason = str(exc)
        return _hold(reason if len(reason) < 120 else
                     "INVALID_PUBLIC_CROSSCHECK_MANIFEST")


def main(argv=None):
    cli = argparse.ArgumentParser(description="Offline source transcript check")
    cli.add_argument("--manifest", required=True)
    args = cli.parse_args(argv)
    try:
        path = Path(args.manifest)
        if path.is_symlink() or any(p.is_symlink() for p in path.parents):
            raise ValueError("UNSAFE_MANIFEST_PATH")
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise ValueError("INVALID_PUBLIC_CROSSCHECK_MANIFEST_SIZE")
        result = audit_manifest_bytes(path.read_bytes())
    except (OSError, ValueError) as exc:
        result = _hold(str(exc) if len(str(exc)) < 120 else "UNREADABLE_MANIFEST")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["public_page_transcription_consistent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
