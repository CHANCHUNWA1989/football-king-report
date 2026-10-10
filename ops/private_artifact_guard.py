"""Redact all market prices, bookmaker identifiers, and fixture identities before upload.

Actions artifacts of public GitHub repositories must not be considered private.
"""
import argparse
import json
from pathlib import Path

ALLOWED = {"CONNECTED", "QUOTA_GUARD", "MISSING_API_KEY",
           "PROVIDER_ERROR", "NO_ACTIVE_LEAGUES", "UNKNOWN"}
MARKETS = {"h2h", "spreads", "totals"}

def sanitize(screen, readiness):
    if not isinstance(screen, dict) or not isinstance(readiness, dict):
        raise ValueError("INVALID_REPORT")
    status = screen.get("input_status", "UNKNOWN")
    if status not in ALLOWED:
        status = "UNKNOWN"
    counts = {}
    for key in ("RESEARCH_ONLY", "STALE", "INCOMPLETE", "INVALID",
                "VERIFIED_VALUE", "NO_VALUE"):
        n = screen.get("counts", {}).get(key, 0)
        counts[key] = n if type(n) is int and 0 <= n <= 100000 else 0
    counts["VERIFIED_VALUE"] = 0  # no trusted verifier is present
    cover = []
    for item in screen.get("coverage", [])[:50]:
        if not isinstance(item, dict):
            continue
        league = item.get("league")
        if league not in ("epl", "championship", "bundesliga",
                          "laliga", "seriea", "ligue1"):
            continue
        n = item.get("quotes", 0)
        cover.append({"league": league,
                      "quotes": n if type(n) is int and 0 <= n <= 100000 else 0,
                      "status": "COUNTS_ONLY"})
    progress = readiness.get("grounded_progress")
    allowed_progress = (
        "settled_cases_in_archive", "settled_cases_required",
        "additional_settled_cases_needed", "independently_verified_result_cases",
        "independent_week_blocks", "minimum_week_blocks",
        "leagues_with_40_settlements", "minimum_leagues_with_40",
        "seven_quality_gates_passed", "seven_quality_gates_required")
    evidence = {k: progress[k] for k in allowed_progress
                if isinstance(progress, dict) and type(progress.get(k)) is int}
    return {"schema": "football-king-public-artifact-summary-v1",
            "input_status": status, "counts": counts, "coverage": cover,
            "requested_markets": [m for m in screen.get("requested_markets", []) if m in MARKETS],
            "evidence_progress": evidence, "production_recommendations": "DISABLED",
            "raw_prices_or_bookmakers_included": False,
            "quotes_are_executable": False, "verified_bets": 0}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--screen", default="output/private_all_market_screen.json")
    p.add_argument("--readiness", default="output/recommendation_readiness.json")
    p.add_argument("--output", default="output/private_all_market_public_summary.json")
    args = p.parse_args()
    result = sanitize(json.loads(Path(args.screen).read_text(encoding="utf-8")),
                      json.loads(Path(args.readiness).read_text(encoding="utf-8")))
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PUBLIC_SUMMARY:", result["input_status"], result["counts"])

if __name__ == "__main__":
    main()
