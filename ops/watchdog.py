"""Independently check published GitHub Pages quality and freshness."""
import argparse
import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen


def parse_utc(value):
    d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return d.astimezone(timezone.utc)


def evaluate(status, quality, now=None, max_age_hours=10):
    now = now or datetime.now(timezone.utc)
    failures = []
    if not isinstance(status, dict) or not isinstance(quality, dict):
        return {"ok": False, "failures": ["INVALID_JSON_OBJECT"]}
    try:
        if status.get("checked_utc") != quality.get("checked_utc"):
            failures.append("STATUS_QUALITY_TIME_MISMATCH")
        age_hours = (now - parse_utc(status["checked_utc"])).total_seconds() / 3600
        if not (-5 / 60 <= age_hours <= max_age_hours):
            failures.append("PUBLISHED_REPORT_STALE_OR_FUTURE")
    except (ValueError, KeyError, TypeError, OverflowError):
        age_hours = None
        failures.append("PUBLISHED_TIME_INVALID")
    if status.get("production_recommendations") != "DISABLED":
        failures.append("UNSAFE_RECOMMENDATIONS_ENABLED")
    if status.get("status") not in ("RESEARCH_ONLY", "HOLD"):
        failures.append("INVALID_PUBLIC_STATUS")
    if status.get("status") == "HOLD":
        failures.append("PUBLIC_SOURCE_HOLD")
    if status.get("quality_status") != quality.get("status"):
        failures.append("QUALITY_STATUS_MISMATCH")
    if quality.get("critical_errors"):
        failures.append("QUALITY_CRITICAL_ERROR")
    return {
        "ok": not failures,
        "failures": sorted(set(failures)),
        "published_checked_utc": status.get("checked_utc"),
        "published_age_hours": round(age_hours, 2) if age_hours is not None else None,
        "research_only": True,
        "production_recommendations": "DISABLED",
    }


def evaluate_research_layers(crosscheck, shadow, validation):
    """Check every published research-only layer; do not mistake HTTP 200 for safety."""
    errors = []
    if crosscheck.get("production_recommendations") != "DISABLED":
        errors.append("CROSSCHECK_SAFETY_FLAG")
    if crosscheck.get("status") not in ("PARTIAL_CHECK", "INCONCLUSIVE"):
        errors.append("INDEPENDENT_SOURCE_CHECK_NOT_SAFE")
    if crosscheck.get("all_leagues_verified") is not False:
        errors.append("MISLEADING_ALL_LEAGUES_VERIFIED")
    if shadow.get("production_recommendations") != "DISABLED":
        errors.append("SHADOW_SAFETY_FLAG")
    if shadow.get("model_calibrated") is not False or shadow.get("market_odds_available") is not False:
        errors.append("INVALID_SHADOW_RESEARCH_PROVENANCE")
    rows = shadow.get("predictions")
    if not isinstance(rows, list) or len(rows) != shadow.get("predictions_count"):
        errors.append("SHADOW_COUNT_MISMATCH")
    if validation.get("status") != "HOLD" or validation.get("production_recommendations") != "DISABLED":
        errors.append("INVALID_MARKET_EVIDENCE_STATE")
    return errors


def fetch_json(url):
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "FootballKingPagesWatchdog/1.0"})
    with urlopen(req, timeout=15) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("PUBLIC_RESPONSE_TOO_BIG")
    return json.loads(raw)


def check_published(base_url, now=None, max_age_hours=10):
    base = base_url.rstrip("/") + "/"
    if not base.startswith("https://"):
        raise ValueError("HTTPS_REQUIRED")
    status, quality = fetch_json(base + "status.json"), fetch_json(base + "quality.json")
    result = evaluate(status, quality, now=now, max_age_hours=max_age_hours)
    extra = evaluate_research_layers(fetch_json(base + "crosscheck.json"),
                                     fetch_json(base + "shadow.json"),
                                     fetch_json(base + "validation.json"))
    result["failures"] = sorted(set(result["failures"] + extra))
    result["ok"] = not result["failures"]
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--max-age-hours", type=float, default=10)
    a = p.parse_args()
    try:
        result = check_published(a.base, max_age_hours=a.max_age_hours)
    except Exception as exc:
        result = {"ok": False, "failures": ["PAGE_UNAVAILABLE_OR_INVALID_" + type(exc).__name__]}
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["ok"] else 1)
