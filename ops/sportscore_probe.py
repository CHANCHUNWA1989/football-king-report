"""One-call, no-key SportScore football availability probe; independent research only.

No raw event tables or data are redistributed. Parsed information has no
certified season, league, score provenance or point-in-time integrity.
Docs/attribution: https://sportscore.com/developers/terms/
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

URL = "https://sportscore.com/api/widget/matches/?sport=football&limit=20"
MAX_BYTES = 350_000


def sample_summary(value):
    if not isinstance(value, dict):
        raise ValueError("BAD_SOURCE_OBJECT")
    rows = value.get("matches")
    if rows is None:
        rows = value.get("data")
    if not isinstance(rows, list) or len(rows) > 50:
        raise ValueError("UNVERIFIED_SOURCE_ROWS")
    total = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        home, away = row.get("home_team"), row.get("away_team")
        if isinstance(home, dict):
            home = home.get("name")
        if isinstance(away, dict):
            away = away.get("name")
        if (isinstance(home, str) and isinstance(away, str)
                and 0 < len(home.strip()) <= 120 and 0 < len(away.strip()) <= 120
                and home.strip().casefold() != away.strip().casefold()):
            total += 1
    return {"raw_fixture_rows": len(rows), "valid_team_pair_rows": total}


def collect(*, now=None, requester=None):
    now = now or datetime.now(timezone.utc)
    result = {
        "schema": "football-king-sportscore-free-coverage-v1",
        "provider": "sportscore.com", "checked_utc": now.isoformat(),
        "status": "HOLD", "reason": "NOT_YET_QUERIED",
        "requests_attempted": 1, "requests_budget": 1,
        "eligible_team_pair_sample": 0, "returned_fixture_sample": 0,
        "six_league_identity_verified": False,
        "final_score_independently_confirmed": False,
        "provider_kickoff_time_verified": False,
        "raw_data_redistributed": False,
        "can_replace_market_odds": False,
        "production_recommendations": "DISABLED",
        "attribution": "Powered by SportScore",
        "attribution_url": "https://sportscore.com/",
        "attribution_link_required_if_data_displayed": True,
    }
    open_request = requester or urlopen
    try:
        req = Request(URL, headers={"User-Agent":"FootballKingResearch/1.0",
                                    "Accept":"application/json"})
        with open_request(req, timeout=12) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            result["reason"] = "RESPONSE_TOO_LARGE"
            return result
        summary = sample_summary(json.loads(raw.decode("utf-8")))
        result["returned_fixture_sample"] = summary["raw_fixture_rows"]
        result["eligible_team_pair_sample"] = summary["valid_team_pair_rows"]
        result["status"] = "PARTIAL" if summary["valid_team_pair_rows"] else "HOLD"
        result["reason"] = "TEAM_PAIRS_ONLY_NO_LEAGUE_OR_PIT_VALIDATION" if summary["valid_team_pair_rows"] else "NO_USABLE_TEAM_PAIR_SAMPLE"
    except HTTPError as exc:
        result["reason"] = "RATE_LIMITED" if exc.code == 429 else "SOURCE_HTTP_ERROR"
    except (URLError, OSError, TimeoutError):
        result["reason"] = "NETWORK_ERROR"
    except (TypeError, ValueError, UnicodeError, OverflowError, json.JSONDecodeError):
        result["reason"] = "SOURCE_SCHEMA_UNVERIFIED"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="sportscore-probe.json")
    args = parser.parse_args(argv)
    report = collect()
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n",
                                 encoding="utf-8")
    print(json.dumps({"status": report["status"], "reason": report["reason"],
                      "returned_fixture_sample": report["returned_fixture_sample"],
                      "eligible_team_pair_sample": report["eligible_team_pair_sample"],
                      "production_recommendations": "DISABLED"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
