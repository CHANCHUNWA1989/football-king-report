"""Offline football-data.co.uk style CSV -> private history contract.

No network. Caller must supply a vetted CSV snapshot and an explicit team
crosswalk to the exact names used by the live private quote provider.
A CSV alone does not establish independent result authenticity.
"""
import csv
import hashlib
import io
from datetime import datetime, timezone
from pathlib import Path
from ops.private_history_intake import SCHEMA, validate

FIELDS = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"}
MAX_BYTES = 1_000_000


def convert(raw, *, league, season, crosswalk, recorded_utc, source):
    if (not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES
            or not isinstance(league, str) or not league.strip()
            or not isinstance(season, str) or not season.strip()
            or not isinstance(source, str) or not source.strip()
            or not isinstance(crosswalk, dict) or not crosswalk):
        raise ValueError("INVALID_CSV_CONTRACT")
    try:
        recorded = datetime.fromisoformat(recorded_utc.replace("Z", "+00:00"))
        if recorded.tzinfo is None:
            raise ValueError("NAIVE_RECORDED_TIME")
        body = raw.decode("utf-8-sig")
        rows = csv.DictReader(io.StringIO(body, newline=""))
        if not rows.fieldnames or not FIELDS.issubset(rows.fieldnames):
            raise ValueError("MISSING_CSV_COLUMNS")
        history = []
        seen = set()
        for row in rows:
            if not row or not row.get("Date") or not row.get("HomeTeam") or not row.get("AwayTeam"):
                continue
            home, away = crosswalk.get(row["HomeTeam"]), crosswalk.get(row["AwayTeam"])
            if not isinstance(home, str) or not isinstance(away, str) or not home.strip() or not away.strip() or home == away:
                raise ValueError("MISSING_OR_INVALID_TEAM_CROSSWALK")
            if row.get("FTR") not in ("H", "D", "A"):
                raise ValueError("INVALID_FULLTIME_RESULT")
            hg, ag = int(row["FTHG"]), int(row["FTAG"])
            if not (0 <= hg <= 20 and 0 <= ag <= 20):
                raise ValueError("INVALID_GOALS")
            actual = "H" if hg > ag else "A" if hg < ag else "D"
            if row["FTR"] != actual:
                raise ValueError("RESULT_SCORE_MISMATCH")
            # Football-data CSV Date has no trusted kickoff clock. Use 00:00
            # UTC only as an offline chronology lower bound, not actual KO.
            date = datetime.strptime(row["Date"], "%d/%m/%Y").replace(tzinfo=timezone.utc)
            if date >= recorded:
                raise ValueError("RESULT_NOT_AVAILABLE_AT_CAPTURE")
            identity = (row["Date"], home, away)
            if identity in seen:
                raise ValueError("DUPLICATE_FIXTURE")
            seen.add(identity)
            eid = hashlib.sha256(("|".join((league, season, *identity))).encode()).hexdigest()
            history.append({
                "source_namespace": "the_odds_api_v4",
                "event_id": "history:" + eid, "league_id": league,
                "home_team_id": home, "away_team_id": away,
                "kickoff_utc": date.isoformat(),
                "result_recorded_utc": recorded.astimezone(timezone.utc).isoformat(),
                "home_goals": hg, "away_goals": ag,
            })
        payload = {"schema": SCHEMA, "production_recommendations": "DISABLED",
                   "source": source, "matches": history}
        validate(payload)
        return payload
    except (UnicodeError, csv.Error, ValueError, TypeError, KeyError, OverflowError):
        raise ValueError("INVALID_OR_UNMAPPED_CSV") from None


def main():
    import argparse
    import json
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True)
    p.add_argument("--crosswalk", required=True)
    p.add_argument("--league", required=True)
    p.add_argument("--season", required=True)
    p.add_argument("--recorded-utc", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    crosswalk = json.loads(Path(args.crosswalk).read_text(encoding="utf-8"))
    result = convert(Path(args.csv).read_bytes(), league=args.league,
                     season=args.season, crosswalk=crosswalk,
                     recorded_utc=args.recorded_utc, source=args.source)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print("PRIVATE_HISTORY_CONVERSION:", len(result["matches"]), "RESEARCH_ONLY")


if __name__ == "__main__":
    main()
