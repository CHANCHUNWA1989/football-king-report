"""One reproducible, zero-secret J3 postmatch reference, not model training.

This module validates the manually transcribed official-page result record
against a fixed public identity. It NEVER fetches publisher bytes, authenticates
independent upstreams or reconstructs an original pre-match decision. One
official result observation is NOT a certified forward-model settlement.
"""
import math

EXPECTED = {
    "schema": "football-king-j3-postmatch-single-public-page-research-v1",
    "source_publisher": "J.LEAGUE",
    "source_url": "https://www.jleague.jp/en/match/j3/2026/111516/",
    "source_reviewed_date_hkt": "2026-11-15",
    "source_raw_bytes_archived": False,
    "source_timestamp_authenticated": False,
    "independent_result_verified": False,
    "league": "j3",
    "season": "2026-27",
    "event_id": "jleague-j3-2026-111516",
    "home_id": "reilac-shiga",
    "away_id": "fc-osaka",
    "kickoff_utc": "2026-11-15T09:03:00+00:00",
    "match_status": "FT",
    "home_goals": 1,
    "away_goals": 1,
    "research_direction": "AWAY",
    "original_selection_provenance": "CHAT_REFERENCE_ONLY_NOT_SEALED",
    "reference_decimal_price": 1.91,
    "reference_price_executable": False,
    "original_model_probability": None,
    "forecast_sealed_before_kickoff": False,
    "positive_ev_verified": False,
    "actual_bet_profit": None,
    "source_independence_proven": False,
    "postmatch_reference_not_pre_match_history": True,
    "production_recommendations": "DISABLED",
    "status": "HOLD",
}
EXPLANATORY_KEY = "explanatory_note"


def examine(record):
    """Return an always-unverified qualitative outcome, never any stake/EV.

    The caller passes manually observed data. Field checks do not establish
    that any page was cryptographically captured, was immutable or was
    independently verified. Do not promote even if every field matches.
    """
    if (not isinstance(record, dict)
            or set(record) != set(EXPECTED) | {EXPLANATORY_KEY}):
        raise ValueError("UNEXPECTED_POSTMATCH_REFERENCE_FIELDS")
    for field, wanted in EXPECTED.items():
        value = record[field]
        if type(value) is not type(wanted) or value != wanted:
            raise ValueError("POSTMATCH_REFERENCE_MISMATCH_" + field.upper())
    note = record[EXPLANATORY_KEY]
    if not isinstance(note, str) or not 25 <= len(note) <= 1000:
        raise ValueError("INVALID_POSTMATCH_SOURCE_CAVEAT")
    # Outcome is deterministically derived from the two goal counts.
    # No claim of a bookmaker return, actual bet or original sealed model.
    h, a = record["home_goals"], record["away_goals"]
    outcome = ("HOME" if h > a else "AWAY" if a > h else "DRAW")
    qual = "FULL_WIN" if outcome == record["research_direction"] else "FULL_LOSS"
    return {
        "schema": "football-king-j3-postmatch-reference-examination-v1",
        "status": "HOLD",
        "fixture_id": record["event_id"],
        "official_source_url": record["source_url"],
        "kickoff_utc": record["kickoff_utc"],
        "match_status_from_public_page": record["match_status"],
        "score_ft_official_page_claim": [h, a],
        "original_research_direction": record["research_direction"],
        "original_direction_from_chat_only": True,
        "qualitative_direction_result": qual,
        "reference_decimal_price_from_chat_only": 1.91,
        "raw_official_source_bytes_archived": False,
        "independent_source_ft_authenticated": False,
        "source_independence": "NOT_ESTABLISHED",
        "pre_kickoff_model_snapshot_authenticated": False,
        "executable_bookmaker_odds_verified": False,
        "calibrated_away_win_probability": None,
        "actual_bet_profit": None,
        "ev_verified": False,
        "validated_positive_ev": False,
        "eligible_for_venue_split_training": False,
        "eligible_for_model_scoring": False,
        "archive_admission": "DENIED_POSTMATCH_UNSEALED",
        "production_recommendations": "DISABLED",
    }
