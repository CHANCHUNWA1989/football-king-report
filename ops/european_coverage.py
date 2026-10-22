"""Read-only audit of European competition API coverage. Never implies live data."""
import json
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "config/european_competitions_2026_27.json"
EXPECTED = {"uefa-champions-league", "uefa-europa-league", "uefa-conference-league", "premier-league", "la-liga", "serie-a", "bundesliga", "ligue-1"}

def audit(path=CONFIG):
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = obj.get("competitions")
    if obj.get("schema_version") != 1 or not isinstance(rows, list):
        raise ValueError("INVALID_MANIFEST")
    ids = [x.get("slug") for x in rows if isinstance(x, dict)]
    if len(ids) != 8 or set(ids) != EXPECTED:
        raise ValueError("INVALID_COMPETITIONS")
    policy = obj.get("provider_policy", {})
    if policy.get("fallback") != "HOLD" or policy.get("production_recommendations") != "DISABLED":
        raise ValueError("UNSAFE_POLICY")
    return {"status": "HOLD", "competitions": ids, "league_ids_verified": False, "api_entitlements_verified": False, "live_odds_verified": False, "production_recommendations": "DISABLED"}

if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False))
