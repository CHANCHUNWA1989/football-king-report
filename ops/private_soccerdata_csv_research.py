"""Strict offline CSV importer for settled football-data-style match records.

Supported columns: Date, HomeTeam, AwayTeam, FTHG, FTAG.
Date must be ISO YYYY-MM-DD or explicit DD/MM/YYYY; no two-digit years.
00:00:00 is a calendar grouping marker, NEVER a claimed kickoff time.
Caller is responsible for obtaining and using data under its license.
"""
import argparse
import csv
from datetime import datetime
import json
import math
import sys
from ops.private_soccerdata_research_cli import run


def import_settled_csv(path, *, min_train=30, test_days=7, max_rows=5000):
    if type(max_rows) is not int or not 1 <= max_rows <= 50000:
        raise ValueError("INVALID_ROW_LIMIT")
    records = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("MISSING_CSV_COLUMNS")
        for line, row in enumerate(reader, start=2):
            if len(records) >= max_rows:
                raise ValueError("CSV_ROW_LIMIT_EXCEEDED")
            if None in row or any(row[k] is None for k in required):
                raise ValueError("MALFORMED_CSV_ROW")
            date_text = row["Date"].strip()
            fmt = "%Y-%m-%d" if len(date_text) == 10 and date_text[4] == "-" else "%d/%m/%Y"
            try:
                date = datetime.strptime(date_text, fmt)
                if date.strftime(fmt) != date_text:
                    raise ValueError("NONCANONICAL_DATE")
            except ValueError as exc:
                raise ValueError("INVALID_CSV_DATE") from exc
            home, away = row["HomeTeam"].strip(), row["AwayTeam"].strip()
            if not home or not away or home == away:
                raise ValueError("INVALID_CSV_TEAMS")
            goals = []
            for field in ("FTHG", "FTAG"):
                value = row[field].strip()
                if not value.isascii() or not value.isdecimal() or len(value) > 2:
                    raise ValueError("INVALID_CSV_SCORE")
                number = int(value)
                if number > 30:
                    raise ValueError("INVALID_CSV_SCORE")
                goals.append(number)
            hg, ag = goals
            records.append({
                "source": "soccerdata.MatchHistory",
                "source_index": str(line),
                "source_local_match_datetime": date.strftime("%Y-%m-%dT00:00:00"),
                "date_only_calendar_marker": True,
                "kickoff_utc": None, "kickoff_time_verified": False,
                "home_team": home, "away_team": away,
                "home_goals": hg, "away_goals": ag,
                "outcome": "H" if hg > ag else "A" if hg < ag else "D",
                "odds_capture_verified": False,
                "pre_match_features_verified": False,
                "production_recommendations": "DISABLED"})
    if not records:
        raise ValueError("EMPTY_CSV")
    return {"schema": "football-king-soccerdata-research-input-v1",
            "records": records, "min_train": min_train, "test_days": test_days}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output", help="Optional research report JSON file")
    parser.add_argument("--min-train", type=int, default=30)
    parser.add_argument("--test-days", type=int, default=7)
    args = parser.parse_args(argv)
    try:
        payload = import_settled_csv(args.csv, min_train=args.min_train,
                                     test_days=args.test_days)
        result = run(payload)
        result["input_caveat"] = "Date-only CSV: midnight is a calendar marker, not kickoff. Source rights and availability unverified."
        rendered = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(rendered)
        else:
            sys.stdout.write(rendered)
    except (ValueError, TypeError, KeyError, OSError, csv.Error) as exc:
        parser.exit(2, f"CSV_RESEARCH_INPUT_REJECTED: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
