"""Read-only European competition coverage audit; no API calls or secrets."""
import json
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "config/european_competitions_2026_27.json"
EXPECTED = {
    "uefa-champions-league", "uefa-europa-league", "uefa-conference-league",
    "premier-league", "la-liga", "serie-a", "bundesliga", "ligue-1",
}
REQUIRED_POLICY = {
    "league_ids": "discover_and_verify_per_provider_and_season",
    "season": "2026/27",
    "api_credentials": "github_actions_secrets_only",
    "entitlement": "must_be_verified_before_collection",
    "odds": "no_live_odds_claim_without_timestamped_provider_quote",
    "quota": "preserve_existing_limits_and_reserves",
    "fallback": "HOLD",
    "production_recommendations": "DISABLED",
}


def audit(path=CONFIG):
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = obj.get("competitions")
    if obj.get("schema_version") != 1 or not isinstance(rows, list):
        raise ValueError("INVALID_MANIFEST")
    ids = [x.get("slug") for x in rows if isinstance(x, dict)]
    if len(ids) != len(EXPECTED) or set(ids) != EXPECTED:
        raise ValueError("INVALID_COMPETITIONS")
    if any(not isinstance(row.get("name"), str) or not row["name"].strip()
           or row.get("type") not in ("continental", "domestic")
           for row in rows):
        raise ValueError("INVALID_COMPETITION_DETAILS")
    policy = obj.get("provider_policy")
    if not isinstance(policy, dict) or any(policy.get(k) != v for k, v in REQUIRED_POLICY.items()):
        raise ValueError("UNSAFE_POLICY")
    return {
        "status": "HOLD",
        "competitions": ids,
        "league_ids_verified": False,
        "api_entitlements_verified": False,
        "live_odds_verified": False,
        "production_recommendations": "DISABLED",
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False))
