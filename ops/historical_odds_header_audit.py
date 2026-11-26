"""Offline CSV header classification for historical football odds.

Never downloads data. Historical closing odds are not pre-match executable quotes.
"""
import csv
from io import StringIO


def inspect_headers(header_line):
    if not isinstance(header_line, str) or not header_line.strip():
        return {"status": "HOLD", "reason": "EMPTY_HEADER"}
    try:
        headers = next(csv.reader(StringIO(header_line)))
    except (csv.Error, StopIteration):
        return {"status": "HOLD", "reason": "INVALID_HEADER"}
    headers = [h.strip().lstrip("\ufeff") for h in headers]
    if len(headers) != len(set(headers)) or any(not h for h in headers):
        return {"status": "HOLD", "reason": "DUPLICATE_OR_BLANK_HEADERS"}
    fixture = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    if not fixture.issubset(headers):
        return {"status": "HOLD", "reason": "MISSING_FIXTURE_OR_RESULT_FIELDS",
                "missing": sorted(fixture - set(headers))}
    # Candidate columns only. No implicit mapping of opening to closing prices.
    totals = [h for h in headers if h in ("B365>2.5", "B365<2.5",
              "P>2.5", "P<2.5", "PC>2.5", "PC<2.5", "Avg>2.5", "Avg<2.5")]
    asian = [h for h in headers if h in ("AHh", "B365AHH", "B365AHA",
             "PAHH", "PAHA", "PCAHH", "PCAHA")]
    return {"status": "SCHEMA_CANDIDATE_ONLY", "fixture_columns": sorted(fixture),
            "totals_candidate_columns": totals, "asian_candidate_columns": asian,
            "production_recommendations": "DISABLED"}
