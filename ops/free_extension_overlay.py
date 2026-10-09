"""Read-only iPhone status for optional new free API and historical open data."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from research_extensions_guard import validate

PROVIDERS = ("openfootapi", "statsbomb_open_data")


def default(now):
    return {
        "schema": "football-king-free-research-extension-site-v1",
        "generated_utc": now.isoformat(),
        "status": "HOLD",
        "reason": "SOURCE_NOT_COLLECTED",
        "providers": [
            {"provider": name, "status": "NOT_YET_COLLECTED",
             "configured": False, "catalogue_entries": 0,
             "observed_fixtures": 0}
            for name in PROVIDERS
        ],
        "historical_data_only_cannot_validate_current_season": True,
        "no_paid_or_unlicensed_1x2_quotes": True,
        "used_to_promote_model": False,
        "production_recommendations": "DISABLED",
    }


def build(snapshot, *, now=None):
    now = now or datetime.now(timezone.utc)
    out = default(now)
    if snapshot is None:
        return out
    try:
        collected = validate(snapshot, now=now)
        seconds = (now - collected).total_seconds()
        if not -300 <= seconds <= 36*3600:
            out["reason"] = "SOURCE_CATALOG_STALE"
            return out
    except (ValueError, KeyError, TypeError, OverflowError, AttributeError):
        out["reason"] = "SOURCE_CATALOG_INVALID"
        return out
    out["status"] = "RESEARCH_ONLY"
    out["reason"] = "FREE_RESEARCH_CATALOG_COVERAGE_ONLY"
    out["collected_utc"] = collected.isoformat()
    out["providers"] = [
        {"provider": p["provider"], "status": p["status"],
         "configured": p["configured"],
         "catalogue_entries": p["catalogue_entries"],
         "observed_fixtures": p["observed_fixtures"],
         "attempted_requests": p["attempted_requests"],
         "issues": p["issues"][:5]}
        for p in snapshot["providers"]
    ]
    return out


def publish(site, source):
    site = Path(site)
    raw = None
    path = Path(source)
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError, OSError):
            pass
    result = build(raw)
    (site/"free_research_extensions.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],
                      "providers":{p["provider"]:p["status"] for p in result["providers"]},
                      "production_recommendations":"DISABLED"},ensure_ascii=False))
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--site",default="app/site")
    p.add_argument("--input",default="sources/research_extensions_latest.json")
    args=p.parse_args()
    publish(args.site,args.input)
