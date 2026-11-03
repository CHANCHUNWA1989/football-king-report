"""Fail-closed offline link-to-fixture identity evidence from official UEFA pages.

These reviewed UEFA match-page links are NOT The Odds API provider-native IDs.
The evidence was collected by following the nine official fixture-index links;
no live page fetch or independent third-party attestation is performed at run.
"""
import re

from ucl_md4_nine_fixture_coverage import validate_manifest

SCHEMA = "football-king-uefa-match-identity-evidence-v1"
INDEX_URL = (
    "https://www.uefa.com/uefachampionsleague/news/"
    "02a8-2174c9e9019d-f909a77bd77a-1000--"
    "2026-27-champions-league-all-the-league-phase-f/"
)
# Independently pinned, source-reviewed public UEFA match-page ids, slugs,
# and displayed match headings. These are NOT bookmaker/odds-feed ids.
PINNED = {
    "ucl26m4-shakhtar-sporting":
        ("2049613", "shakhtar-vs-sporting-cp", "Shakhtar vs Sporting CP"),
    "ucl26m4-galatasaray-stuttgart":
        ("2049614", "galatasaray-vs-stuttgart", "Galatasaray vs Stuttgart"),
    "ucl26m4-atletico-bayern":
        ("2049608", "atleti-vs-bayern-munchen", "Atleti vs Bayern München"),
    "ucl26m4-barcelona-villa":
        ("2049607", "barcelona-vs-aston-villa", "Barcelona vs Aston Villa"),
    "ucl26m4-feyenoord-inter":
        ("2049610", "feyenoord-vs-inter", "Feyenoord vs Inter"),
    "ucl26m4-bodo-lille":
        ("2049611", "bodo-glimt-vs-lille", "Bodø/Glimt vs Lille"),
    "ucl26m4-lask-slovan":
        ("2049615", "lask-vs-s-bratislava", "LASK vs S. Bratislava"),
    "ucl26m4-manchester-roma":
        ("2049609", "man-utd-vs-roma", "Man Utd vs Roma"),
    "ucl26m4-villarreal-psg":
        ("2049612", "villarreal-vs-paris", "Villarreal vs Paris"),
}
EVIDENCE_KEYS = frozenset((
    "schema", "publisher", "source_index_url", "observation_date_utc",
    "evidence_method", "fixture_date_utc", "provider_bookmaker_ids_confirmed",
    "links",
))
LINK_KEYS = frozenset((
    "local_request_id", "uefa_match_id", "uefa_match_url",
    "official_page_title",
))
URL_BASE = "https://www.uefa.com/uefachampionsleague/match/"


def validate_official_links(evidence, manifest):
    """Reconcile all nine reviewed match-page links against one fixture batch.

    Each input assertion is checked against pinned review values, source URL,
    exact case identity, and unique UEFA ID. This structural gate does NOT
    independently authenticate the present live UEFA page or its ownership.
    """
    fixtures = validate_manifest(manifest)
    fixture_ids = {x["local_request_id"] for x in fixtures}
    if fixture_ids != set(PINNED):
        raise ValueError("UNEXPECTED_MANIFEST_SCOPE")
    if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_KEYS:
        raise ValueError("INVALID_OFFICIAL_EVIDENCE_SHAPE")
    if (evidence["schema"] != SCHEMA
            or evidence["publisher"] != "UEFA"
            or evidence["source_index_url"] != INDEX_URL
            or evidence["observation_date_utc"] != "2026-11-03"
            or evidence["fixture_date_utc"] != "2026-11-03"
            or evidence["evidence_method"] != (
                "FOLLOW_LINKS_FROM_UEFA_OFFICIAL_MATCHDAY4_INDEX")
            or evidence["provider_bookmaker_ids_confirmed"] is not False):
        raise ValueError("UNSUPPORTED_OFFICIAL_EVIDENCE_CLAIM")
    rows = evidence["links"]
    if not isinstance(rows, list) or len(rows) != len(fixtures):
        raise ValueError("NOT_EXACT_NINE_OFFICIAL_LINKS")
    resolved, seen_uefa_ids = {}, set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != LINK_KEYS:
            raise ValueError("INVALID_OFFICIAL_MATCH_LINK")
        local_id, official_id = row["local_request_id"], row["uefa_match_id"]
        if (not isinstance(local_id, str)
                or local_id not in PINNED
                or local_id in resolved
                or not isinstance(official_id, str)
                or re.fullmatch(r"[1-9][0-9]{6}", official_id) is None
                or official_id in seen_uefa_ids):
            raise ValueError("AMBIGUOUS_OFFICIAL_MATCH_ID")
        expected_id, slug, expected_title = PINNED[local_id]
        expected_url = URL_BASE + expected_id + "--" + slug + "/"
        if (official_id != expected_id
                or row["uefa_match_url"] != expected_url
                or row["official_page_title"] != expected_title):
            raise ValueError("OFFICIAL_INDEX_LINK_ID_OR_TITLE_MISMATCH")
        # Fix local join identity via separately validated nine-game manifest.
        resolved[local_id] = {
            "uefa_match_id": official_id,
            "uefa_match_url": expected_url,
        }
        seen_uefa_ids.add(official_id)
    if set(resolved) != fixture_ids:
        raise ValueError("OFFICIAL_ID_MANIFEST_MISMATCH")
    return resolved
